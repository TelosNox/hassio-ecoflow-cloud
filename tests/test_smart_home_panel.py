"""Smart Home Panel (1) commands from api-docs/smart_home_panel.md."""

from types import SimpleNamespace

from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices import EcoflowDeviceInfo, const
from custom_components.ecoflow_cloud.devices.public.smart_home_panel import SmartHomePanel

SN = "SP10TESTUNIT0001"


def _device() -> SmartHomePanel:
    options = DeviceOptions(
        refresh_period=5,
        power_step=-1,
        diagnostic_mode=False,
        verbose_status_mode=False,
        assume_offline_sec=300,
        reset_sensors_on_offline=False,
    )
    info = EcoflowDeviceInfo(
        public_api=True,
        sn=SN,
        name=SN,
        device_type="Smart Home Panel",
        status=1,
        data_topic=f"/open/test/{SN}/quota",
        set_topic=f"/open/test/{SN}/set",
        set_reply_topic=f"/open/test/{SN}/set_reply",
        get_topic=f"/open/test/{SN}/get",
        get_reply_topic=f"/open/test/{SN}/get_reply",
    )
    device = SmartHomePanel(info, DeviceData(SN, SN, "Smart Home Panel", options, None, None))
    device.coordinator = None  # type: ignore[assignment]  # entities only store it
    return device


def test_setting_the_discharge_limit_keeps_the_reported_charge_limit() -> None:
    device = _device()
    # Keys as returned by quota for "Pushing standby charging/discharging parameters".
    device.data.params.update({"backupChaDiscCfg.forceChargeHigh": 90, "backupChaDiscCfg.discLower": 10})
    numbers = {n._attr_name: n for n in device.numbers(SimpleNamespace())}  # type: ignore[arg-type]

    command = numbers[const.MIN_DISCHARGE_LEVEL].command_dict(20)
    assert command["params"] == {"cmdSet": 11, "id": 29, "discLower": 20, "forceChargeHigh": 90}

    command = numbers[const.MAX_CHARGE_LEVEL].command_dict(80)
    assert command["params"] == {"cmdSet": 11, "id": 29, "forceChargeHigh": 80, "discLower": 10}
