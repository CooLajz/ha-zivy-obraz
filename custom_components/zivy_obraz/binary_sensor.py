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
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_OVERDUE_TOLERANCE, DEFAULT_OVERDUE_TOLERANCE, DOMAIN
from .coordinator import ZivyObrazCoordinator


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

    def _build_entities_for_macs(macs: set[str]) -> list[ZivyObrazOverdueBinarySensor]:
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
        self._attr_unique_id = f"{mac}_{description.key}"

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return current device data."""
        return self.coordinator.data.get(self._mac, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        data = self._device_data
        caption = data.get("caption") or self._mac

        fw = data.get("fw")
        fw_build = data.get("fw_build")
        board_type = data.get("board_type")
        display_type = data.get("display_type")
        x = data.get("x")
        y = data.get("y")
        colors = data.get("colors")

        sw_version = None
        if fw and fw_build:
            sw_version = f"{fw} ({fw_build})"
        elif fw:
            sw_version = str(fw)

        model_parts: list[str] = []
        if display_type:
            model_parts.append(str(display_type))
        if x and y:
            model_parts.append(f"{x}x{y}")
        if colors:
            model_parts.append(str(colors))

        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=caption,
            manufacturer="Živý Obraz",
            model=" ".join(model_parts) if model_parts else None,
            hw_version=str(board_type) if board_type is not None else None,
            sw_version=sw_version,
        )

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

        overdue_after = next_contact + timedelta(minutes=self._overdue_tolerance_minutes)
        return dt_util.now() > overdue_after

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        next_contact = self._parse_next_contact()

        if next_contact is None:
            return {
                "mac": self._mac,
                "tolerance_minutes": self._overdue_tolerance_minutes,
                "next_contact": self._device_data.get("next_contact"),
                "minutes_overdue": None,
            }

        overdue_after = next_contact + timedelta(minutes=self._overdue_tolerance_minutes)
        delta_minutes = int((dt_util.now() - overdue_after).total_seconds() // 60)

        return {
            "mac": self._mac,
            "tolerance_minutes": self._overdue_tolerance_minutes,
            "next_contact": next_contact.isoformat(),
            "overdue_after": overdue_after.isoformat(),
            "minutes_overdue": max(delta_minutes, 0),
        }
