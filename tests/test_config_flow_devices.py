"""Config flow when the developer account lists no devices.

tolwi#598, #791: the keys belong to another account than the devices, or the
devices are only shared with it. The flow said "every device in this account
has already been added", which sent users looking in the wrong place.
"""

import asyncio
import json
from pathlib import Path

from custom_components.ecoflow_cloud.config_flow import EcoflowConfigFlow

TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / "ecoflow_cloud" / "translations"


class _Auth:
    def __init__(self, devices):
        self.devices = devices

    async def fetch_all_available_devices(self):
        return self.devices


def _select_device(devices) -> dict:
    flow = EcoflowConfigFlow()
    flow.auth = _Auth(devices)  # type: ignore[assignment]
    flow.flow_id = "test"
    flow.handler = "ecoflow_cloud"
    return asyncio.run(flow.async_step_select_device())  # type: ignore[return-value]


def test_empty_device_list_has_its_own_reason():
    result = _select_device([])

    assert result["type"] == "abort"
    assert result["reason"] == "no_devices_found"


def test_every_translation_has_the_reason():
    for path in TRANSLATIONS.glob("*.json"):
        abort = json.loads(path.read_text(encoding="utf-8"))["config"]["abort"]
        assert "no_devices_found" in abort, path.name
