"""IntegralEnergySensorEntity against the IntegrationSensor signature of each HA version."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass

from custom_components.ecoflow_cloud import sensor


def _base() -> SimpleNamespace:
    return SimpleNamespace(
        coordinator=SimpleNamespace(hass=MagicMock()),
        _device=SimpleNamespace(device_info=SimpleNamespace(name="STREAM")),
        title=lambda: "Power PV Energy",
        entity_id="sensor.stream_power_pv",
        _attr_unique_id="ecoflow-api-SN-powGetPv",
        device_info={"identifiers": {("ecoflow_cloud", "SN")}},
        enabled_default=True,
    )


def test_integral_sensor_can_be_created_on_the_installed_ha():
    # A required argument HA adds to IntegrationSensor fails here, on the beta job first
    entity = sensor.IntegralEnergySensorEntity(_base())  # type: ignore[arg-type]
    assert entity.unique_id == "ecoflow-api-SN-powGetPv_energy"


def test_device_class_is_passed_when_ha_requires_it(monkeypatch):
    received = {}

    def init(self, **kwargs) -> None:
        received.update(kwargs)

    monkeypatch.setattr(sensor.IntegrationSensor, "__init__", init)
    monkeypatch.setattr(sensor, "_INTEGRATION_SENSOR_TAKES_DEVICE_CLASS", True)
    sensor.IntegralEnergySensorEntity(_base())  # type: ignore[arg-type]
    assert received["device_class"] == SensorDeviceClass.ENERGY


def test_device_class_is_not_passed_to_older_ha(monkeypatch):
    received = {}

    def init(self, **kwargs) -> None:
        received.update(kwargs)

    monkeypatch.setattr(sensor.IntegrationSensor, "__init__", init)
    monkeypatch.setattr(sensor, "_INTEGRATION_SENSOR_TAKES_DEVICE_CLASS", False)
    sensor.IntegralEnergySensorEntity(_base())  # type: ignore[arg-type]
    assert "device_class" not in received
