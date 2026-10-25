"""STREAM system commands go to the system's main SN.

Reference: stream.md, "Obtain the main device serial number of the STREAM
system" (GET /iot-open/sign/device/system/main/sn?sn=..., data.sn) and the
note on every system command: "If there are multiple devices, use the API to
obtain the serial number of the main device"; AC1/AC2 take the unit's own SN.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from custom_components.ecoflow_cloud.api import EcoflowMqttInfo
from custom_components.ecoflow_cloud.api.commands import (
    MAIN_SN_RETRY_SEC,
    MAIN_SN_TTL_SEC,
    MainSnCache,
    stream_command_target_sn,
)
from custom_components.ecoflow_cloud.api.public_api import EcoflowPublicApiClient
from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices.public.stream_ac import StreamAC

SLAVE = "BK61SLAVEUNIT001"
MASTER = "BK31MASTERUNIT01"
ACCOUNT = "open-account"


class FakeMqtt:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.topics: list[str] = []
        self.connected = True

    def publish(self, topic: str, payload) -> None:
        self.published.append((topic, json.loads(payload)))

    def add_topic(self, topic: str) -> None:
        self.topics.append(topic)

    def is_connected(self) -> bool:
        return self.connected


class FakeClient(EcoflowPublicApiClient):
    def __init__(self, main_sn: str | None) -> None:
        super().__init__("api-e.ecoflow.com", "ak", "sk", "Home")
        self.mqtt_info = EcoflowMqttInfo("mqtt-e.ecoflow.com", 8883, ACCOUNT, "pw", "cid")
        self.mqtt_client = FakeMqtt()  # type: ignore[assignment]
        self.main_sn = main_sn
        self.lookups: list[dict[str, str] | None] = []

    async def call_api(self, endpoint: str, params: dict[str, str] | None = None) -> dict:
        assert endpoint == "/device/system/main/sn"
        self.lookups.append(params)
        if self.main_sn is None:
            raise RuntimeError("server busy")
        return {"code": "0", "message": "Success", "data": {"sn": self.main_sn}}


def _stream(client: FakeClient, sn: str = SLAVE) -> StreamAC:
    options = DeviceOptions(5, -1, False, False, 300, True)
    info = client._create_device_info(sn, sn, "Stream Ultra X", 1)
    device = StreamAC(info, DeviceData(sn, sn, "Stream Ultra X", options, None, None))
    device.coordinator = SimpleNamespace()  # type: ignore[assignment]
    client.add_device(device)
    return device


def _command(device: StreamAC, client: FakeClient, key: str) -> Any:
    entities = [*device.switches(client), *device.numbers(client)]  # type: ignore[arg-type]
    return next(e for e in entities if e.mqtt_key == key)


def test_target_sn_for_documented_system_commands():
    for params in (
        {"cfgBackupReverseSoc": 10},
        {"cfgEnergyStrategyOperateMode": {"operateSelfPoweredOpen": True}},
        {"cfgFeedGridMode": 2},
    ):
        assert stream_command_target_sn({"params": params}, SLAVE, MASTER) == MASTER


def test_target_sn_for_unit_and_unknown_commands():
    for params in ({"cfgRelay2Onoff": True}, {"cfgRelay3Onoff": False}, {"cfgSomethingNew": 1}, {}):
        assert stream_command_target_sn({"params": params}, SLAVE, MASTER) == SLAVE
    # a mixed command is not a pure system command
    assert stream_command_target_sn({"params": {"cfgFeedGridMode": 2, "cfgRelay2Onoff": True}}, SLAVE, MASTER) == SLAVE


def test_cache_falls_back_to_own_sn_and_keeps_last_known():
    now = [0.0]
    cache = MainSnCache(SLAVE, clock=lambda: now[0])
    assert cache.sn == SLAVE and cache.due()

    assert cache.begin_refresh()
    assert not cache.begin_refresh()  # one lookup at a time
    cache.accept(None)
    assert cache.sn == SLAVE and not cache.due()
    now[0] += MAIN_SN_RETRY_SEC
    assert cache.due()

    cache.begin_refresh()
    assert cache.accept(MASTER)
    assert cache.sn == MASTER
    now[0] += MAIN_SN_TTL_SEC - 1
    assert not cache.due()

    # a failed refresh keeps the last known main SN
    now[0] += 1
    cache.begin_refresh()
    cache.accept(None)
    assert cache.sn == MASTER

    cache.invalidate()
    assert cache.due()


def test_slave_sends_system_commands_to_main_sn():
    client = FakeClient(MASTER)
    device = _stream(client)
    device.data.params["feedGridMode"] = 1
    asyncio.run(client.async_refresh_main_sns())
    assert client.lookups == [{"sn": SLAVE}]
    # the reply to a routed command arrives on the main unit's topic
    assert client.mqtt_client.topics == [f"/open/{ACCOUNT}/{MASTER}/set_reply"]  # type: ignore[attr-defined]

    _command(device, client, "feedGridMode").turn_on()
    asyncio.run(_command(device, client, "backupReverseSoc").async_set_native_value(20))
    _command(device, client, "energyStrategyOperateMode.operateSelfPoweredOpen").turn_on()
    _command(device, client, "relay2Onoff").turn_on()

    sent = client.mqtt_client.published  # type: ignore[attr-defined]
    assert [(topic, payload["sn"]) for topic, payload in sent] == [
        (f"/open/{ACCOUNT}/{MASTER}/set", MASTER),
        (f"/open/{ACCOUNT}/{MASTER}/set", MASTER),
        (f"/open/{ACCOUNT}/{MASTER}/set", MASTER),
        (f"/open/{ACCOUNT}/{SLAVE}/set", SLAVE),
    ]
    # the optimistic state stays on the unit whose entity sent it
    assert device.data.params["feedGridMode"] == 2


def test_master_and_unresolved_units_use_their_own_sn():
    for main_sn, sn in ((MASTER, MASTER), (None, SLAVE)):
        client = FakeClient(main_sn)
        device = _stream(client, sn)
        asyncio.run(client.async_refresh_main_sns())
        assert client.mqtt_client.topics == []  # type: ignore[attr-defined]

        _command(device, client, "feedGridMode").turn_off()

        assert client.mqtt_client.published == [  # type: ignore[attr-defined]
            (f"/open/{ACCOUNT}/{sn}/set", client.mqtt_client.published[0][1])  # type: ignore[attr-defined]
        ]
        assert client.mqtt_client.published[0][1]["sn"] == sn  # type: ignore[attr-defined]
