from __future__ import annotations  # for DeviceData.parent: DeviceData

import dataclasses


@dataclasses.dataclass
class DeviceOptions:
    refresh_period: int
    power_step: int
    diagnostic_mode: bool
    verbose_status_mode: bool
    assume_offline_sec: int
    reset_sensors_on_offline: bool
    # STREAM: how far back the first statistics import of the system history reaches
    history_backfill_days: int = 90


@dataclasses.dataclass
class DeviceData:
    sn: str
    name: str
    device_type: str
    options: DeviceOptions
    display_name: str | None
    parent: DeviceData | None
