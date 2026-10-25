"""Decode tests for the STREAM AC 5000 (ES22) / STREAM 5000 (ES21) family.

Only the frame decoder runs here; no Home Assistant instance is started. The
fixtures are masked real-device captures from shuette42/ecoflow-energy-ha, see
fixtures/stream_ac5000/NOTICE.md. Expected values were read off the frames and
cross-checked against the EcoFlow app readings recorded in the fixture notes.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices import EcoflowDeviceInfo
from custom_components.ecoflow_cloud.devices.internal import stream_ac_5000
from custom_components.ecoflow_cloud.devices.internal.proto import stream_ac_5000_pb2
from custom_components.ecoflow_cloud.devices.internal.stream_ac_5000 import StreamAC5000
from custom_components.ecoflow_cloud.devices.registry import devices

FIXTURES = Path(__file__).parent / "fixtures" / "stream_ac5000"

# Single-unit captures carry the serial already masked to this run of X.
MASKED_SN = "X" * 16
PAIR_A = "ES21TESTUNITAAAA"
PAIR_B = "ES21TESTUNITBBBB"
ES22_LINKED = "ES22TESTUNITAAAA"

PV_KEYS = ("pvPower", "pv1Power", "pv2Power", "pv3Power", "pv4Power")
STRING_KEYS = PV_KEYS[1:]


def _device(sn: str, device_type: str = "STREAM_5000") -> StreamAC5000:
    options = DeviceOptions(
        refresh_period=5,
        power_step=-1,
        diagnostic_mode=False,
        verbose_status_mode=False,
        assume_offline_sec=300,
        reset_sensors_on_offline=False,
    )
    info = EcoflowDeviceInfo(
        public_api=False,
        sn=sn,
        name=sn,
        device_type=device_type,
        status=1,
        data_topic=f"/app/device/property/{sn}",
        set_topic=f"/app/0/{sn}/thing/property/set",
        set_reply_topic=f"/app/0/{sn}/thing/property/set_reply",
        get_topic=f"/app/0/{sn}/thing/property/get",
        get_reply_topic=f"/app/0/{sn}/thing/property/get_reply",
    )
    return StreamAC5000(info, DeviceData(sn, sn, device_type, options, None, None))


def _frames(name: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["frames"]


def _decode(device: StreamAC5000, frame: dict[str, Any]) -> dict[str, Any]:
    return device._prepare_data(bytes.fromhex(frame["hex"]))["params"]


def _at(name: str, stamp: str) -> dict[str, Any]:
    return next(frame for frame in _frames(name) if frame["ts_iso"].startswith(stamp))


def _strings(params: dict[str, Any]) -> list[float]:
    return [params[key] for key in STRING_KEYS]


class TestRegistry:
    def test_both_models_are_selectable(self) -> None:
        assert devices["STREAM_AC_5000"] is StreamAC5000
        assert devices["STREAM_5000"] is StreamAC5000

    def test_pv_entities_only_on_the_pv_model(self) -> None:
        client = SimpleNamespace()
        assert _device(MASKED_SN, "STREAM_AC_5000")._pv_sensors(client) == []  # type: ignore[arg-type]
        assert _device("ES22TESTUNITAAAA", "STREAM_AC_5000")._has_pv_inputs() is False
        assert _device(MASKED_SN, "STREAM_5000")._has_pv_inputs() is True
        # An ES21 configured under the older STREAM_AC_5000 type still gets PV.
        assert _device(PAIR_A, "STREAM_AC_5000")._has_pv_inputs() is True


class TestSingleES21:
    """One ES21 with PV wired (es21_pv_masked.json)."""

    def test_strings_match_the_app_reading(self) -> None:
        # The owner read 0 / 34 / 50 / 102 W in the app right after this frame.
        params = _decode(_device(MASKED_SN), _at("es21_pv_masked.json", "2026-08-16T07:21:30"))
        assert params["pvPower"] == pytest.approx(195.91, abs=0.01)
        assert _strings(params) == pytest.approx([0.0, 36.57, 55.32, 104.02], abs=0.01)

    def test_string_sum_equals_total(self) -> None:
        device = _device(MASKED_SN)
        checked = 0
        for frame in _frames("es21_pv_masked.json"):
            params = _decode(device, frame)
            if params.get("pvPower"):
                assert sum(_strings(params)) == pytest.approx(params["pvPower"], abs=0.01), frame["ts_iso"]
                checked += 1
        assert checked >= 7

    @pytest.mark.parametrize("stamp", ["2026-08-15T22:15:26", "2026-08-16T00:27:49"])
    def test_night_reads_zero(self, stamp: str) -> None:
        params = _decode(_device(MASKED_SN), _at("es21_pv_masked.json", stamp))
        for key in PV_KEYS:
            assert params[key] == 0.0, key

    def test_battery_net_power_is_pv_minus_ac_grid(self) -> None:
        """Field .4 is the signed battery power, not the grid port.

        At 07:21:30 the strings deliver 195.91 W while 79 W are drawn from the
        grid, and the battery takes both.
        """
        params = _decode(_device(MASKED_SN), _at("es21_pv_masked.json", "2026-08-16T07:21:30"))
        assert params["batteryNetPower"] == pytest.approx(274.91, abs=0.01)
        assert params["acGridPower"] == pytest.approx(-79.0, abs=0.01)

        device = _device(MASKED_SN)
        for frame in _frames("es21_pv_masked.json"):
            params = _decode(device, frame)
            if "batteryNetPower" in params:
                assert params["batteryNetPower"] == pytest.approx(
                    params["pvPower"] - params["acGridPower"], abs=0.05
                ), frame["ts_iso"]

    def test_evening_frame_without_pv(self) -> None:
        params = _decode(_device(MASKED_SN), _at("es21_frames_masked.json", "2026-08-09T17:32:53"))
        assert params["batteryNetPower"] == pytest.approx(-625.55, abs=0.01)
        assert params["acGridPower"] == pytest.approx(625.55, abs=0.01)
        for key in PV_KEYS:
            assert params[key] == 0.0, key


class TestLinkedES21Pair:
    """Two linked ES21; the master's frames carry both units' entries."""

    def test_each_unit_gets_its_own_strings(self) -> None:
        frame = _frames("es21_pair_pv_masked.json")[0]

        own = _decode(_device(PAIR_A), frame)
        assert own["pvPower"] == pytest.approx(1480.33, abs=0.01)
        assert _strings(own) == pytest.approx([232.52, 475.74, 482.09, 289.99], abs=0.01)

        other = _decode(_device(PAIR_B), frame)
        assert other["pvPower"] == pytest.approx(1366.0)
        assert _strings(other) == pytest.approx([337.0, 129.0, 233.0, 666.0])

    def test_each_unit_gets_its_own_soc(self) -> None:
        frame = _frames("es21_pair_pv_masked.json")[2]
        assert _decode(_device(PAIR_A), frame)["soc"] == 49
        assert _decode(_device(PAIR_B), frame)["soc"] == 48

    def test_string_sum_equals_total_per_unit(self) -> None:
        # The neighbour's entry is relayed in whole watts and its total is the
        # unrounded sum, hence the wider tolerance for that unit.
        checked = 0
        for frame in _frames("es21_pair_pv_masked.json") + _frames("es21_pair_pv_both_connections_masked.json"):
            owner = PAIR_A if frame["connection"] == "unit_a" else PAIR_B
            for sn in (PAIR_A, PAIR_B):
                params = _decode(_device(sn), frame)
                if params.get("pvPower") and all(key in params for key in STRING_KEYS):
                    tolerance = 0.01 if sn == owner else 2.5
                    assert sum(_strings(params)) == pytest.approx(params["pvPower"], abs=tolerance)
                    checked += 1
        assert checked >= 20

    def test_relayed_entry_missing_a_live_string_is_not_zero_filled(self) -> None:
        """Frame 17 relays unit A with 72 + 71 + 74 W against a 239 W total.

        The fourth string was producing about 22 W and simply left out, so it
        must keep its previous reading instead of dropping to 0 W.
        """
        frame = _frames("es21_pair_pv_both_connections_masked.json")[17]
        params = _decode(_device(PAIR_A), frame)
        assert params["pvPower"] == pytest.approx(239.0)
        assert [params[key] for key in STRING_KEYS[:3]] == pytest.approx([72.0, 71.0, 74.0])
        assert "pv4Power" not in params

        own = _decode(_device(PAIR_B), frame)
        assert sum(_strings(own)) == pytest.approx(own["pvPower"], abs=0.01)

    @pytest.mark.parametrize("index", [0, 1, 4])
    def test_night_reads_zero_on_both_units(self, index: int) -> None:
        frame = _frames("es21_pair_pv_both_connections_masked.json")[index]
        for sn in (PAIR_A, PAIR_B):
            params = _decode(_device(sn), frame)
            for key in PV_KEYS:
                assert params[key] == 0.0, (sn, key)

    def test_empty_block_publishes_nothing(self) -> None:
        # Unit B's own connection sent blocks 50 and 54 without entries.
        params = _decode(_device(PAIR_B), _frames("es21_pair_pv_masked.json")[3])
        for key in (*PV_KEYS, "batteryNetPower", "acGridPower", "soc"):
            assert key not in params, key

    def test_foreign_serial_publishes_nothing(self) -> None:
        params = _decode(_device("ES21TESTUNITCCCC"), _frames("es21_pair_pv_masked.json")[0])
        for key in (*PV_KEYS, "batteryNetPower", "acGridPower", "soc"):
            assert key not in params, key


class TestES22WithoutPV:
    """STREAM AC 5000 units: no MPPT, so no PV value may ever appear."""

    @pytest.mark.parametrize("name", ["es22_push_capture_masked.json", "es22_get_reply_masked.json"])
    def test_no_pv_values(self, name: str) -> None:
        device = _device(MASKED_SN, "STREAM_AC_5000")
        decoded = 0
        for frame in _frames(name):
            params = _decode(device, frame)
            for key in PV_KEYS:
                assert key not in params, (frame["ts_iso"], key)
            decoded += "batteryNetPower" in params
        assert decoded >= 1

    def test_battery_and_grid_power(self) -> None:
        # Discharging 535 W into the house, as the app showed at the time.
        params = _decode(_device(MASKED_SN, "STREAM_AC_5000"), _frames("es22_get_reply_masked.json")[0])
        assert params["batteryNetPower"] == pytest.approx(-535.23, abs=0.01)
        assert params["acGridPower"] == pytest.approx(535.23, abs=0.01)

    def test_linked_pv_unit_does_not_leak_into_the_es22(self) -> None:
        """An ES22 linked to a Stream Ultra that carries the PV.

        Decoding block 50 as one merged message used to hand the ES22 the
        Ultra's power; its own entry carries nothing but serial and SoC.
        """
        device = _device(ES22_LINKED, "STREAM_AC_5000")
        decoded = 0
        for frame in _frames("es22_ultra_pv_pair_masked.json"):
            params = _decode(device, frame)
            for key in PV_KEYS:
                assert key not in params, (frame["ts"], key)
            if "batteryNetPower" in params:
                assert params["batteryNetPower"] == 0.0, frame["ts"]
                assert params["acGridPower"] == 0.0, frame["ts"]
                decoded += 1
            if "soc" in params:
                assert params["soc"] == 20, frame["ts"]
        assert decoded >= 5


class TestPvValues:
    """The zero-fill rule on synthetic entries."""

    @staticmethod
    def _entry(**fields: float) -> Any:
        return stream_ac_5000_pb2.StreamAC5000DevicePower(sn=PAIR_A, **fields)

    def test_idle_string_reads_zero_when_total_agrees(self) -> None:
        values = stream_ac_5000._pv_values(self._entry(pvPower=100.0, pv2Power=60.0, pv3Power=40.0))
        assert values == {"pvPower": 100.0, "pv1Power": 0.0, "pv2Power": 60.0, "pv3Power": 40.0, "pv4Power": 0.0}

    def test_absent_strings_stay_out_when_total_disagrees(self) -> None:
        values = stream_ac_5000._pv_values(self._entry(pvPower=100.0, pv2Power=60.0))
        assert values == {"pvPower": 100.0, "pv2Power": 60.0}

    def test_strings_without_total_are_not_filled(self) -> None:
        assert stream_ac_5000._pv_values(self._entry(pv1Power=10.0)) == {"pv1Power": 10.0}

    def test_empty_entry_is_night(self) -> None:
        assert stream_ac_5000._pv_values(self._entry()) == dict.fromkeys(PV_KEYS, 0.0)
