from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity

from custom_components.ecoflow_cloud.devices import BaseDevice, const
from custom_components.ecoflow_cloud.api import EcoflowApiClient
from custom_components.ecoflow_cloud.devices.public.delta3_max_plus import Delta3ChargingStateSensorEntity
from custom_components.ecoflow_cloud.entities import keep_unique_id
from custom_components.ecoflow_cloud.number import (
    ChargingPowerEntity,
    MaxBatteryLevelEntity,
    MinBatteryLevelEntity,
)
from custom_components.ecoflow_cloud.select import DictSelectEntity, TimeoutDictSelectEntity
from custom_components.ecoflow_cloud.sensor import (
    # AmpSensorEntity,
    CapacitySensorEntity,
    FrequencySensorEntity,
    # CyclesSensorEntity,
    # InAmpSensorEntity,
    # InVoltSensorEntity,
    InWattsSensorEntity,
    LevelSensorEntity,
    MiscSensorEntity,
    # OutVoltSensorEntity,
    OutWattsSensorEntity,
    QuotaStatusSensorEntity,
    RemainSensorEntity,
    TempSensorEntity,
    # VoltSensorEntity,
)
from custom_components.ecoflow_cloud.switch import BeeperEntity, EnabledEntity


class FlowInfoSwitch(EnabledEntity):
    """Output switch whose state is a flowInfo* quota field.

    delta_pro_3.md: the set command is cfg*Open, but the device reports the
    state as flowInfoAcHvOut / flowInfoAcLvOut / flowInfo12v / flowInfo24v,
    "(0: off, 2: on.)". Other values leave the state alone. The command keeps
    sending 1/0 as before (reported working, tolwi#615).
    """

    def _update_value(self, val: Any) -> bool:
        if val == 2:
            new_state = True
        elif val == 0:
            new_state = False
        else:
            return False
        if self._attr_is_on != new_state:
            self._attr_is_on = new_state
            return True
        return False

    def turn_on(self, **kwargs: Any) -> None:
        if self._command:
            self.send_set_message(2, self.command_dict(1))

    def turn_off(self, **kwargs: Any) -> None:
        if self._command:
            self.send_set_message(0, self.command_dict(0))


class DeltaPro3(BaseDevice):
    def sensors(self, client: EcoflowApiClient) -> list[SensorEntity]:
        return [
            LevelSensorEntity(client, self, "bmsBattSoc", const.MAIN_BATTERY_LEVEL),
            # .attr("bmsDesignCap", const.ATTR_DESIGN_CAPACITY, 0)
            # .attr("bmsFullCapMah", const.ATTR_FULL_CAPACITY, 0)
            # .attr("bmsRemainCapMah", const.ATTR_REMAIN_CAPACITY, 0),
            CapacitySensorEntity(client, self, "bmsDesignCap", const.MAIN_DESIGN_CAPACITY, False),
            # CapacitySensorEntity(client, self, "bmsFullCapMah", const.MAIN_FULL_CAPACITY, False),
            # CapacitySensorEntity(client, self, "bmsRemainCapMah", const.MAIN_REMAIN_CAPACITY, False),
            # 0: idle, 1: discharging, 2: charging (same enum as the DELTA 3 Max Plus)
            Delta3ChargingStateSensorEntity(client, self, "cmsChgDsgState", "Charging/Discharging State", False),
            MiscSensorEntity(client, self, "cmsBmsRunState", "BMS Run State", False),
            LevelSensorEntity(client, self, "cmsBattSoc", const.COMBINED_BATTERY_LEVEL),
            # LevelSensorEntity(client, self, "bmsBattSoh", const.SOH),
            # CyclesSensorEntity(client, self, "bmsCycles", const.CYCLES),
            # VoltSensorEntity(client, self, "bmsBattVol", const.BATTERY_VOLT, False)
            # .attr("bmsMinCellVol", const.ATTR_MIN_CELL_VOLT, 0)
            # .attr("bmsMaxCellVol", const.ATTR_MAX_CELL_VOLT, 0),
            # VoltSensorEntity(client, self, "bmsMinCellVol", const.MIN_CELL_VOLT, False),
            # VoltSensorEntity(client, self, "bmsMaxCellVol", const.MAX_CELL_VOLT, False),
            # AmpSensorEntity(client, self, "bmsBattAmp", const.MAIN_BATTERY_CURRENT, False),
            TempSensorEntity(client, self, "bmsMaxCellTemp", const.MAX_CELL_TEMP, False),
            TempSensorEntity(client, self, "bmsMinCellTemp", const.MIN_CELL_TEMP, False),
            # TempSensorEntity(client, self, "bmsMaxMosTemp", const.BATTERY_TEMP)
            # .attr("bmsMinCellTemp", const.ATTR_MIN_CELL_TEMP, 0)
            # .attr("bmsMaxCellTemp", const.ATTR_MAX_CELL_TEMP, 0),
            RemainSensorEntity(client, self, "bmsChgRemTime", const.CHARGE_REMAINING_TIME),
            RemainSensorEntity(client, self, "bmsDsgRemTime", const.DISCHARGE_REMAINING_TIME),
            RemainSensorEntity(client, self, "cmsChgRemTime", "Total Charging Time"),
            RemainSensorEntity(client, self, "cmsDsgRemTime", "Total Discharging Time"),
            InWattsSensorEntity(client, self, "powInSumW", const.TOTAL_IN_POWER).with_energy(),
            OutWattsSensorEntity(client, self, "powOutSumW", const.TOTAL_OUT_POWER).with_energy(),
            InWattsSensorEntity(client, self, "powGetAcIn", const.AC_IN_POWER),
            OutWattsSensorEntity(client, self, "powGetAcHvOut", "Real-time grid power"),
            OutWattsSensorEntity(client, self, "powGetAc", const.AC_OUT_POWER),
            OutWattsSensorEntity(client, self, "powGet12v", "12V DC Output Power"),
            OutWattsSensorEntity(client, self, "powGet24v", "24V DC Output Power"),
            OutWattsSensorEntity(client, self, "powGetAcLvOut", "Real-time low-voltage AC output power"),
            OutWattsSensorEntity(
                client, self, "powGetAcLvTt30Out", "Real-time power of the low-voltage AC output port"
            ),
            # OutVoltSensorEntity(client, self, "powGet12vVol", "12V DC Output Voltage"),
            # OutVoltSensorEntity(client, self, "powGet24vVol", "24V DC Output Voltage"),
            InWattsSensorEntity(client, self, "powGetPvH", "Solar High Voltage Input Power"),
            InWattsSensorEntity(client, self, "powGetPvL", "Solar Low Voltage Input Power"),
            # InVoltSensorEntity(client, self, "powGetPvHVol", "Solar HV Input Voltage"),
            # InVoltSensorEntity(client, self, "powGetPvLVol", "Solar LV Input Voltage"),
            # InAmpSensorEntity(client, self, "powGetPvHAmp", "Solar HV Input Current"),
            # InAmpSensorEntity(client, self, "powGetPvLAmp", "Solar LV Input Current"),
            OutWattsSensorEntity(client, self, "powGetQcusb1", const.USB_QC_1_OUT_POWER),
            OutWattsSensorEntity(client, self, "powGetQcusb2", const.USB_QC_2_OUT_POWER),
            OutWattsSensorEntity(client, self, "powGetTypec1", const.TYPEC_1_OUT_POWER),
            OutWattsSensorEntity(client, self, "powGetTypec2", const.TYPEC_2_OUT_POWER),
            OutWattsSensorEntity(client, self, "powGet5p8", "5P8 Power I/O Port Power"),
            OutWattsSensorEntity(client, self, "powGet4p81", "4P8 Extra Battery Port 1 Power", False, True),
            OutWattsSensorEntity(client, self, "powGet4p82", "4P8 Extra Battery Port 2 Power", False, True),
            # OutWattsSensorEntity(client, self, "acOutFreq", "AC Output Frequency"),
            FrequencySensorEntity(client, self, "plugInInfoAcInFeq", "AC Input Frequency"),
            QuotaStatusSensorEntity(client, self),
        ]

    def numbers(self, client: EcoflowApiClient) -> list[NumberEntity]:
        return [
            MaxBatteryLevelEntity(
                client,
                self,
                "cmsMaxChgSoc",
                const.MAX_CHARGE_LEVEL,
                50,
                100,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgMaxChgSoc": value},
                },
            ),
            MinBatteryLevelEntity(
                client,
                self,
                "cmsMinDsgSoc",
                const.MIN_DISCHARGE_LEVEL,
                0,
                30,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgMinDsgSoc": value},
                },
            ),
            MaxBatteryLevelEntity(
                client,
                self,
                "cmsOilOnSoc",
                "Smart Generator Start SOC",
                0,
                100,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgCmsOilOnSoc": value},
                },
            ),
            MinBatteryLevelEntity(
                client,
                self,
                "cmsOilOffSoc",
                "Smart Generator Stop SOC",
                0,
                100,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgCmsOilOffSoc": value},
                },
            ),
            # quota field plugInInfoAcInChgPowMax; cfg* is only the set command name
            keep_unique_id(ChargingPowerEntity(
                client,
                self,
                "plugInInfoAcInChgPowMax",
                const.AC_CHARGING_POWER,
                400,
                2900,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgPlugInInfoAcInChgPowMax": value},
                },
            ), "cfgPlugInInfoAcInChgPowMax"),
        ]

    def switches(self, client: EcoflowApiClient) -> list[SwitchEntity]:
        return [
            BeeperEntity(
                client,
                self,
                "enBeep",
                const.BEEPER,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgBeepEn": value},
                },
                # enBeep / cfgBeepEn are true when the beeper is on, unlike the
                # inverted quiet-mode flags BeeperEntity defaults to
                enableValue=1,
                disableValue=0,
            ),
            keep_unique_id(FlowInfoSwitch(
                client,
                self,
                "flowInfoAcHvOut",
                "AC HV Output Enabled",
                lambda value, params=None: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgHvAcOutOpen": value},
                },
            ), "cfgHvAcOutOpen"),
            keep_unique_id(FlowInfoSwitch(
                client,
                self,
                "flowInfoAcLvOut",
                "AC LV Output Enabled",
                lambda value, params=None: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgLvAcOutOpen": value},
                },
            ), "cfgLvAcOutOpen"),
            keep_unique_id(FlowInfoSwitch(
                client,
                self,
                "flowInfo12v",
                "12V DC Output Enabled",
                lambda value, params=None: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgDc12vOutOpen": value},
                },
            ), "cfgDc12vOutOpen"),
            keep_unique_id(FlowInfoSwitch(
                client,
                self,
                "flowInfo24v",
                "24V DC Output Enabled",
                lambda value, params=None: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgDc24vOutOpen": value},
                },
            ), "cfgDc24vOutOpen"),
            EnabledEntity(
                client,
                self,
                "xboostEn",
                const.XBOOST_ENABLED,
                lambda value, params=None: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgXboostEn": value},
                },
            ),
            EnabledEntity(
                client,
                self,
                "acEnergySavingOpen",
                "AC Energy Saving Enabled",
                lambda value, params=None: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgAcEnergySavingOpen": value},
                },
            ),
            EnabledEntity(
                client,
                self,
                "cmsOilSelfStart",
                "Smart Generator Auto Start/Stop",
                lambda value, params=None: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgCmsOilSelfStart": value},
                },
            ),
        ]

    def selects(self, client: EcoflowApiClient) -> list[SelectEntity]:
        return [
            TimeoutDictSelectEntity(
                client,
                self,
                "screenOffTime",
                const.SCREEN_TIMEOUT,
                const.SCREEN_TIMEOUT_OPTIONS,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgScreenOffTime": value},
                },
            ),
            TimeoutDictSelectEntity(
                client,
                self,
                "acStandbyTime",
                const.AC_TIMEOUT,
                const.AC_TIMEOUT_OPTIONS,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgAcStandbyTime": value},
                },
            ),
            TimeoutDictSelectEntity(
                client,
                self,
                "dcStandbyTime",
                "DC Timeout",
                const.UNIT_TIMEOUT_OPTIONS_LIMITED,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgDcStandbyTime": value},
                },
            ),
            TimeoutDictSelectEntity(
                client,
                self,
                "bleStandbyTime",
                "Bluetooth Timeout",
                const.UNIT_TIMEOUT_OPTIONS_LIMITED,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgBleStandbyTime": value},
                },
            ),
            TimeoutDictSelectEntity(
                client,
                self,
                "devStandbyTime",
                "Device Timeout",
                const.UNIT_TIMEOUT_OPTIONS_LIMITED,
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgDevStandbyTime": value},
                },
            ),
            DictSelectEntity(
                client,
                self,
                "plugInInfoAcOutType",
                "AC Output Type",
                {"HV+LV": 0, "HV Only": 1, "LV Only": 2},
                lambda value: {
                    "sn": self.device_info.sn,
                    "cmdId": 17,
                    "dirDest": 1,
                    "dirSrc": 1,
                    "cmdFunc": 254,
                    "dest": 2,
                    "params": {"cfgPlugInInfoAcOutType": int(value)},
                },
            ),
        ]
