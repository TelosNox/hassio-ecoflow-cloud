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
