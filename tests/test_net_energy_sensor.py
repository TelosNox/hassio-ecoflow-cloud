"""NetEnergySensorEntity: Smart Meter net counters fall during export.

shuette42/ecoflow-energy-ha#331 measured the meter's per-phase and total net
energy (import minus export) dropping while a phase fed in, so these must be
TOTAL counters that accept lower and negative readings.
"""

from homeassistant.components.sensor import SensorStateClass

from custom_components.ecoflow_cloud.sensor import EnergySensorEntity, NetEnergySensorEntity


def _entity() -> NetEnergySensorEntity:
    entity = NetEnergySensorEntity.__new__(NetEnergySensorEntity)
    entity._attr_native_value = None
    return entity


def test_state_class_is_total() -> None:
    assert _entity().state_class == SensorStateClass.TOTAL
    assert EnergySensorEntity.__new__(EnergySensorEntity).state_class == SensorStateClass.TOTAL_INCREASING


def test_accepts_falling_and_negative_values() -> None:
    entity = _entity()
    assert entity._update_value(13671.0)
    assert entity._update_value(13668.0)
    assert entity._attr_native_value == 13668
    assert entity._update_value(-25)
    assert entity._attr_native_value == -25


def test_zero_is_ignored() -> None:
    entity = _entity()
    entity._update_value(42)
    assert not entity._update_value(0)
    assert entity._attr_native_value == 42
