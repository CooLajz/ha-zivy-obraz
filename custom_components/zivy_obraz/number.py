from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .command import ZivyObrazCommandError, command_entity_unique_id
from .config_helpers import (
    async_update_option,
    async_update_options,
    get_config_value,
    migrate_entry_entity_unique_ids,
    options_update_signal,
)
from .const import (
    ATTR_SLEEP_FORCED,
    CONF_COMMAND_KEY,
    CONF_IMPORT_KEY,
    CONF_OVERDUE_TOLERANCE,
    CONF_PUSH_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_COMMAND_KEY,
    DEFAULT_IMPORT_KEY,
    DEFAULT_OVERDUE_TOLERANCE,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_OVERDUE_TOLERANCE,
    MAX_PUSH_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_OVERDUE_TOLERANCE,
    MIN_PUSH_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info, diagnostic_device_identifier

PUSH_NUMBER_KEYS = {CONF_PUSH_INTERVAL}


@dataclass(frozen=True, kw_only=True)
class ZivyObrazNumberDescription(NumberEntityDescription):
    """Description for Živý Obraz config number entity."""

    option_key: str
    default_value: int


NUMBER_DESCRIPTIONS: tuple[ZivyObrazNumberDescription, ...] = (
    ZivyObrazNumberDescription(
        key="import_refresh_interval",
        translation_key="import_refresh_interval",
        option_key=CONF_SCAN_INTERVAL,
        default_value=DEFAULT_SCAN_INTERVAL,
        native_min_value=MIN_SCAN_INTERVAL,
        native_max_value=MAX_SCAN_INTERVAL,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:update",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazNumberDescription(
        key="push_interval",
        translation_key="push_interval",
        option_key=CONF_PUSH_INTERVAL,
        default_value=DEFAULT_PUSH_INTERVAL,
        native_min_value=MIN_PUSH_INTERVAL,
        native_max_value=MAX_PUSH_INTERVAL,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:cloud-upload-outline",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazNumberDescription(
        key="overdue_tolerance",
        translation_key="overdue_tolerance",
        option_key=CONF_OVERDUE_TOLERANCE,
        default_value=DEFAULT_OVERDUE_TOLERANCE,
        native_min_value=MIN_OVERDUE_TOLERANCE,
        native_max_value=MAX_OVERDUE_TOLERANCE,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-alert-outline",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Živý Obraz config number entities."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data
    has_import_key = bool(
        str(get_config_value(entry, CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY) or "").strip()
    )
    if not has_import_key:
        _remove_push_config_numbers(hass, entry)

    command_key = str(
        get_config_value(entry, CONF_COMMAND_KEY, DEFAULT_COMMAND_KEY) or ""
    ).strip()
    if not command_key:
        _remove_command_device_numbers(hass, entry)
    else:
        migrate_entry_entity_unique_ids(
            hass,
            entry,
            "number",
            {"_sleep_forced"},
        )

    entities: list[NumberEntity] = [
        ZivyObrazConfigNumber(hass, entry, description)
        for description in NUMBER_DESCRIPTIONS
        if has_import_key or description.key not in PUSH_NUMBER_KEYS
    ]

    known_command_entity_ids: set[str] = set()

    def _build_command_numbers(
        macs: set[str],
    ) -> list[ZivyObrazSleepForcedNumber]:
        command_numbers: list[ZivyObrazSleepForcedNumber] = []
        if not command_key:
            return command_numbers

        for mac in macs:
            unique_id = command_entity_unique_id(
                entry.entry_id,
                mac,
                ATTR_SLEEP_FORCED,
            )
            if unique_id in known_command_entity_ids:
                continue
            known_command_entity_ids.add(unique_id)
            command_numbers.append(
                ZivyObrazSleepForcedNumber(
                    coordinator,
                    mac,
                    command_key,
                    entry.entry_id,
                )
            )
        return command_numbers

    entities.extend(_build_command_numbers(set(coordinator.data)))
    async_add_entities(entities)

    if command_key:

        @callback
        def _handle_new_devices(new_macs: set[str]) -> None:
            new_entities = _build_command_numbers(new_macs)
            if new_entities:
                async_add_entities(new_entities)

        entry.async_on_unload(
            coordinator.async_add_new_device_listener(_handle_new_devices)
        )


@callback
def _remove_push_config_numbers(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove push config number entities when Import key is not configured."""
    entity_registry = er.async_get(hass)
    obsolete_unique_ids = {f"{entry.entry_id}_{key}" for key in PUSH_NUMBER_KEYS}

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "number":
            continue
        if entity_entry.unique_id not in obsolete_unique_ids:
            continue
        entity_registry.async_remove(entity_entry.entity_id)


@callback
def _remove_command_device_numbers(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove command numbers when Command key is not configured."""
    entity_registry = er.async_get(hass)

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "number":
            continue
        if not entity_entry.unique_id.endswith("_sleep_forced"):
            continue
        entity_registry.async_remove(entity_entry.entity_id)


class ZivyObrazConfigNumber(NumberEntity):
    """Representation of a Živý Obraz config number entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        description: ZivyObrazNumberDescription,
    ) -> None:
        """Initialize config number entity."""
        self.hass = hass
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._native_value = self._read_option_value(description)
        self._scan_interval = int(
            get_config_value(
                entry,
                CONF_SCAN_INTERVAL,
                DEFAULT_SCAN_INTERVAL,
            )
        )
        self._attr_device_info = DeviceInfo(
            identifiers={diagnostic_device_identifier(entry)},
            name=f"Živý Obraz - {entry.title}",
            manufacturer="Živý Obraz",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                options_update_signal(self._entry.entry_id),
                self._handle_options_update,
            )
        )

    @property
    def native_min_value(self) -> float:
        """Return current minimum value."""
        if self.entity_description.option_key != CONF_OVERDUE_TOLERANCE:
            return self.entity_description.native_min_value

        return max(MIN_OVERDUE_TOLERANCE, math.ceil(self._scan_interval / 60))

    @property
    def native_value(self) -> int:
        """Return current option value."""
        return self._native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the stored option value."""
        int_value = round(value)
        int_value = max(int_value, int(self.native_min_value))
        int_value = min(int_value, int(self.native_max_value))

        if self.entity_description.option_key == CONF_SCAN_INTERVAL:
            min_overdue_tolerance = math.ceil(int_value / 60)
            overdue_tolerance = int(
                get_config_value(
                    self._entry,
                    CONF_OVERDUE_TOLERANCE,
                    DEFAULT_OVERDUE_TOLERANCE,
                )
            )
            await async_update_options(
                self.hass,
                self._entry,
                {
                    CONF_SCAN_INTERVAL: int_value,
                    CONF_OVERDUE_TOLERANCE: max(
                        overdue_tolerance,
                        min_overdue_tolerance,
                    ),
                },
            )
            return

        await async_update_option(
            self.hass,
            self._entry,
            self.entity_description.option_key,
            int_value,
        )

    def _read_option_value(
        self,
        description: ZivyObrazNumberDescription,
    ) -> int:
        """Return stored value for a number description."""
        return int(
            get_config_value(
                self._entry,
                description.option_key,
                description.default_value,
            )
        )

    def _handle_options_update(self, changed_options: dict[str, object]) -> None:
        """Update HA state after runtime options changed."""
        if CONF_SCAN_INTERVAL in changed_options:
            self._scan_interval = int(changed_options[CONF_SCAN_INTERVAL])

        if self.entity_description.option_key in changed_options:
            self._native_value = int(changed_options[self.entity_description.option_key])
            self.schedule_update_ha_state()
            return

        if (
            self.entity_description.option_key == CONF_OVERDUE_TOLERANCE
            and CONF_SCAN_INTERVAL in changed_options
        ):
            self.schedule_update_ha_state()


class ZivyObrazSleepForcedNumber(
    CoordinatorEntity[ZivyObrazCoordinator],
    NumberEntity,
):
    """Refresh-disabled check interval for one Živý Obraz device."""

    _attr_has_entity_name = True
    _attr_translation_key = "sleep_forced"
    _attr_icon = "mdi:sleep"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 5
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: ZivyObrazCoordinator,
        mac: str,
        command_key: str,
        entry_id: str,
    ) -> None:
        """Initialize the forced sleep number."""
        super().__init__(coordinator)
        self._mac = mac
        self._command_key = command_key
        self._device_data_cache: dict[str, Any] = coordinator.data.get(mac, {})
        self._attr_unique_id = command_entity_unique_id(
            entry_id,
            mac,
            ATTR_SLEEP_FORCED,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated Export API data."""
        if self._mac in self.coordinator.data:
            self._device_data_cache = self.coordinator.data[self._mac]
        elif self.coordinator.last_update_success:
            self._device_data_cache = {}
        super()._handle_coordinator_update()

    @property
    def device_info(self):
        """Return device registry information."""
        if not self._device_data_cache:
            return DeviceInfo(identifiers={(DOMAIN, self._mac)})
        return build_device_info(self._mac, self._device_data_cache)

    @property
    def available(self) -> bool:
        """Return whether the forced sleep value is available."""
        return self._device_data_cache.get(ATTR_SLEEP_FORCED) is not None

    @property
    def native_value(self) -> int | None:
        """Return the forced sleep duration from Export API data."""
        value = self._device_data_cache.get(ATTR_SLEEP_FORCED)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the forced sleep duration through Command API."""
        int_value = round(value)
        int_value = max(int_value, int(self.native_min_value))
        int_value = min(int_value, int(self.native_max_value))
        target = f"device:{self._mac}"
        properties = {ATTR_SLEEP_FORCED: int_value}

        try:
            await self.coordinator.async_send_command(
                self._command_key,
                target,
                properties,
            )
        except ZivyObrazCommandError as err:
            raise HomeAssistantError(
                f"Živý Obraz command failed for {self._mac}: {err}"
            ) from err

        affected_macs = await self.coordinator.async_apply_local_command(
            target,
            target,
            properties,
        )
        if self._mac not in affected_macs:
            raise HomeAssistantError(
                f"Živý Obraz device {self._mac} is not available for command"
            )
