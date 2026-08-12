from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_helpers import async_update_option, get_config_value, options_update_signal
from .const import (
    ATTR_OTA,
    ATTR_REFRESH_SCREEN,
    ATTR_ROTATE_180,
    ATTR_SHOW_AP_CONNECT_SCREEN,
    CONF_COMMAND_KEY,
    CONF_IMPORT_KEY,
    CONF_OVERDUE_NOTIFICATION,
    CONF_PUSH_ENABLED,
    CONF_REPLACE_INVALID_STATES_WITH_NA,
    CONF_SEND_ONLY_CHANGED,
    DEFAULT_COMMAND_KEY,
    DEFAULT_IMPORT_KEY,
    DEFAULT_OVERDUE_NOTIFICATION,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_REPLACE_INVALID_STATES_WITH_NA,
    DEFAULT_SEND_ONLY_CHANGED,
    DOMAIN,
)
from .command import ZivyObrazCommandError
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info, diagnostic_device_identifier

PUSH_SWITCH_KEYS = {
    CONF_PUSH_ENABLED,
    CONF_REPLACE_INVALID_STATES_WITH_NA,
    CONF_SEND_ONLY_CHANGED,
}


@dataclass(frozen=True, kw_only=True)
class ZivyObrazSwitchDescription(SwitchEntityDescription):
    """Description for Živý Obraz config switch entity."""

    option_key: str
    default_value: bool


@dataclass(frozen=True, kw_only=True)
class ZivyObrazCommandSwitchDescription(SwitchEntityDescription):
    """Description for Živý Obraz device command switch entity."""

    command_property: str
    data_key: str

    def __post_init__(self) -> None:
        """Use the entity key as the default translation key."""
        if self.translation_key is None:
            object.__setattr__(self, "translation_key", self.key)
        object.__setattr__(self, "name", None)


SWITCH_DESCRIPTIONS: tuple[ZivyObrazSwitchDescription, ...] = (
    ZivyObrazSwitchDescription(
        key="overdue_notification",
        translation_key="overdue_notification",
        option_key=CONF_OVERDUE_NOTIFICATION,
        default_value=DEFAULT_OVERDUE_NOTIFICATION,
        icon="mdi:bell-alert",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazSwitchDescription(
        key="push_enabled",
        translation_key="push_enabled",
        option_key=CONF_PUSH_ENABLED,
        default_value=DEFAULT_PUSH_ENABLED,
        icon="mdi:cloud-upload-outline",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazSwitchDescription(
        key="send_only_changed",
        translation_key="send_only_changed",
        option_key=CONF_SEND_ONLY_CHANGED,
        default_value=DEFAULT_SEND_ONLY_CHANGED,
        icon="mdi:delta",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazSwitchDescription(
        key="replace_invalid_states_with_na",
        translation_key="replace_invalid_states_with_na",
        option_key=CONF_REPLACE_INVALID_STATES_WITH_NA,
        default_value=DEFAULT_REPLACE_INVALID_STATES_WITH_NA,
        icon="mdi:cloud-question-outline",
        entity_category=EntityCategory.CONFIG,
    ),
)

COMMAND_SWITCH_DESCRIPTIONS: tuple[ZivyObrazCommandSwitchDescription, ...] = (
    ZivyObrazCommandSwitchDescription(
        key="ota",
        translation_key="ota",
        command_property=ATTR_OTA,
        data_key="ota",
        icon="mdi:cellphone-arrow-down",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazCommandSwitchDescription(
        key="refresh_screen",
        translation_key="refresh_screen",
        command_property=ATTR_REFRESH_SCREEN,
        data_key="refresh_screen",
        icon="mdi:monitor-screenshot",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazCommandSwitchDescription(
        key="rotate_180",
        translation_key="rotate_180",
        command_property=ATTR_ROTATE_180,
        data_key="rotate_180",
        icon="mdi:rotate-3d-variant",
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazCommandSwitchDescription(
        key="show_ap_connect_screen",
        translation_key="show_ap_connect_screen",
        command_property=ATTR_SHOW_AP_CONNECT_SCREEN,
        data_key="show_ap_connect_screen",
        icon="mdi:wifi-cog",
        entity_category=EntityCategory.CONFIG,
    ),
)

COMMAND_SWITCH_KEYS = {description.key for description in COMMAND_SWITCH_DESCRIPTIONS}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Živý Obraz config switch entities."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data
    has_import_key = bool(
        str(get_config_value(entry, CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY) or "").strip()
    )
    command_key = str(
        get_config_value(entry, CONF_COMMAND_KEY, DEFAULT_COMMAND_KEY) or ""
    )
    command_key = command_key.strip()
    has_command_key = bool(command_key)
    if not has_import_key:
        _remove_push_config_switches(hass, entry)
    if not has_command_key:
        _remove_command_device_switches(hass, entry)

    entities: list[SwitchEntity] = [
        ZivyObrazConfigSwitch(hass, entry, description)
        for description in SWITCH_DESCRIPTIONS
        if has_import_key or description.key not in PUSH_SWITCH_KEYS
    ]

    known_command_entity_ids: set[str] = set()

    def _build_command_switches_for_macs(
        macs: set[str],
    ) -> list[ZivyObrazCommandSwitch]:
        command_switches: list[ZivyObrazCommandSwitch] = []

        if not has_command_key:
            return command_switches

        for mac in macs:
            for description in COMMAND_SWITCH_DESCRIPTIONS:
                unique_id = f"{mac}_{description.key}"
                if unique_id in known_command_entity_ids:
                    continue

                known_command_entity_ids.add(unique_id)
                command_switches.append(
                    ZivyObrazCommandSwitch(
                        coordinator,
                        mac,
                        description,
                        command_key,
                    )
                )

        return command_switches

    entities.extend(_build_command_switches_for_macs(set(coordinator.data.keys())))

    async_add_entities(entities)

    if has_command_key:

        @callback
        def _handle_new_devices(new_macs: set[str]) -> None:
            new_entities = _build_command_switches_for_macs(new_macs)
            if new_entities:
                async_add_entities(new_entities)

        entry.async_on_unload(
            coordinator.async_add_new_device_listener(_handle_new_devices)
        )


@callback
def _remove_push_config_switches(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove push config switches when Import key is not configured."""
    entity_registry = er.async_get(hass)
    obsolete_unique_ids = {f"{entry.entry_id}_{key}" for key in PUSH_SWITCH_KEYS}

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "switch":
            continue
        if entity_entry.unique_id not in obsolete_unique_ids:
            continue
        entity_registry.async_remove(entity_entry.entity_id)


@callback
def _remove_command_device_switches(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove command switches when Command key is not configured."""
    entity_registry = er.async_get(hass)
    suffixes = {f"_{key}" for key in COMMAND_SWITCH_KEYS}

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "switch":
            continue
        if not any(entity_entry.unique_id.endswith(suffix) for suffix in suffixes):
            continue
        entity_registry.async_remove(entity_entry.entity_id)


class ZivyObrazConfigSwitch(SwitchEntity):
    """Representation of a Živý Obraz config switch entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        description: ZivyObrazSwitchDescription,
    ) -> None:
        """Initialize config switch entity."""
        self.hass = hass
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
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
    def is_on(self) -> bool:
        """Return current option value."""
        return bool(
            get_config_value(
                self._entry,
                self.entity_description.option_key,
                self.entity_description.default_value,
            )
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the option on."""
        await async_update_option(
            self.hass,
            self._entry,
            self.entity_description.option_key,
            True,
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the option off."""
        await async_update_option(
            self.hass,
            self._entry,
            self.entity_description.option_key,
            False,
        )

    def _handle_options_update(self, changed_options: dict[str, object]) -> None:
        """Update HA state after runtime options changed."""
        if self.entity_description.option_key in changed_options:
            self.schedule_update_ha_state()


def _coerce_bool_state(value: Any) -> bool:
    """Return a stable boolean state from common API bool representations."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"", "0", "false", "no", "off"}:
        return False

    return bool(value)


class ZivyObrazCommandSwitch(
    CoordinatorEntity[ZivyObrazCoordinator],
    SwitchEntity,
):
    """Representation of one Živý Obraz Command API switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZivyObrazCoordinator,
        mac: str,
        description: ZivyObrazCommandSwitchDescription,
        command_key: str,
    ) -> None:
        """Initialize the command switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._command_key = command_key
        self._device_data_cache: dict[str, Any] = coordinator.data.get(mac, {})
        self._attr_unique_id = f"{mac}_{description.key}"

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
        return bool(self._device_data)

    @property
    def is_on(self) -> bool:
        """Return current command state."""
        return _coerce_bool_state(
            self._device_data.get(self.entity_description.data_key)
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the command property on."""
        await self._async_set_command_value(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the command property off."""
        await self._async_set_command_value(False)

    async def _async_set_command_value(self, value: bool) -> None:
        """Apply one device command."""
        target = f"device:{self._mac}"
        properties = {self.entity_description.command_property: value}

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
