from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .config_helpers import async_update_option, get_config_value, options_update_signal
from .const import (
    CONF_OVERDUE_NOTIFICATION,
    CONF_PUSH_ENABLED,
    CONF_SEND_ONLY_CHANGED,
    DEFAULT_OVERDUE_NOTIFICATION,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_SEND_ONLY_CHANGED,
    DOMAIN,
)


@dataclass(frozen=True, kw_only=True)
class ZivyObrazSwitchDescription(SwitchEntityDescription):
    """Description for Živý Obraz config switch entity."""

    option_key: str
    default_value: bool


SWITCH_DESCRIPTIONS: tuple[ZivyObrazSwitchDescription, ...] = (
    ZivyObrazSwitchDescription(
        key="overdue_notification",
        translation_key="overdue_notification",
        option_key=CONF_OVERDUE_NOTIFICATION,
        default_value=DEFAULT_OVERDUE_NOTIFICATION,
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazSwitchDescription(
        key="push_enabled",
        translation_key="push_enabled",
        option_key=CONF_PUSH_ENABLED,
        default_value=DEFAULT_PUSH_ENABLED,
        entity_category=EntityCategory.CONFIG,
    ),
    ZivyObrazSwitchDescription(
        key="send_only_changed",
        translation_key="send_only_changed",
        option_key=CONF_SEND_ONLY_CHANGED,
        default_value=DEFAULT_SEND_ONLY_CHANGED,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Živý Obraz config switch entities."""
    async_add_entities(
        ZivyObrazConfigSwitch(hass, entry, description)
        for description in SWITCH_DESCRIPTIONS
    )


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
            identifiers={(DOMAIN, f"{entry.entry_id}_push")},
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
