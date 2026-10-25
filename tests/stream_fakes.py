"""Fakes for tests that send STREAM commands without hass or a broker."""

import json
from types import SimpleNamespace
from typing import Any

from custom_components.ecoflow_cloud.api import EcoflowMqttInfo
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


def make_stream(client: FakeClient, sn: str = SLAVE) -> StreamAC:
    options = DeviceOptions(5, -1, False, False, 300, True)
    info = client._create_device_info(sn, sn, "Stream Ultra X", 1)
    device = StreamAC(info, DeviceData(sn, sn, "Stream Ultra X", options, None, None))
    device.coordinator = SimpleNamespace()  # type: ignore[assignment]
    client.add_device(device)
    return device


def find_entity(device: StreamAC, client: FakeClient, key: str) -> Any:
    entities = [*device.switches(client), *device.numbers(client)]  # type: ignore[arg-type]
    return next(e for e in entities if e.mqtt_key == key)
