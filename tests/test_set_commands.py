"""Outgoing set commands: the id, the audit log line.

References: EcoFlow "General information", "Request Topic's Common Field"
("id: Message ID, unique per request ... Response will return the same id");
tolwi/hassio-ecoflow-cloud#819, #922 (settings changed without a traceable command).
"""

import asyncio
import json

from custom_components.ecoflow_cloud.api.commands import SET_REPLY_TIMEOUT_SEC, PendingCommands, evaluate_set_reply
from custom_components.ecoflow_cloud.api.message import JSONMessage
from custom_components.ecoflow_cloud.devices.data_holder import PreparedData
from tests.stream_fakes import MASTER, SLAVE, FakeClient, find_entity, make_stream


def test_json_message_id_is_stable_across_serialisations():
    # A set_reply can only be matched if the id that went out is the id we keep
    message = JSONMessage({"sn": "BK11", "params": {"cfgFeedGridMode": 2}})

    first = json.loads(message.to_mqtt_payload())  # type: ignore[arg-type]
    second = json.loads(message.to_mqtt_payload())  # type: ignore[arg-type]

    assert first["id"] == second["id"] == message.message_id


def test_json_message_describe_is_the_sent_payload():
    message = JSONMessage({"sn": "BK11", "params": {"cfgFeedGridMode": 2}})

    assert json.loads(message.describe()) == json.loads(message.to_mqtt_payload())  # type: ignore[arg-type]


def test_no_set_command_while_disconnected():
    # paho would queue it and deliver it after the next connect, however late
    client = FakeClient(MASTER)
    device = make_stream(client, MASTER)
    device.data.params["feedGridMode"] = 1
    client.mqtt_client.connected = False  # type: ignore[attr-defined]

    find_entity(device, client, "feedGridMode").turn_on()

    assert client.mqtt_client.published == []  # type: ignore[attr-defined]
    # no optimistic state either: the switch keeps showing the real setting
    assert device.data.params["feedGridMode"] == 1


# set_reply evaluation. References: general_information.md, "Reply Topic's
# Common Field" (code 0 / -1 / -2, same id as the request); stream.md,
# "Set & Set Reply" (data.configOk, actionId, id).


def test_evaluate_documented_replies():
    assert evaluate_set_reply({"data": {"cfgFeedGridMode": 1, "configOk": True, "actionId": 381}, "id": 123}) is None
    assert evaluate_set_reply({"code": "0", "data": {"ack": 1}, "id": 1}) is None  # ack is not judged
    assert evaluate_set_reply({"data": {"configOk": False}, "id": 1}) == "configOk is false"
    assert evaluate_set_reply({"code": "-2", "id": 1}) == "code -2: the device is offline"
    assert evaluate_set_reply({"code": "-1", "id": 1}) == "code -1: the device does not belong to this account"
    assert evaluate_set_reply({"code": 5, "message": "busy", "id": 1}) == "code 5: busy"


def _sent_feed_in(client: FakeClient, device) -> str:
    device.data.params["feedGridMode"] = 1
    find_entity(device, client, "feedGridMode").turn_on()
    assert device.data.params["feedGridMode"] == 2  # optimistic
    return client.mqtt_client.published[-1][1]["id"]  # type: ignore[attr-defined]


def _reply(client: FakeClient, message_id, config_ok: bool) -> None:
    payload = {"data": {"cfgFeedGridMode": 2, "configOk": config_ok, "actionId": 381}, "id": int(message_id)}
    client.on_set_reply(json.dumps(payload).encode())


def test_rejected_command_restores_previous_state():
    client = FakeClient(MASTER)
    device = make_stream(client, MASTER)
    message_id = _sent_feed_in(client, device)

    _reply(client, message_id, config_ok=False)

    assert device.data.params["feedGridMode"] == 1
    assert len(client.pending_commands) == 0


def test_accepted_command_keeps_state():
    client = FakeClient(MASTER)
    device = make_stream(client, MASTER)
    message_id = _sent_feed_in(client, device)

    _reply(client, message_id, config_ok=True)
    client.expire_pending_commands()

    assert device.data.params["feedGridMode"] == 2
    assert len(client.pending_commands) == 0


def test_reply_for_another_command_is_ignored():
    client = FakeClient(MASTER)
    device = make_stream(client, MASTER)
    message_id = _sent_feed_in(client, device)

    _reply(client, int(message_id) + 1, config_ok=False)  # e.g. a command from the app

    assert device.data.params["feedGridMode"] == 2
    assert len(client.pending_commands) == 1


def test_unanswered_command_is_rolled_back_after_timeout():
    now = [0.0]
    client = FakeClient(MASTER)
    client.pending_commands = PendingCommands(clock=lambda: now[0])
    device = make_stream(client, MASTER)
    _sent_feed_in(client, device)

    client.expire_pending_commands()
    assert device.data.params["feedGridMode"] == 2

    now[0] += SET_REPLY_TIMEOUT_SEC
    client.expire_pending_commands()
    assert device.data.params["feedGridMode"] == 1


def test_device_report_after_the_command_wins_over_rollback():
    client = FakeClient(MASTER)
    device = make_stream(client, MASTER)
    message_id = _sent_feed_in(client, device)
    device.data.add_data(PreparedData(None, {"params": {"feedGridMode": 2}}, None))

    _reply(client, message_id, config_ok=False)

    assert device.data.params["feedGridMode"] == 2


def test_later_command_is_not_undone_by_an_earlier_rejection():
    client = FakeClient(MASTER)
    device = make_stream(client, MASTER)
    first = _sent_feed_in(client, device)
    find_entity(device, client, "feedGridMode").turn_off()  # optimistic 1 again

    _reply(client, first, config_ok=False)

    assert device.data.params["feedGridMode"] == 1
    assert len(client.pending_commands) == 1


def test_rejected_routed_command_looks_the_main_sn_up_again():
    client = FakeClient(MASTER)
    device = make_stream(client, SLAVE)
    asyncio.run(client.async_refresh_main_sns())
    assert device.main_sn_cache is not None and not device.main_sn_cache.due()
    message_id = _sent_feed_in(client, device)

    _reply(client, message_id, config_ok=False)

    assert device.main_sn_cache.due()


def test_devices_without_opt_in_are_not_tracked(monkeypatch):
    client = FakeClient(MASTER)
    device = make_stream(client, MASTER)
    monkeypatch.setattr(device, "evaluates_set_replies", lambda: False)

    _sent_feed_in(client, device)
    client.expire_pending_commands()

    assert len(client.pending_commands) == 0
    assert device.data.params["feedGridMode"] == 2
