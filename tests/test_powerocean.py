"""PowerOcean quota/all fields from api-docs/power_ocean.md (GetAllQuotaResponse)."""

from types import SimpleNamespace

from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices import EcoflowDeviceInfo
from custom_components.ecoflow_cloud.devices.public.powerocean import PowerOcean

SN = "HJ31TESTUNIT0001"
OPTIONAL_KEYS = ("mpptPwr", "evPwr", "chargingStatus")


def _enabled_by_key(params: dict) -> dict[str, bool]:
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
        device_type="Power Ocean",
        status=1,
        data_topic=f"/open/test/{SN}/quota",
        set_topic=f"/open/test/{SN}/set",
        set_reply_topic=f"/open/test/{SN}/set_reply",
        get_topic=f"/open/test/{SN}/get",
        get_reply_topic=f"/open/test/{SN}/get_reply",
    )
    device = PowerOcean(info, DeviceData(SN, SN, "Power Ocean", options, None, None))
    device.coordinator = None  # type: ignore[assignment]  # entities only store it
    device.data.params.update(params)
    return {
        e.mqtt_key: e.enabled_default
        for e in device.sensors(SimpleNamespace())  # type: ignore[arg-type]
        if getattr(e, "mqtt_key", None) in OPTIONAL_KEYS
    }


def test_ev_charger_fields_enable_only_when_reported() -> None:
    assert _enabled_by_key({}) == dict.fromkeys(OPTIONAL_KEYS, False)
    reported = _enabled_by_key({"mpptPwr": 0, "evPwr": 0, "chargingStatus": "EV_CHG_STS_AVAILABLE"})
    assert reported == dict.fromkeys(OPTIONAL_KEYS, True)
