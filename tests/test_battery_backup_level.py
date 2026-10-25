"""Range tracking of BatteryBackupLevel (STREAM backup reserve).

EcoFlow documents the STREAM backup reserve as 3-95 % and at least 3 points
above the discharge limit (api-docs/stream.md, "Backup reserve level"). The
charge/discharge limits may narrow that range but must never widen it.
"""

from typing import Any

import pytest

from custom_components.ecoflow_cloud.number import BatteryBackupLevel, MinMaxLevelEntity


def _entity(monkeypatch: pytest.MonkeyPatch) -> BatteryBackupLevel:
    # Skip the HA/coordinator plumbing: only the range arithmetic is under test.
    monkeypatch.setattr(MinMaxLevelEntity, "_updated", lambda self, data: None)
    entity = BatteryBackupLevel.__new__(BatteryBackupLevel)
    entity._min_key = "cmsMinDsgSoc"
    entity._max_key = "cmsMaxChgSoc"
    entity._gap_min = 3
    entity._static_min = 3
    entity._static_max = 95
    entity._attr_native_min_value = 3
    entity._attr_native_max_value = 95
    return entity


@pytest.mark.parametrize(
    ("data", "expected_min", "expected_max"),
    [
        ({"cmsMinDsgSoc": 0, "cmsMaxChgSoc": 100}, 3, 95),
        ({"cmsMinDsgSoc": 5, "cmsMaxChgSoc": 100}, 8, 95),
        ({"cmsMinDsgSoc": 10, "cmsMaxChgSoc": 80}, 13, 80),
        ({"cmsMinDsgSoc": 0, "cmsMaxChgSoc": 95}, 3, 95),
    ],
)
def test_range_follows_limits_within_static_bounds(
    monkeypatch: pytest.MonkeyPatch, data: dict[str, Any], expected_min: int, expected_max: int
) -> None:
    entity = _entity(monkeypatch)
    entity._updated(data)
    assert entity._attr_native_min_value == expected_min
    assert entity._attr_native_max_value == expected_max


def test_range_unchanged_without_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    entity = _entity(monkeypatch)
    entity._updated({"backupReverseSoc": 50})
    assert (entity._attr_native_min_value, entity._attr_native_max_value) == (3, 95)
