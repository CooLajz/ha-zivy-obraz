from __future__ import annotations

import math
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .config_helpers import (
    async_update_option,
    async_update_options,
    get_config_value,
    options_update_signal,
)
from .const import (
    CONF_OVERDUE_TOLERANCE,
    CONF_PUSH_INTERVAL,
    CONF_SCAN_INTERVAL,
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
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Živý Obraz config number entities."""
    async_add_entities(
        ZivyObrazConfigNumber(hass, entry, description)
        for description in NUMBER_DESCRIPTIONS
    )


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
            self.async_write_ha_state()
            return

        if (
            self.entity_description.option_key == CONF_OVERDUE_TOLERANCE
            and CONF_SCAN_INTERVAL in changed_options
        ):
            self.async_write_ha_state()
