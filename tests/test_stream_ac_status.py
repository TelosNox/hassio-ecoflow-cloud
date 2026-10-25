"""The app-API STREAM must carry a status sensor that reconnects on a stall.

Without it nothing noticed the cloud-side stall on the app API either
(tolwi/hassio-ecoflow-cloud#908, #830).
"""

from types import SimpleNamespace

import pytest

from custom_components.ecoflow_cloud.device_data import DeviceData, DeviceOptions
from custom_components.ecoflow_cloud.devices import EcoflowDeviceInfo
from custom_components.ecoflow_cloud.devices.internal.stream_ac import StreamAC
from custom_components.ecoflow_cloud.sensor import StatusSensorEntity

SN = "BK11TESTUNITAAAA"


def _device(device_type: str) -> StreamAC:
    options = DeviceOptions(
        refresh_period=5,
        power_step=-1,
        diagnostic_mode=False,
        verbose_status_mode=False,
        assume_offline_sec=300,
        reset_sensors_on_offline=True,
    )
    info = EcoflowDeviceInfo(
        public_api=False,
        sn=SN,
        name=SN,
        device_type=device_type,
        status=1,
        data_topic=f"/app/device/property/{SN}",
        set_topic=f"/app/0/{SN}/thing/property/set",
        set_reply_topic=f"/app/0/{SN}/thing/property/set_reply",
        get_topic=f"/app/0/{SN}/thing/property/get",
        get_reply_topic=f"/app/0/{SN}/thing/property/get_reply",
    )
    device = StreamAC(info, DeviceData(SN, SN, device_type, options, None, None))
    device.coordinator = SimpleNamespace()  # type: ignore[assignment]
    return device


@pytest.mark.parametrize("device_type", ["STREAM_AC", "STREAM_PRO", "STREAM_ULTRA", "STREAM_ULTRA_X"])
def test_status_sensor_reconnects_when_stale(device_type: str) -> None:
    sensors = _device(device_type).sensors(SimpleNamespace())  # type: ignore[arg-type]

    status = [s for s in sensors if isinstance(s, StatusSensorEntity)]
    assert len(status) == 1
    assert status[0]._reconnect_when_stale
    assert status[0].unique_id == f"ecoflow-{SN}-status"
