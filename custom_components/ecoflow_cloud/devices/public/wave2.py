from custom_components.ecoflow_cloud.devices.public.data_bridge import to_plain
from typing import Any
from custom_components.ecoflow_cloud.devices.internal.wave2 import Wave2 as InternalWave2
from custom_components.ecoflow_cloud.api import EcoflowApiClient
from custom_components.ecoflow_cloud.sensor import StatusSensorEntity

# MQTT quota reports name their module by typeCode; quota/all lists the same
# fields under these prefixes. analysisBMS is left out: it comes from
# moduleType 4 (BMS_SLAVE) and would overwrite the main pack's bms.* values.
TYPE_CODE_PREFIX = {
    "analysisPD": "pd",
    "devStatus": "pd",
    "analysisPOWER": "power",
}


class Wave2(InternalWave2):
    def _prepare_data(self, raw_data) -> dict[str, Any]:
        res = super()._prepare_data(raw_data)
        res = to_plain(res)
        prefix = TYPE_CODE_PREFIX.get(res["raw_data"].get("typeCode"))
        report = res["raw_data"].get("params")
        if prefix and isinstance(report, dict):
            for k, v in report.items():
                res["params"][f"{prefix}.{k}"] = v
        return res

    def _status_sensor(self, client: EcoflowApiClient) -> StatusSensorEntity:
        return StatusSensorEntity(client, self)
