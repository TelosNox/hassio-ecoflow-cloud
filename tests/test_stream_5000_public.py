"""STREAM 5000 (ES21) on the public API.

Payloads are the examples from EcoFlow's "STREAM 5000 Series" document (2026-10-29).

ES22 stays out of device_by_sn_prefix on purpose. The document names "STREAM 5000
AC" as supported, but every example is an ES21 and the open API was still reported
to refuse ES22 with error 1006 (MichelFR/ha-ecoflow-iot#19; #27 on 2026-10-30 has
ES22 still unsupported there). Add it once someone has seen data for one.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.ecoflow_cloud.api.commands import evaluate_set_reply
from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices.internal.stream_ac_5000 import StreamAC5000
from custom_components.ecoflow_cloud.devices.public.stream_5000 import Stream5000, flatten_quota
from custom_components.ecoflow_cloud.devices.registry import device_by_product, devices
from tests.stream_fakes import ACCOUNT, FakeClient

SN = "ES21ZE1B2J6H0060"
MAIN = "ES21ZE1B2J6H0099"

HTTP_QUOTA = {
    "sysEnergyStreamReport-pvPwr": 4,
    "sysEnergyStreamReport-bpPwr": -786,
    "sysEnergyStreamReport-bpSoc": 91,
    "sysEnergyStreamReport-loadPwr": 875,
    "sysEnergyStreamReport-gridPwr": 85,
    "sysEnergyStreamReport-onGridPwr": 790,
    "bpBackupConfig-backupSocOnOff": True,
    "bpBackupConfig-backupSoc": 50,
    "workMode": "SELF_CONSUMPTION",
    "powerParameterConfig-feedToGridLimitOnOff": False,
    "devSwitch-acSocketOnoff": True,
}
MQTT_REPORT = {
    "sysEnergyStreamReport": {
        "bpSoc": 4,
        "onGridPwr": -2493,
        "pvPwr": 0,
        "bpPwr": 2493,
        "gridPwr": 2693,
        "loadPwr": 200,
    }
}
MQTT_CONFIG = {
    "workMode": "TIMER_TASK",
    "bpBackupConfig": {"backupSocOnOff": True, "backupSoc": 50},
    "devSwitch": {"acSocketOnoff": False},
    "powerParameterConfig": {"feedToGridLimitOnOff": True},
}


class Client(FakeClient):
    def __init__(self, main_sn: str | None = SN) -> None:
        super().__init__(main_sn)
        self.responses: dict[str, dict] = {}

    async def call_api(self, endpoint: str, params: dict[str, str] | None = None) -> dict:
        if endpoint in self.responses:
            return self.responses[endpoint]
        return await super().call_api(endpoint, params)


def make_device(client: FakeClient, sn: str = SN) -> Stream5000:
    options = DeviceOptions(5, -1, False, False, 300, True)
    info = client._create_device_info(sn, sn, "STREAM 5000", 1)
    device = Stream5000(info, DeviceData(sn, sn, "STREAM 5000", options, None, None))
    device.coordinator = SimpleNamespace()  # type: ignore[assignment]
    client.add_device(device)
    return device


def entity(device: Stream5000, client: FakeClient, key: str) -> Any:
    entities: list[Any] = [*device.switches(client), *device.numbers(client), *device.selects(client)]
    return next(e for e in entities if e.mqtt_key == key)


def push(device: Stream5000, payload: dict) -> None:
    device.update_data(json.dumps(payload).encode(), device.device_info.data_topic)


def published(client: FakeClient) -> tuple[str, dict]:
    return client.mqtt_client.published[-1]  # type: ignore[attr-defined]


def test_registered_next_to_the_private_device():
    assert device_by_product["STREAM 5000"] is Stream5000
    assert devices["STREAM_5000"] is StreamAC5000


def test_http_and_mqtt_end_on_one_key():
    client = Client()
    client.responses["/device/quota/all"] = {"code": "0", "message": "Success", "data": HTTP_QUOTA}
    device = make_device(client)

    asyncio.run(client.quota_all(SN))
    assert device.data.params == HTTP_QUOTA

    push(device, MQTT_REPORT)
    push(device, MQTT_CONFIG)

    assert set(device.data.params) == set(HTTP_QUOTA)
    assert device.data.params["sysEnergyStreamReport-gridPwr"] == 2693
    assert device.data.params["bpBackupConfig-backupSoc"] == 50
    assert device.data.params["workMode"] == "TIMER_TASK"


@pytest.mark.parametrize(
    "payload",
    [
        MQTT_REPORT,
        {"param": MQTT_REPORT},
        {"params": MQTT_REPORT},
        {"sysEnergyStreamReport-pvPwr": 0, "sysEnergyStreamReport-bpPwr": 2493},
    ],
)
def test_flatten_accepts_every_shape_without_a_command_prefix(payload):
    flat = flatten_quota({"cmdFunc": 254, "cmdId": 21, **payload})
    assert flat["sysEnergyStreamReport-pvPwr"] == 0
    assert flat["sysEnergyStreamReport-bpPwr"] == 2493


def test_malformed_frame_changes_nothing():
    device = make_device(Client())
    device.update_data(b"\x0a\x03not json", device.device_info.data_topic)
    assert device.data.params == {}


def test_status_message_sets_online_state():
    device = make_device(Client())
    online: list[bool] = []
    device.status_tracker.on_explicit_status = online.append  # type: ignore[assignment,method-assign]
    assert device.device_info.status_topic is not None

    device.update_data(
        json.dumps({"id": "1", "version": "1.0", "timestamp": 1, "params": {"status": 1}}).encode(),
        device.device_info.status_topic,
    )

    assert online == [True]


def test_every_entity_finds_its_value() -> None:
    client = Client()
    device = make_device(client)
    device.data.params.update(HTTP_QUOTA)

    entities: list[Any] = [
        *(s for s in device.sensors(client) if hasattr(s, "mqtt_key")),
        *device.switches(client),
        *device.numbers(client),
        *device.selects(client),
    ]

    assert {e.mqtt_key for e in entities} == set(HTTP_QUOTA)
    for e in entities:
        assert [m.value for m in e._mqtt_key_expr.find(device.data.params)] == [HTTP_QUOTA[e.mqtt_key]]


def test_unique_id_format():
    client = Client()
    grid = next(s for s in make_device(client).sensors(client) if getattr(s, "mqtt_key", "").endswith("gridPwr"))
    assert grid.unique_id == f"ecoflow-api-{SN}-sysEnergyStreamReport-gridPwr"


@pytest.mark.parametrize(
    ("key", "act", "params"),
    [
        (
            "bpBackupConfig-backupSocOnOff",
            lambda e: e.turn_on(),
            {"bpBackupConfig": {"backupSocOnOff": True}},
        ),
        (
            "bpBackupConfig-backupSocOnOff",
            lambda e: e.turn_off(),
            {"bpBackupConfig": {"backupSocOnOff": False, "backupSoc": 0}},
        ),
        (
            "bpBackupConfig-backupSoc",
            lambda e: asyncio.run(e.async_set_native_value(50)),
            {"bpBackupConfig": {"backupSocOnOff": True, "backupSoc": 50}},
        ),
        (
            "powerParameterConfig-feedToGridLimitOnOff",
            lambda e: e.turn_off(),
            {"powerParameterConfig": {"feedToGridLimitOnOff": False}},
        ),
        ("devSwitch-acSocketOnoff", lambda e: e.turn_on(), {"devSwitch": {"acSocketOnoff": True}}),
        ("workMode", lambda e: e.select_option("AI mode"), {"workMode": "AI_MODE"}),
    ],
)
def test_commands_use_the_documented_envelope(key, act, params):
    client = Client()
    device = make_device(client)
    device.data.params.update(HTTP_QUOTA)

    act(entity(device, client, key))

    _, sent = published(client)
    assert sent["params"] == params
    assert (sent["cmdId"], sent["cmdFunc"], sent["dirDest"], sent["dirSrc"], sent["dest"], sent["needAck"]) == (
        38,
        254,
        1,
        1,
        2,
        True,
    )
    assert sent["version"] == "1.0"


def test_system_commands_go_to_the_main_sn_and_the_socket_stays():
    client = Client(MAIN)
    device = make_device(client)
    device.data.params.update(HTTP_QUOTA)
    asyncio.run(client.async_refresh_main_sns())

    for key, act in (
        ("bpBackupConfig-backupSocOnOff", lambda e: e.turn_off()),
        ("bpBackupConfig-backupSoc", lambda e: asyncio.run(e.async_set_native_value(40))),
        ("powerParameterConfig-feedToGridLimitOnOff", lambda e: e.turn_on()),
        ("workMode", lambda e: e.select_option("Timer tasks")),
    ):
        act(entity(device, client, key))
        topic, sent = published(client)
        assert topic == f"/open/{ACCOUNT}/{MAIN}/set"
        assert sent["sn"] == MAIN

    entity(device, client, "devSwitch-acSocketOnoff").turn_off()
    topic, sent = published(client)
    assert topic == f"/open/{ACCOUNT}/{SN}/set"
    assert sent["sn"] == SN


def test_set_reply_cmd_ok():
    assert evaluate_set_reply({"data": {"workMode": "AI_MODE", "cmdOk": True, "actionId": 25}, "id": 123}) is None
    assert evaluate_set_reply({"data": {"workMode": "AI_MODE", "cmdOk": False}, "id": 123}) == "cmdOk is false"


def test_rejected_command_restores_the_hyphen_key():
    client = Client()
    device = make_device(client)
    device.data.params.update(HTTP_QUOTA)

    entity(device, client, "workMode").select_option("AI mode")
    assert device.data.params["workMode"] == "AI_MODE"
    entity(device, client, "powerParameterConfig-feedToGridLimitOnOff").turn_on()
    assert device.data.params["powerParameterConfig-feedToGridLimitOnOff"] is True

    _, sent = published(client)
    client.on_set_reply(json.dumps({"data": {"cmdOk": False}, "id": int(sent["id"])}).encode())

    assert device.data.params["powerParameterConfig-feedToGridLimitOnOff"] is False
    assert device.data.params["workMode"] == "AI_MODE"


def test_report_after_the_command_survives_a_rejection():
    client = Client()
    device = make_device(client)
    device.data.params.update(HTTP_QUOTA)

    entity(device, client, "devSwitch-acSocketOnoff").turn_off()
    _, sent = published(client)
    push(device, {"devSwitch": {"acSocketOnoff": False}})
    client.on_set_reply(json.dumps({"data": {"cmdOk": False}, "id": int(sent["id"])}).encode())

    assert device.data.params["devSwitch-acSocketOnoff"] is False


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"sn": SN, "online": 1, "productName": "STREAM 5000"}, "STREAM 5000"),
        ({"sn": SN, "online": 1, "productName": "Stream 5000 Series"}, "STREAM 5000"),
        ({"sn": SN, "online": 1}, "STREAM 5000"),
        ({"sn": "ES22ZE1B2J6H0060", "online": 1, "productName": "STREAM AC 5000"}, "STREAM AC 5000"),
        ({"sn": "BK11ZE1B2J6H0060", "online": 1, "productName": "Stream Ultra"}, "Stream Ultra"),
    ],
)
def test_device_list_maps_es21_and_only_es21(entry, expected):
    client = Client()
    client.responses["/device/list"] = {"code": "0", "message": "Success", "data": [entry]}

    found = asyncio.run(client.fetch_all_available_devices())

    assert found[0].device_type == expected
