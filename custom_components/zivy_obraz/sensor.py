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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info
from .push import ZivyObrazPushManager


@dataclass(frozen=True, kw_only=True)
class ZivyObrazSensorDescription(SensorEntityDescription):
    """Sensor description for Živý Obraz."""

    value_key: str
    create_if_missing: bool = False


@dataclass(frozen=True, kw_only=True)
class ZivyObrazPushSensorDescription(SensorEntityDescription):
    """Sensor description for Živý Obraz push diagnostics."""

    value_key: str


@dataclass(frozen=True, kw_only=True)
class ZivyObrazSyncSensorDescription(SensorEntityDescription):
    """Sensor description for Živý Obraz sync diagnostics."""

    value_key: str


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
        device_class=SensorDeviceClass.VOLTAGE,
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
        key="ssid",
        value_key="ssid",
        name="WiFi SSID",
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
    ZivyObrazSensorDescription(
        key="group_name",
        value_key="group_name",
        name="Group name",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSensorDescription(
        key="fw_build",
        value_key="fw_build",
        name="FW build",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="reset_reason",
        value_key="reset_reason",
        name="Reset reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="last_picture_download_ms",
        value_key="last_picture_download_ms",
        name="Last picture download",
        native_unit_of_measurement="ms",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="last_display_refresh_ms",
        value_key="last_display_refresh_ms",
        name="Last display refresh",
        native_unit_of_measurement="ms",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

PUSH_SENSOR_DESCRIPTIONS: tuple[ZivyObrazPushSensorDescription, ...] = (
    ZivyObrazPushSensorDescription(
        key="push_last_push",
        value_key="last_push",
        name="Last push",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazPushSensorDescription(
        key="push_last_successful_push",
        value_key="last_successful_push",
        name="Last successful push",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazPushSensorDescription(
        key="push_status",
        value_key="status",
        name="Push status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazPushSensorDescription(
        key="push_pushed_entities",
        value_key="pushed_entities",
        name="Pushed entities",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazPushSensorDescription(
        key="push_skipped_entities",
        value_key="skipped_entities",
        name="Skipped entities",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazPushSensorDescription(
        key="push_request_batches",
        value_key="request_batches",
        name="Request batches",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

PUSH_NEXT_SENSOR_DESCRIPTION = ZivyObrazPushSensorDescription(
    key="push_next_push",
    value_key="next_push",
    name="Next push",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)

SYNC_SENSOR_DESCRIPTIONS: tuple[ZivyObrazSyncSensorDescription, ...] = (
    ZivyObrazSyncSensorDescription(
        key="sync_last_sync",
        value_key="last_sync",
        name="Last sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSyncSensorDescription(
        key="sync_last_successful_sync",
        value_key="last_successful_sync",
        name="Last successful sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSyncSensorDescription(
        key="sync_status",
        value_key="status",
        name="Sync status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSyncSensorDescription(
        key="sync_next_sync",
        value_key="next_sync",
        name="Next sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSyncSensorDescription(
        key="sync_device_count",
        value_key="device_count",
        name="Device count",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Živý Obraz sensors from a config entry."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data
    known_entity_ids: set[str] = set()
    push_manager: ZivyObrazPushManager | None = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("push_manager")
    )
    push_is_scheduled = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("push_unsub")
        is not None
    )

    def _should_create_entity(
        mac: str, description: ZivyObrazSensorDescription
    ) -> bool:
        """Return True if the sensor should exist for this device."""
        if description.create_if_missing:
            return True

        device_data = coordinator.data.get(mac, {})
        return device_data.get(description.value_key) is not None

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
    if push_manager is not None:
        initial_entities.extend(
            ZivyObrazPushDiagnosticSensor(entry, push_manager, description)
            for description in PUSH_SENSOR_DESCRIPTIONS
        )
        if push_is_scheduled:
            initial_entities.append(
                ZivyObrazPushDiagnosticSensor(
                    entry,
                    push_manager,
                    PUSH_NEXT_SENSOR_DESCRIPTION,
                )
            )

    if not push_is_scheduled:
        entity_registry = er.async_get(hass)
        entity_id = entity_registry.async_get_entity_id(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_{PUSH_NEXT_SENSOR_DESCRIPTION.key}",
        )
        if entity_id is not None:
            entity_registry.async_remove(entity_id)

    initial_entities.extend(
        ZivyObrazSyncDiagnosticSensor(entry, coordinator, description)
        for description in SYNC_SENSOR_DESCRIPTIONS
    )

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

    entry.async_on_unload(
        coordinator.async_add_new_device_listener(_handle_new_devices)
    )
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
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._device_data_cache: dict[str, Any] = coordinator.data.get(mac, {})
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        self._device_data_cache = self.coordinator.data.get(self._mac, {})
        super()._handle_coordinator_update()

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return cached device data."""
        return self._device_data_cache

    @property
    def device_info(self):
        """Return device info."""
        return build_device_info(self._mac, self._device_data)

    @property
    def available(self) -> bool:
        """Return availability."""
        return (
            self.coordinator.last_update_success
            and self._mac in self.coordinator.data
        )

    @property
    def native_value(self):
        """Return sensor value."""
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
            return max(0, min(value, 100))

        if self.entity_description.key == "battery_volts":
            if value is None:
                return None
            try:
                return round(float(value), 2)
            except (TypeError, ValueError):
                return None

        if self.entity_description.key in (
            "temperature",
            "humidity",
            "pressure",
            "rssi",
            "last_picture_download_ms",
            "last_display_refresh_ms",
        ):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        if self.entity_description.key in (
            "ssid",
            "group_name",
            "fw_build",
            "reset_reason",
        ):
            if value is None:
                return None
            return str(value)

        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes only where they add value."""
        if self.entity_description.key == "group_name":
            group_id = self._device_data.get("group_id")
            if group_id is not None:
                return {"group_id": group_id}
        return None


class ZivyObrazPushDiagnosticSensor(SensorEntity):
    """Representation of one Živý Obraz push diagnostic sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        push_manager: ZivyObrazPushManager,
        description: ZivyObrazPushSensorDescription,
    ) -> None:
        """Initialize the push diagnostic sensor."""
        self.entity_description = description
        self._push_manager = push_manager
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_push")},
            name=f"Živý Obraz - {entry.title}",
            manufacturer="Živý Obraz",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        self.async_on_remove(
            self._push_manager.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self):
        """Return push diagnostic value."""
        diagnostics = self._push_manager.diagnostics
        return getattr(diagnostics, self.entity_description.value_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra details for the push status sensor."""
        diagnostics = self._push_manager.diagnostics

        if self.entity_description.key == "push_status":
            return {"last_error": diagnostics.last_error}

        if self.entity_description.key == "push_pushed_entities":
            return {
                "variables": diagnostics.variables,
                "variables_total": diagnostics.variables_total,
                "variables_truncated": diagnostics.variables_truncated,
            }

        if self.entity_description.key == "push_skipped_entities":
            return {
                "skipped_variables": diagnostics.skipped_variables,
                "skipped_variables_total": diagnostics.skipped_variables_total,
                "skipped_variables_truncated": diagnostics.skipped_variables_truncated,
            }

        return None


class ZivyObrazSyncDiagnosticSensor(
    CoordinatorEntity[ZivyObrazCoordinator],
    SensorEntity,
):
    """Representation of one Živý Obraz sync diagnostic sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ZivyObrazCoordinator,
        description: ZivyObrazSyncSensorDescription,
    ) -> None:
        """Initialize the sync diagnostic sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_push")},
            name=f"Živý Obraz - {entry.title}",
            manufacturer="Živý Obraz",
        )

    @property
    def available(self) -> bool:
        """Keep sync diagnostics available even when the last refresh failed."""
        return True

    @property
    def native_value(self):
        """Return sync diagnostic value."""
        diagnostics = self.coordinator.diagnostics
        return getattr(diagnostics, self.entity_description.value_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra details for the sync status sensor."""
        if self.entity_description.key == "sync_status":
            return {"last_error": self.coordinator.diagnostics.last_error}

        return None
