"""EcoflowMQTTClient behaviour that does not need a broker.

paho's connect() and network loop are replaced, everything else is the real
paho client.
"""

import threading

import pytest
from paho.mqtt.client import Client

from custom_components.ecoflow_cloud.api import EcoflowMqttInfo
from custom_components.ecoflow_cloud.api.ecoflow_mqtt import EcoflowMQTTClient


@pytest.fixture
def offline_paho(monkeypatch):
    calls: dict[str, int] = {"connect": 0, "loop_start": 0}

    def connect(self, *args, **kwargs):
        calls["connect"] += 1
        return 0

    def loop_start(self):
        calls["loop_start"] += 1
        return 0

    monkeypatch.setattr(Client, "connect", connect)
    monkeypatch.setattr(Client, "loop_start", loop_start)
    return calls


def _client() -> EcoflowMQTTClient:
    return EcoflowMQTTClient(EcoflowMqttInfo("mqtt-e.ecoflow.com", 8883, "user", "pw", "cid"), {})


def test_paho_keeps_its_locks(offline_paho):
    # paho runs its own network thread (loop_start) while commands are
    # published from the event loop and executor threads; HA's AsyncMQTTClient
    # replaces these locks with no-ops
    paho = _client()._EcoflowMQTTClient__client  # type: ignore[attr-defined]

    assert isinstance(paho._out_message_mutex, type(threading.RLock()))
    assert isinstance(paho._callback_mutex, type(threading.RLock()))


def _connack(client: EcoflowMQTTClient) -> None:
    from paho.mqtt.packettypes import PacketTypes
    from paho.mqtt.reasoncodes import ReasonCode

    client._on_connect(None, None, None, ReasonCode(PacketTypes.CONNACK, "Success"))  # type: ignore[arg-type]


def test_stale_unacknowledged_command_is_not_resent(offline_paho, monkeypatch):
    from custom_components.ecoflow_cloud.api import ecoflow_mqtt

    now = [1000.0]
    monkeypatch.setattr(ecoflow_mqtt.time, "monotonic", lambda: now[0])
    client = _client()
    paho = client._EcoflowMQTTClient__client  # type: ignore[attr-defined]

    # not connected: paho keeps both for the next connect
    client.publish("/open/user/BK11OLD/set", b'{"old": 1}')
    now[0] += ecoflow_mqtt.STALE_COMMAND_SEC
    client.publish("/open/user/BK11NEW/set", b'{"new": 1}')
    assert len(paho._out_messages) == 2

    _connack(client)

    assert [m.payload for m in paho._out_messages.values()] == [b'{"new": 1}']


def test_acknowledged_message_is_forgotten(offline_paho):
    client = _client()
    paho = client._EcoflowMQTTClient__client  # type: ignore[attr-defined]
    client.publish("/open/user/BK11/set", b"{}")
    mid = next(iter(paho._out_messages))

    client._on_publish(None, None, mid, None, None)  # type: ignore[arg-type]

    assert client._EcoflowMQTTClient__unacked == {}  # type: ignore[attr-defined]
