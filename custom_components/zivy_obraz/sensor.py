from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
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
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    BATTERY_CHARGE_BASELINE_DAYS,
    BATTERY_CHARGE_COOLDOWN_DAYS,
    BATTERY_CHARGE_DAILY_AVERAGE_SAMPLE_LIMIT,
    BATTERY_CHARGE_MAX_STAT_VOLTAGE,
    BATTERY_CHARGE_THRESHOLD_VOLTS,
    DOMAIN,
)
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info, diagnostic_device_identifier
from .push import ZivyObrazPushManager


@dataclass(frozen=True, kw_only=True)
class ZivyObrazSensorDescription(SensorEntityDescription):
    """Sensor description for Živý Obraz."""

    value_key: str
    create_if_missing: bool = False

    def __post_init__(self) -> None:
        """Use the entity key as the default translation key."""
        if self.translation_key is None:
            object.__setattr__(self, "translation_key", self.key)
        object.__setattr__(self, "name", None)


@dataclass(frozen=True, kw_only=True)
class ZivyObrazPushSensorDescription(SensorEntityDescription):
    """Sensor description for Živý Obraz push diagnostics."""

    value_key: str

    def __post_init__(self) -> None:
        """Use the entity key as the default translation key."""
        if self.translation_key is None:
            object.__setattr__(self, "translation_key", self.key)
        object.__setattr__(self, "name", None)


@dataclass(frozen=True, kw_only=True)
class ZivyObrazSyncSensorDescription(SensorEntityDescription):
    """Sensor description for Živý Obraz sync diagnostics."""

    value_key: str

    def __post_init__(self) -> None:
        """Use the entity key as the default translation key."""
        if self.translation_key is None:
            object.__setattr__(self, "translation_key", self.key)
        object.__setattr__(self, "name", None)


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
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSensorDescription(
        key="battery_days_since_last_charge",
        value_key="battery_volts",
        name="Battery days since last charge",
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:battery-clock-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSensorDescription(
        key="battery_charge_detection_status",
        value_key="battery_volts",
        name="Battery charge detection status",
        translation_key="battery_charge_detection_status",
        icon="mdi:battery-sync-outline",
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
        icon="mdi:wifi-strength-2",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="ssid",
        value_key="ssid",
        name="WiFi SSID",
        icon="mdi:access-point-network",
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
        icon="mdi:account-group",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSensorDescription(
        key="fw_build",
        value_key="fw_build",
        name="FW build",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="reset_reason",
        value_key="reset_reason",
        name="Reset reason",
        icon="mdi:restart-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="last_picture_download_ms",
        value_key="last_picture_download_ms",
        name="Last picture download",
        native_unit_of_measurement="ms",
        icon="mdi:image-sync",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="last_display_refresh_ms",
        value_key="last_display_refresh_ms",
        name="Last display refresh",
        native_unit_of_measurement="ms",
        icon="mdi:monitor-dashboard",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSensorDescription(
        key="daily_contacts",
        value_key="last_contact",
        name="Daily contacts",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSensorDescription(
        key="daily_display_refreshes",
        value_key="last_contact",
        name="Daily display refreshes",
        icon="mdi:monitor-dashboard",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

PUSH_SENSOR_DESCRIPTIONS: tuple[ZivyObrazPushSensorDescription, ...] = (
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
        icon="mdi:cloud-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazPushSensorDescription(
        key="push_pushed_entities",
        value_key="pushed_entities",
        name="Pushed entities",
        icon="mdi:cloud-upload-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazPushSensorDescription(
        key="push_skipped_entities",
        value_key="skipped_entities",
        name="Skipped entities",
        icon="mdi:debug-step-over",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazPushSensorDescription(
        key="push_failed_entities",
        value_key="failed_entities",
        name="Failed entities",
        icon="mdi:cloud-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazPushSensorDescription(
        key="push_request_batches",
        value_key="request_batches",
        name="Request batches",
        icon="mdi:package-variant-closed",
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
    icon="mdi:cloud-clock-outline",
    entity_category=EntityCategory.DIAGNOSTIC,
)

SYNC_SENSOR_DESCRIPTIONS: tuple[ZivyObrazSyncSensorDescription, ...] = (
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
        icon="mdi:sync-circle",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZivyObrazSyncSensorDescription(
        key="sync_next_sync",
        value_key="next_sync",
        name="Next sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:cloud-clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZivyObrazSyncSensorDescription(
        key="sync_device_count",
        value_key="device_count",
        name="Device count",
        icon="mdi:devices",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


def _timestamp_attribute(value: Any) -> str | None:
    """Return a timestamp attribute in a storage-friendly form."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@callback
def _remove_obsolete_diagnostic_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Remove diagnostic entities that were replaced by status attributes."""
    obsolete_unique_ids = {
        f"{entry.entry_id}_push_last_push",
        f"{entry.entry_id}_sync_last_sync",
    }
    entity_registry = er.async_get(hass)

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "sensor":
            continue
        if entity_entry.unique_id not in obsolete_unique_ids:
            continue
        entity_registry.async_remove(entity_entry.entity_id)


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
    _remove_obsolete_diagnostic_entities(hass, entry)

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

    def _registered_macs_for_description(
        description: ZivyObrazSensorDescription,
    ) -> set[str]:
        """Return MACs for previously registered sensors of this entry."""
        entity_registry = er.async_get(hass)
        suffix = f"_{description.key}"
        macs: set[str] = set()

        for entity_entry in er.async_entries_for_config_entry(
            entity_registry,
            entry.entry_id,
        ):
            if entity_entry.domain != "sensor":
                continue
            if not entity_entry.unique_id.endswith(suffix):
                continue
            mac = entity_entry.unique_id.removesuffix(suffix)
            if mac:
                macs.add(mac)

        return macs

    def _build_restored_entities() -> list[ZivyObrazSensor]:
        """Recreate previously registered ePaper sensors before fresh data arrives."""
        entities: list[ZivyObrazSensor] = []

        for description in SENSOR_DESCRIPTIONS:
            for mac in _registered_macs_for_description(description):
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
    initial_entities.extend(_build_restored_entities())
    if push_manager is not None:
        initial_entities.extend(
            ZivyObrazPushDiagnosticSensor(entry, push_manager, description)
            for description in PUSH_SENSOR_DESCRIPTIONS
        )
        initial_entities.append(
            ZivyObrazPushDiagnosticSensor(
                entry,
                push_manager,
                PUSH_NEXT_SENSOR_DESCRIPTION,
            )
        )

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


class ZivyObrazSensor(
    CoordinatorEntity[ZivyObrazCoordinator],
    RestoreSensor,
):
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
        self._restored_native_value: Any = None
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last known state until fresh data is available."""
        await super().async_added_to_hass()
        last_sensor_data = await self.async_get_last_sensor_data()
        if last_sensor_data is not None:
            self._restored_native_value = last_sensor_data.native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        if self._mac in self.coordinator.data:
            self._device_data_cache = self.coordinator.data[self._mac]
        elif self.coordinator.last_update_success:
            self._device_data_cache = {}
        super()._handle_coordinator_update()

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return cached device data."""
        return self._device_data_cache

    @property
    def device_info(self):
        """Return device info."""
        if not self._device_data:
            return DeviceInfo(identifiers={(DOMAIN, self._mac)})
        return build_device_info(self._mac, self._device_data)

    @property
    def available(self) -> bool:
        """Return availability."""
        return bool(self._device_data) or self._restored_native_value is not None

    @property
    def native_value(self):
        """Return sensor value."""
        value = self._device_data.get(self.entity_description.value_key)
        if value is None and not self._device_data:
            return self._restored_native_value

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

        if self.entity_description.key == "battery_days_since_last_charge":
            last_charged = self.coordinator.battery_tracker.state_for(
                self._mac
            ).last_charged
            if last_charged is None:
                return None
            try:
                days_since_charge = (
                    dt_util.now().date() - dt_util.as_local(last_charged).date()
                ).days
                return max(days_since_charge, 0)
            except (TypeError, ValueError):
                return None

        if self.entity_description.key == "battery_charge_detection_status":
            return self.coordinator.battery_tracker.state_for(self._mac).status

        if self.entity_description.key == "daily_contacts":
            return self.coordinator.display_activity_tracker.state_for(
                self._mac
            ).daily_contacts

        if self.entity_description.key == "daily_display_refreshes":
            return self.coordinator.display_activity_tracker.state_for(
                self._mac
            ).daily_display_refreshes

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
        if self.entity_description.key == "fw_build":
            fw = self._device_data.get("fw")
            if fw is not None:
                return {"major_version": str(fw)}
        if self.entity_description.key == "battery_volts":
            tracker_state = self.coordinator.battery_tracker.state_for(self._mac)
            return {
                "voltage_min": tracker_state.voltage_min,
                "voltage_max": tracker_state.voltage_max,
                "last_charged": tracker_state.last_charged.isoformat()
                if tracker_state.last_charged
                else None,
            }
        if self.entity_description.key == "battery_charge_detection_status":
            tracker_state = self.coordinator.battery_tracker.state_for(self._mac)
            return {
                "daily_samples": tracker_state.daily_samples,
                "daily_average": tracker_state.daily_average,
                "daily_average_sample_limit": (
                    BATTERY_CHARGE_DAILY_AVERAGE_SAMPLE_LIMIT
                ),
                "excluded_daily_samples": tracker_state.excluded_daily_samples,
                "previous_3_day_average": tracker_state.previous_average,
                "stored_days": tracker_state.stored_days,
                "valid_baseline_days": tracker_state.valid_baseline_days,
                "threshold_volts": BATTERY_CHARGE_THRESHOLD_VOLTS,
                "max_stat_voltage": BATTERY_CHARGE_MAX_STAT_VOLTAGE,
                "baseline_days": BATTERY_CHARGE_BASELINE_DAYS,
                "cooldown_days": BATTERY_CHARGE_COOLDOWN_DAYS,
            }
        if self.entity_description.key == "daily_contacts":
            tracker_state = self.coordinator.display_activity_tracker.state_for(
                self._mac
            )
            return {
                "date": tracker_state.day.isoformat() if tracker_state.day else None,
                "daily_display_refreshes": tracker_state.daily_display_refreshes,
                "last_counted_contact": tracker_state.last_counted_contact,
            }
        if self.entity_description.key == "daily_display_refreshes":
            tracker_state = self.coordinator.display_activity_tracker.state_for(
                self._mac
            )
            return {
                "date": tracker_state.day.isoformat() if tracker_state.day else None,
                "daily_contacts": tracker_state.daily_contacts,
                "refresh_ratio": tracker_state.refresh_ratio,
                "refresh_percentage": tracker_state.refresh_percentage,
                "last_counted_contact": tracker_state.last_counted_contact,
                "last_display_refresh_ms": tracker_state.last_display_refresh_ms,
            }
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
            identifiers={diagnostic_device_identifier(entry)},
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
            return {
                "last_attempt": _timestamp_attribute(diagnostics.last_push),
                "last_success": _timestamp_attribute(
                    diagnostics.last_successful_push
                ),
                "last_error": diagnostics.last_error,
                "pushed_entities": diagnostics.pushed_entities,
                "skipped_entities": diagnostics.skipped_entities,
                "failed_entities": diagnostics.failed_entities,
            }

        if self.entity_description.key == "push_pushed_entities":
            return {
                "variables": diagnostics.variables,
                "variables_truncated": diagnostics.variables_truncated,
            }

        if self.entity_description.key == "push_skipped_entities":
            return {
                "skipped_variables": diagnostics.skipped_variables,
                "skipped_variables_truncated": diagnostics.skipped_variables_truncated,
            }

        if self.entity_description.key == "push_failed_entities":
            return {
                "failed_variables": diagnostics.failed_variables,
                "failed_variables_truncated": diagnostics.failed_variables_truncated,
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
            identifiers={diagnostic_device_identifier(entry)},
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
            diagnostics = self.coordinator.diagnostics
            return {
                "last_attempt": _timestamp_attribute(diagnostics.last_sync),
                "last_success": _timestamp_attribute(
                    diagnostics.last_successful_sync
                ),
                "last_error": diagnostics.last_error,
            }

        return None
