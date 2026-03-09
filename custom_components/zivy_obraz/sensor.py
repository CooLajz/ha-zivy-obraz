from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import ZivyObrazCoordinator


@dataclass(frozen=True, kw_only=True)
class ZivyObrazSensorDescription(SensorEntityDescription):
    value_key: str
    create_if_missing: bool = False


SENSOR_DESCRIPTIONS: tuple[ZivyObrazSensorDescription, ...] = (
    ZivyObrazSensorDescription(
        key="battery_percent",
        value_key="battery_percent",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        create_if_missing=True,
    ),
    ZivyObrazSensorDescription(
        key="battery_volts",
        value_key="battery_volts",
        name="Battery voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="temperature",
        value_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZivyObrazSensorDescription(
        key="humidity",
        value_key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZivyObrazSensorDescription(
        key="pressure",
        value_key="pressure",
        name="Pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZivyObrazSensorDescription(
        key="rssi",
        value_key="rssi",
        name="RSSI",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="last_contact",
        value_key="last_contact",
        name="Last contact",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSensorDescription(
        key="next_contact",
        value_key="next_contact",
        name="Next contact",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zivy Obraz sensors from a config entry."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data

    known_entity_ids: set[str] = set()

    def _should_create_entity(mac: str, description: ZivyObrazSensorDescription) -> bool:
        """Return True if the sensor should exist for this device."""
        if description.create_if_missing:
            return True

        device_data = coordinator.data.get(mac, {})
        value = device_data.get(description.value_key)
        return value is not None

    def _build_entities_for_macs(macs: set[str]) -> list[ZivyObrazSensor]:
        entities: list[ZivyObrazSensor] = []

        for mac in macs:
            for description in SENSOR_DESCRIPTIONS:
                if not _should_create_entity(mac, description):
                    continue

                unique_id = f"{mac}_{description.key}"
                if unique_id in known_entity_ids:
                    continue

                known_entity_ids.add(unique_id)
                entities.append(ZivyObrazSensor(coordinator, mac, description))

        return entities

    def _build_entities_for_all_supported_data() -> list[ZivyObrazSensor]:
        entities: list[ZivyObrazSensor] = []

        for mac in coordinator.data:
            for description in SENSOR_DESCRIPTIONS:
                if not _should_create_entity(mac, description):
                    continue

                unique_id = f"{mac}_{description.key}"
                if unique_id in known_entity_ids:
                    continue

                known_entity_ids.add(unique_id)
                entities.append(ZivyObrazSensor(coordinator, mac, description))

        return entities

    initial_entities = _build_entities_for_macs(set(coordinator.data.keys()))
    if initial_entities:
        async_add_entities(initial_entities)

    @callback
    def _handle_new_devices(new_macs: set[str]) -> None:
        new_entities = _build_entities_for_macs(new_macs)
        if new_entities:
            async_add_entities(new_entities)

    @callback
    def _handle_coordinator_update() -> None:
        """Add entities if newly supported values appear after refresh."""
        new_entities = _build_entities_for_all_supported_data()
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_new_device_listener(_handle_new_devices))
    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


class ZivyObrazSensor(CoordinatorEntity[ZivyObrazCoordinator], SensorEntity):
    """Representation of one Živý Obraz sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZivyObrazCoordinator,
        mac: str,
        description: ZivyObrazSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
        )

    @property
    def _device_data(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._mac, {})

    @property
    def device_info(self) -> DeviceInfo:
        data = self._device_data
        caption = data.get("caption") or self._mac
        fw = data.get("fw")
        x = data.get("x")
        y = data.get("y")
        colors = data.get("colors")

        model_parts: list[str] = []
        if x and y:
            model_parts.append(f"{x}x{y}")
        if colors:
            model_parts.append(str(colors))

        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=caption,
            manufacturer="Živý Obraz",
            model=" ".join(model_parts) if model_parts else None,
            sw_version=fw,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._mac in self.coordinator.data

    @property
    def native_value(self):
        value = self._device_data.get(self.entity_description.value_key)

        if self.entity_description.key in ("last_contact", "next_contact"):
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(str(value))
                if parsed.tzinfo is None:
                    parsed = dt_util.as_local(parsed)
                return parsed
            except (TypeError, ValueError):
                return None

        if self.entity_description.key == "battery_percent":
            if value is None:
                return None
            try:
                value = int(value)
            except (TypeError, ValueError):
                return None

            if value > 100:
                return 100
            if value < 0:
                return 0
            return value

        if self.entity_description.key in (
            "temperature",
            "humidity",
            "pressure",
            "battery_volts",
            "rssi",
        ):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._device_data
        return {
            "mac": self._mac,
            "caption": data.get("caption"),
            "alias": data.get("alias"),
            "hwtype": data.get("hwtype"),
            "fw": data.get("fw"),
            "content_mode": data.get("contentMode"),
            "is_external": data.get("isexternal"),
            "rotate": data.get("rotate"),
            "lut": data.get("lut"),
            "wakeup_reason": data.get("wakeupReason"),
            "capabilities": data.get("capabilities"),
        }