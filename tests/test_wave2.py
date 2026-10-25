"""WAVE 2 entity keys checked against api-docs/wave_air_conditioner.md (GetAllQuotaResponse)."""

from types import SimpleNamespace

from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices import EcoflowDeviceInfo
from custom_components.ecoflow_cloud.devices.public.wave2 import Wave2

SN = "KT21TESTUNIT0001"


def _device() -> Wave2:
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
        device_type="WAVE 2",
        status=1,
        data_topic=f"/open/test/{SN}/quota",
        set_topic=f"/open/test/{SN}/set",
        set_reply_topic=f"/open/test/{SN}/set_reply",
        get_topic=f"/open/test/{SN}/get",
        get_reply_topic=f"/open/test/{SN}/get_reply",
    )
    device = Wave2(info, DeviceData(SN, SN, "WAVE 2", options, None, None))
    device.coordinator = None  # type: ignore[assignment]  # entities only store it
    return device


def _sensors_by_uid() -> dict:
    return {e._attr_unique_id: e for e in _device().sensors(SimpleNamespace())}  # type: ignore[arg-type]


def test_mistyped_keys_read_the_documented_field_but_keep_their_unique_id() -> None:
    sensors = _sensors_by_uid()
    for legacy_uid_suffix, documented_key in (
        ("pd-psdrPower ", "pd.psdrPower"),
        ("pd-batPower ", "pd.batPower"),
        ("power-acPwrI", "power.acPwrIn"),
        ("power-mpptPwr ", "power.mpptPwr"),
    ):
        entity = sensors[f"ecoflow-api-{SN}-{legacy_uid_suffix}"]
        assert entity.mqtt_key == documented_key
        assert [m.value for m in entity._mqtt_key_expr.find({documented_key: 42})] == [42]
