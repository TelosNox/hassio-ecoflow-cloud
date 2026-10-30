"""STREAM 5000 (SN prefix ES21) and STREAM 5000 AC (ES22) on the public developer API.

Implemented from EcoFlow's "STREAM 5000 Series" document (published 2026-10-29).
It exposes 11 system-level fields; the private-API device in
devices/internal/stream_ac_5000.py has far more data and is unrelated to this one.
Cross-checked against MichelFR/ha-ecoflow-iot v0.51.0 (MIT).
"""

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import ServiceValidationError

from custom_components.ecoflow_cloud.api import EcoflowApiClient
from custom_components.ecoflow_cloud.api.commands import MainSnCache, stream_command_target_sn
from custom_components.ecoflow_cloud.api.message import JSONMessage, Message
from custom_components.ecoflow_cloud.device_data import DeviceData
from custom_components.ecoflow_cloud.devices import BaseDevice, EcoflowDeviceInfo, const
from custom_components.ecoflow_cloud.number import LevelEntity
from custom_components.ecoflow_cloud.select import DictSelectEntity
from custom_components.ecoflow_cloud.sensor import (
    LevelSensorEntity,
    StatusSensorEntity,
    WattsSensorEntity,
)
from custom_components.ecoflow_cloud.switch import EnabledEntity


def flatten_quota(payload: dict[str, Any]) -> dict[str, Any]:
    """Put an MQTT message on the documented HTTP key: {"a": {"b": 1}} becomes {"a-b": 1}.

    HTTP data needs no such step: quota_all() stores the response as it is, and
    GetAllQuotaResponse already uses the hyphen-flattened names.
    """
    body = {k: v for k, v in payload.items() if k not in ("param", "params")}
    for envelope in ("param", "params"):
        if isinstance(payload.get(envelope), dict):
            body.update(payload[envelope])

    flat: dict[str, Any] = {}

    def add(key: str, value: Any) -> None:
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                add(f"{key}-{sub_key}", sub_value)
        else:
            flat[key] = value

    for key, value in body.items():
        add(key, value)
    return flat


class WorkModeSelectEntity(DictSelectEntity):
    """Shows every documented mode but cannot start a read-only one.

    HA only displays a current option that is in the list, so a read-only mode
    is listed while the device is in it, and refused if selected.
    """

    def options_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self._options_dict.items() if k not in const.STREAM_5000_WORK_MODE_READ_ONLY}

    @property
    def options(self) -> list[str]:
        return [
            option
            for option in self._options
            if option not in const.STREAM_5000_WORK_MODE_READ_ONLY or option == self.current_option
        ]

    def select_option(self, option: str) -> None:
        if option in const.STREAM_5000_WORK_MODE_READ_ONLY:
            raise ServiceValidationError(f"{option} cannot be selected from Home Assistant")
        super().select_option(option)


class Stream5000(BaseDevice):
    def __init__(self, device_info: EcoflowDeviceInfo, device_data: DeviceData):
        super().__init__(device_info, device_data)
        self._main_sn = MainSnCache(device_info.sn)

    @property
    def main_sn_cache(self) -> MainSnCache | None:
        return self._main_sn

    def set_command_target_sn(self, command: Message) -> str:
        # Everything but the AC socket is a system setting and goes to the main
        # SN; "An AC socket command uses the SN of the device that owns the socket"
        if isinstance(command, JSONMessage):
            return stream_command_target_sn(command.data, self.device_info.sn, self._main_sn.sn)
        return self.device_info.sn

    def evaluates_set_replies(self) -> bool:
        # every command has needAck true, the reply carries the id and data.cmdOk
        return True

    def _command(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "sn": self.device_info.sn,
            "cmdId": 38,
            "cmdFunc": 254,
            "dirDest": 1,
            "dirSrc": 1,
            "dest": 2,
            "needAck": True,
            "params": params,
        }

    def sensors(self, client: EcoflowApiClient) -> list[SensorEntity]:
        return [
            LevelSensorEntity(client, self, "sysEnergyStreamReport-bpSoc", const.STREAM_SYSTEM_BATTERY_LEVEL),
            WattsSensorEntity(client, self, "sysEnergyStreamReport-pvPwr", const.STREAM_5000_SYSTEM_PV_POWER),
            WattsSensorEntity(client, self, "sysEnergyStreamReport-bpPwr", const.STREAM_POWER_BATTERY),
            WattsSensorEntity(client, self, "sysEnergyStreamReport-loadPwr", const.STREAM_5000_SYSTEM_LOAD_POWER),
            WattsSensorEntity(client, self, "sysEnergyStreamReport-gridPwr", const.STREAM_5000_SYSTEM_GRID_POWER),
            WattsSensorEntity(client, self, "sysEnergyStreamReport-onGridPwr", const.STREAM_5000_ON_GRID_POWER),
            self._status_sensor(client),
        ]

    def numbers(self, client: EcoflowApiClient) -> list[NumberEntity]:
        return [
            LevelEntity(
                client,
                self,
                "bpBackupConfig-backupSoc",
                const.BACKUP_RESERVE_LEVEL,
                0,
                100,
                # "The switch must already be on; it may also be enabled in the same
                # request": a backupSoc-only request is rejected while it is off
                lambda value: self._command({"bpBackupConfig": {"backupSocOnOff": True, "backupSoc": int(value)}}),
            ).with_icon("mdi:battery-charging-90"),
        ]

    def switches(self, client: EcoflowApiClient) -> list[SwitchEntity]:
        return [
            EnabledEntity(
                client,
                self,
                "bpBackupConfig-backupSocOnOff",
                const.BP_ENABLED,
                # "Turning the switch off sends backupSoc: 0 in the same command"
                lambda value: self._command(
                    {"bpBackupConfig": {"backupSocOnOff": True} if value else {"backupSocOnOff": False, "backupSoc": 0}}
                ),
                enableValue=True,
                disableValue=False,
            ),
            EnabledEntity(
                client,
                self,
                "powerParameterConfig-feedToGridLimitOnOff",
                const.STREAM_5000_FEED_IN_LIMIT,
                lambda value: self._command({"powerParameterConfig": {"feedToGridLimitOnOff": bool(value)}}),
                enableValue=True,
                disableValue=False,
            ),
            EnabledEntity(
                client,
                self,
                "devSwitch-acSocketOnoff",
                const.STREAM_5000_AC_SOCKET,
                lambda value: self._command({"devSwitch": {"acSocketOnoff": bool(value)}}),
                enableValue=True,
                disableValue=False,
            ),
        ]

    def selects(self, client: EcoflowApiClient) -> list[SelectEntity]:
        return [
            WorkModeSelectEntity(
                client,
                self,
                "workMode",
                const.STREAM_5000_WORK_MODE,
                const.STREAM_5000_WORK_MODE_OPTIONS,
                lambda value: self._command({"workMode": value}),
            ),
        ]

    def _prepare_data(self, raw_data: bytes) -> dict[str, Any]:
        res = super()._prepare_data(raw_data)
        if not isinstance(res, dict) or not res:
            return {}
        return {"params": flatten_quota(res), "raw_data": res}

    def _status_sensor(self, client: EcoflowApiClient) -> StatusSensorEntity:
        # Same as StreamAC. How often this series reports on the public API has not
        # been seen yet; a long quiet phase would reconnect the account's MQTT session.
        return StatusSensorEntity(client, self, reconnect_when_stale=True)
