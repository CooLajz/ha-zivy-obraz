from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ZivyObrazCoordinator
from .device import diagnostic_device_identifier
from .push import ZivyObrazPushManager


@dataclass(frozen=True, kw_only=True)
class ZivyObrazButtonDescription(ButtonEntityDescription):
    """Description for Živý Obraz action button."""

    press_action: str


BUTTON_DESCRIPTIONS: tuple[ZivyObrazButtonDescription, ...] = (
    ZivyObrazButtonDescription(
        key="refresh_import",
        translation_key="refresh_import",
        press_action="refresh_import",
    ),
    ZivyObrazButtonDescription(
        key="push_now",
        translation_key="push_now",
        press_action="push_now",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Živý Obraz action buttons."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data

    def _push_manager() -> ZivyObrazPushManager | None:
        return hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("push_manager")

    async def _async_push_now() -> None:
        push_manager = _push_manager()
        if push_manager is not None:
            await push_manager.async_push()

    entities: list[ZivyObrazButton] = [
        ZivyObrazButton(
            entry,
            BUTTON_DESCRIPTIONS[0],
            available=lambda: True,
            press_action=coordinator.async_request_manual_refresh,
        ),
        ZivyObrazButton(
            entry,
            BUTTON_DESCRIPTIONS[1],
            available=lambda: _push_manager() is not None,
            press_action=_async_push_now,
        ),
    ]

    async_add_entities(entities)


class ZivyObrazButton(ButtonEntity):
    """Representation of a Živý Obraz action button."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        description: ZivyObrazButtonDescription,
        available: Callable[[], bool],
        press_action: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize action button."""
        self.entity_description = description
        self._available = available
        self._press_action = press_action
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={diagnostic_device_identifier(entry)},
            name=f"Živý Obraz - {entry.title}",
            manufacturer="Živý Obraz",
        )

    @property
    def available(self) -> bool:
        """Return whether button can be pressed."""
        return self._available()

    async def async_press(self) -> None:
        """Handle button press."""
        await self._press_action()
