"""Decode tests for the DELTA 3 family on the internal/App API."""

from types import SimpleNamespace

import pytest

from custom_components.ecoflow_cloud.devices.internal.delta3 import Delta3
from custom_components.ecoflow_cloud.devices.internal.proto import ef_delta3_pb2 as delta3_pb2

BMS_HEADER = {"cmdFunc": 32, "cmdId": 50}


def _bms_report(**fields) -> bytes:
    return delta3_pb2.Delta3BMSHeartBeatReport(**fields).SerializeToString()


def _decode(pdata: bytes, header: dict) -> dict:
    return Delta3._decode_message_by_type(Delta3.__new__(Delta3), pdata, header)


@pytest.mark.parametrize("header", [BMS_HEADER, {"cmdFunc": 99, "cmdId": 99}], ids=["bms", "fallback"])
def test_bms_report_of_the_built_in_battery_is_kept(header):
    result = _decode(_bms_report(num=0, soc=53, cycles=11, accu_chg_energy=12990), header)
    assert result["soc"] == 53
    assert result["accu_chg_energy"] == 12990


@pytest.mark.parametrize("header", [BMS_HEADER, {"cmdFunc": 99, "cmdId": 99}], ids=["bms", "fallback"])
def test_bms_report_of_an_extra_battery_is_dropped(header):
    # shuette42/ecoflow-energy-ha#304: pack 1 sent its own lifetime totals into the same keys
    assert _decode(_bms_report(num=1, soc=57, cycles=9, accu_chg_energy=11147), header) == {}


@pytest.mark.parametrize(
    ("device_type", "expected"),
    [("DELTA_3_MAX_PLUS", (200, 2400)), ("DELTA_3", (100, 1500))],
)
def test_ac_charging_power_range(device_type, expected):
    device = Delta3.__new__(Delta3)
    device.device_data = SimpleNamespace(device_type=device_type)
    assert device._ac_charging_power_range() == expected
