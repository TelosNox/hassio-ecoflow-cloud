"""Decode tests for the Smart Meter (BK21) on the internal/App API.

The frame is a masked get_reply from a real BK21, copied from
shuette42/ecoflow-energy-ha (MIT), tests/fixtures/smart_meter/bk21_midnight_issue331.json
at commit 6830cd3649c1a4f3603d9379157fba5ee88e1f63, see tests/fixtures/stream_ac5000/NOTICE.md
for the licence. Phase A was idle on that installation.
"""

from types import SimpleNamespace

import pytest

from custom_components.ecoflow_cloud.devices.internal.smart_meter import SmartMeter

GET_REPLY_HEX = (
    "0a220a13a812c0a907b012d00fb812e0a712c012e0d403100240fe01481670828ad6c5060aac010a9c01a808c801b208"
    "0d4575726f70652f585858585858b808019d20cb9cb943d52600000000d826019a2700c22d00c82d00e02d00e82d00d0"
    "2f01d82f01e02f019d30211e7643a530d1939043aa301e0d000040401500a826461d00287b46250026d146350000e041"
    "3d00eed046853189d3e13fe53bacfa7543ed3bb3ce7343f53b00000000fd3b5c01383f953c000000009d3c4485a242c0"
    "3d8280c9ac02100240fe01481570828ad6c506"
)


def _params() -> dict:
    meter = SmartMeter.__new__(SmartMeter)
    meter.device_data = SimpleNamespace(sn="BK21TESTUNITAAAA")
    return SmartMeter._prepare_data(meter, bytes.fromhex(GET_REPLY_HEX))["params"]


def test_phase_currents_follow_their_phase_power():
    params = _params()
    # The idle phase carries no current; 784 used to land on L1 and showed
    # phase C's current next to 0 W (shuette42/ecoflow-energy-ha#331).
    assert params["254_21.powerL1"] == 0.0
    assert params["254_21.currentL1"] == 0.0
    assert params["254_21.powerL2"] == pytest.approx(81.26, abs=0.01)
    assert params["254_21.currentL2"] == pytest.approx(0.719, abs=0.001)
    assert params["254_21.powerL3"] == pytest.approx(289.155, abs=0.01)
    assert params["254_21.currentL3"] == pytest.approx(1.764, abs=0.001)
