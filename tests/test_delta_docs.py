"""Entity and command checks for the DELTA review fixes (docs/review/delta-docs.md).

Only entity construction and command building run here; no Home Assistant
instance is started and nothing is sent.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices import EcoflowDeviceInfo
from custom_components.ecoflow_cloud.devices.internal.delta2_max import Delta2Max
from custom_components.ecoflow_cloud.devices.internal.delta_pro_3 import DeltaPro3 as InternalDeltaPro3
from custom_components.ecoflow_cloud.devices.public.delta_pro import DeltaPro as PublicDeltaPro
from custom_components.ecoflow_cloud.devices.public.delta_pro_3 import DeltaPro3 as PublicDeltaPro3

SN = "X" * 16


def _device(cls: type, device_type: str, public_api: bool) -> Any:
    options = DeviceOptions(
        refresh_period=5,
        power_step=-1,
        diagnostic_mode=False,
        verbose_status_mode=False,
        assume_offline_sec=300,
        reset_sensors_on_offline=False,
    )
    info = EcoflowDeviceInfo(
        public_api=public_api,
        sn=SN,
        name=SN,
        device_type=device_type,
        status=1,
        data_topic=f"/open/x/{SN}/quota",
        set_topic=f"/open/x/{SN}/set",
        set_reply_topic=f"/open/x/{SN}/set_reply",
        get_topic=f"/open/x/{SN}/get",
        get_reply_topic=f"/open/x/{SN}/get_reply",
    )
    device = cls(info, DeviceData(SN, SN, device_type, options, None, None))
    # Entities only store the coordinator; nothing is polled here.
    device.coordinator = SimpleNamespace()
    return device


def _by_key(entities: list[Any]) -> dict[str, Any]:
    return {e._EcoFlowDictEntity__mqtt_key: e for e in entities if hasattr(e, "_EcoFlowDictEntity__mqtt_key")}


CLIENT = SimpleNamespace()


class TestDelta2MaxTimeouts:
    """api-docs/delta_2_max.md PD / INV / MPPT standbyTime; tolwi#324."""

    @pytest.fixture
    def selects(self) -> dict[str, Any]:
        return _by_key(_device(Delta2Max, "DELTA_2_MAX", False).selects(CLIENT))

    @pytest.mark.parametrize(
        ("key", "title", "module_type"),
        [
            ("pd.standbyMin", "Unit Timeout", 1),
            ("inv.standbyMin", "AC Timeout", 3),
            ("mppt.carStandbyMin", "DC (12V) Timeout", 5),
        ],
    )
    def test_each_timeout_writes_the_module_it_reads(
        self, selects: dict[str, Any], key: str, title: str, module_type: int
    ) -> None:
        entity = selects[key]
        assert entity.title() == title
        command = entity.command_dict(120)
        assert command["moduleType"] == module_type
        assert command["operateType"] == "standbyTime"
        assert command["params"] == {"standbyMin": 120}


class TestDelta2MaxXboost:
    """api-docs/delta_2_max.md INV acOutCfg; tolwi#900."""

    def test_xboost_sends_the_full_ac_out_cfg(self) -> None:
        switches = _by_key(_device(Delta2Max, "DELTA_2_MAX", False).switches(CLIENT))
        command = switches["inv.cfgAcXboost"].command_dict(1)
        assert command["moduleType"] == 3
        assert command["operateType"] == "acOutCfg"
        assert command["params"] == {"enabled": 255, "out_voltage": 4294967295, "out_freq": 255, "xboost": 1}


class TestPublicDeltaPro:
    def test_car_out_power_is_read_in_tenths_of_a_watt(self) -> None:
        """tolwi#455: the app shows 6 W while the field reports 60."""
        sensors = _by_key(_device(PublicDeltaPro, "DELTA Pro", True).sensors(CLIENT))
        entity = sensors["mppt.carOutWatts"]
        entity._update_value(60)
        assert entity._attr_native_value == 6


class TestPublicDeltaPro3:
    """api-docs/delta_pro_3.md set commands and GetAllQuotaResponse."""

    @pytest.fixture
    def device(self) -> Any:
        return _device(PublicDeltaPro3, "Delta Pro 3", True)

    def test_beeper_is_not_inverted(self, device: Any) -> None:
        beeper = _by_key(device.switches(CLIENT))["enBeep"]
        beeper._update_value(True)
        assert beeper.is_on is True
        beeper._update_value(False)
        assert beeper.is_on is False
        assert beeper._enable_value == 1
        assert beeper.command_dict(beeper._enable_value)["params"] == {"cfgBeepEn": 1}

    @pytest.mark.parametrize(("raw", "text"), [(0, "idle"), (1, "discharging"), (2, "charging")])
    def test_charge_state_follows_the_doc_enum(self, device: Any, raw: int, text: str) -> None:
        entity = _by_key(device.sensors(CLIENT))["cmsChgDsgState"]
        entity._update_value(raw)
        assert entity._attr_native_value == text

    def test_ac_input_frequency_is_in_hertz(self, device: Any) -> None:
        entity = _by_key(device.sensors(CLIENT))["plugInInfoAcInFeq"]
        assert entity.native_unit_of_measurement == "Hz"


class TestInternalDeltaPro3:
    @pytest.mark.parametrize("key", ["pow_get_12v", "pow_get_24v", "pow_get_5p8", "pow_get_4p8_1", "pow_get_4p8_2"])
    def test_dc_port_power_is_in_watts(self, key: str) -> None:
        """api-docs/delta_pro_3.md: powGet12v ... are float W; port of tolwi#944."""
        entity = _by_key(_device(InternalDeltaPro3, "DELTA_PRO_3", False).sensors(CLIENT))[key]
        entity._update_value(42.5)
        assert entity._attr_native_value == 42.5
