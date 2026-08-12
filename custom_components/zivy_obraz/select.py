from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .command import ZivyObrazCommandError
from .config_helpers import get_config_value
from .const import (
    ATTR_INVERT_SCREEN,
    CONF_COMMAND_KEY,
    DEFAULT_COMMAND_KEY,
    DOMAIN,
)
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info

INVERT_SCREEN_DEFAULT = "default"
INVERT_SCREEN_ENABLED = "invert"
INVERT_SCREEN_DISABLED = "do_not_invert"
INVERT_SCREEN_OPTIONS = [
    INVERT_SCREEN_DEFAULT,
    INVERT_SCREEN_ENABLED,
    INVERT_SCREEN_DISABLED,
]
INVERT_SCREEN_VALUES = {
    INVERT_SCREEN_DEFAULT: None,
    INVERT_SCREEN_ENABLED: True,
    INVERT_SCREEN_DISABLED: False,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Živý Obraz command select entities."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data
    command_key = str(
        get_config_value(entry, CONF_COMMAND_KEY, DEFAULT_COMMAND_KEY) or ""
    ).strip()

    if not command_key:
        _remove_invert_screen_selects(hass, entry)
        return

    known_entity_ids: set[str] = set()

    def _build_entities(macs: set[str]) -> list[ZivyObrazInvertScreenSelect]:
        entities: list[ZivyObrazInvertScreenSelect] = []
        for mac in macs:
            unique_id = f"{mac}_invert_screen"
            if unique_id in known_entity_ids:
                continue
            known_entity_ids.add(unique_id)
            entities.append(
                ZivyObrazInvertScreenSelect(coordinator, mac, command_key)
            )
        return entities

    async_add_entities(_build_entities(set(coordinator.data)))

    @callback
    def _handle_new_devices(new_macs: set[str]) -> None:
        new_entities = _build_entities(new_macs)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        coordinator.async_add_new_device_listener(_handle_new_devices)
    )


@callback
def _remove_invert_screen_selects(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove invert screen selects when Command key is not configured."""
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "select":
            continue
        if not entity_entry.unique_id.endswith("_invert_screen"):
            continue
        entity_registry.async_remove(entity_entry.entity_id)


class ZivyObrazInvertScreenSelect(
    CoordinatorEntity[ZivyObrazCoordinator],
    SelectEntity,
):
    """Select the display color inversion behavior."""

    _attr_has_entity_name = True
    _attr_translation_key = "invert_screen"
    _attr_icon = "mdi:invert-colors"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = INVERT_SCREEN_OPTIONS

    def __init__(
        self,
        coordinator: ZivyObrazCoordinator,
        mac: str,
        command_key: str,
    ) -> None:
        """Initialize the invert screen select."""
        super().__init__(coordinator)
        self._mac = mac
        self._command_key = command_key
        self._device_data_cache: dict[str, Any] = coordinator.data.get(mac, {})
        self._attr_unique_id = f"{mac}_invert_screen"

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
        """Return whether current device data is available."""
        return bool(self._device_data_cache)

    @property
    def current_option(self) -> str | None:
        """Return the current inversion behavior from Export API data."""
        value = self._device_data_cache.get(ATTR_INVERT_SCREEN)
        if value is None:
            return INVERT_SCREEN_DEFAULT
        if value is True:
            return INVERT_SCREEN_ENABLED
        if value is False:
            return INVERT_SCREEN_DISABLED
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the inversion behavior through Command API."""
        if option not in INVERT_SCREEN_VALUES:
            raise HomeAssistantError(f"Unsupported invert screen option: {option}")

        target = f"device:{self._mac}"
        properties = {ATTR_INVERT_SCREEN: INVERT_SCREEN_VALUES[option]}

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
