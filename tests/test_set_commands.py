"""Outgoing set commands: the id, the audit log line.

References: EcoFlow "General information", "Request Topic's Common Field"
("id: Message ID, unique per request ... Response will return the same id");
tolwi/hassio-ecoflow-cloud#819, #922 (settings changed without a traceable command).
"""

import json

from custom_components.ecoflow_cloud.api.message import JSONMessage
from tests.stream_fakes import MASTER, FakeClient, find_entity, make_stream


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
