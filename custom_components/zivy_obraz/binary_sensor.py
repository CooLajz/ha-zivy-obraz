from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_OVERDUE_TOLERANCE, DEFAULT_OVERDUE_TOLERANCE
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info


@dataclass(frozen=True, kw_only=True)
class ZivyObrazBinarySensorDescription(BinarySensorEntityDescription):
    """Description for Zivy Obraz binary sensor."""


BINARY_SENSOR_DESCRIPTIONS: tuple[ZivyObrazBinarySensorDescription, ...] = (
    ZivyObrazBinarySensorDescription(
        key="overdue",
        name="Overdue",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zivy Obraz binary sensors from a config entry."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data
    overdue_tolerance_minutes = entry.options.get(
        CONF_OVERDUE_TOLERANCE,
        entry.data.get(CONF_OVERDUE_TOLERANCE, DEFAULT_OVERDUE_TOLERANCE),
    )
    known_entity_ids: set[str] = set()

    def _build_entities_for_macs(
        macs: set[str],
    ) -> list[ZivyObrazOverdueBinarySensor]:
        entities: list[ZivyObrazOverdueBinarySensor] = []

        for mac in macs:
            for description in BINARY_SENSOR_DESCRIPTIONS:
                unique_id = f"{mac}_{description.key}"
                if unique_id in known_entity_ids:
                    continue

                known_entity_ids.add(unique_id)
                entities.append(
                    ZivyObrazOverdueBinarySensor(
                        coordinator,
                        mac,
                        description,
                        overdue_tolerance_minutes,
                    )
                )

        return entities

    initial_entities = _build_entities_for_macs(set(coordinator.data.keys()))
    if initial_entities:
        async_add_entities(initial_entities)

    @callback
    def _handle_new_devices(new_macs: set[str]) -> None:
        new_entities = _build_entities_for_macs(new_macs)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_new_device_listener(_handle_new_devices))


class ZivyObrazOverdueBinarySensor(
    CoordinatorEntity[ZivyObrazCoordinator],
    BinarySensorEntity,
):
    """Binary sensor indicating whether the panel is overdue."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZivyObrazCoordinator,
        mac: str,
        description: ZivyObrazBinarySensorDescription,
        overdue_tolerance_minutes: int,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._overdue_tolerance_minutes = overdue_tolerance_minutes
        self._device_data_cache: dict[str, Any] = coordinator.data.get(mac, {})
        self._attr_unique_id = f"{mac}_{description.key}"

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

    def _parse_next_contact(self) -> datetime | None:
        """Parse next_contact timestamp."""
        value = self._device_data.get("next_contact")
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                parsed = dt_util.as_local(parsed)
            return parsed
        except (TypeError, ValueError):
            return None

    @property
    def is_on(self) -> bool | None:
        """Return whether the panel is overdue."""
        next_contact = self._parse_next_contact()
        if next_contact is None:
            return None

        overdue_after = next_contact + timedelta(
            minutes=self._overdue_tolerance_minutes
        )
        return dt_util.now() > overdue_after

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for overdue sensor."""
        next_contact = self._parse_next_contact()

        if next_contact is None:
            return {
                "tolerance_minutes": self._overdue_tolerance_minutes,
                "next_contact": self._device_data.get("next_contact"),
                "minutes_overdue": None,
            }

        overdue_after = next_contact + timedelta(
            minutes=self._overdue_tolerance_minutes
        )
        delta_minutes = int((dt_util.now() - overdue_after).total_seconds() // 60)

        return {
            "tolerance_minutes": self._overdue_tolerance_minutes,
            "next_contact": next_contact.isoformat(),
            "overdue_after": overdue_after.isoformat(),
            "minutes_overdue": max(delta_minutes, 0),
        }
