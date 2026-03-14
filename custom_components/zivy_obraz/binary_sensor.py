from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
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

from .const import (
    CONF_OVERDUE_NOTIFICATION,
    CONF_OVERDUE_TOLERANCE,
    DEFAULT_OVERDUE_NOTIFICATION,
    DEFAULT_OVERDUE_TOLERANCE,
)
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
    overdue_notification = entry.options.get(
        CONF_OVERDUE_NOTIFICATION,
        entry.data.get(CONF_OVERDUE_NOTIFICATION, DEFAULT_OVERDUE_NOTIFICATION),
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
                        overdue_notification,
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
        overdue_notification: bool,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._overdue_tolerance_minutes = overdue_tolerance_minutes
        self._overdue_notification = overdue_notification
        self._device_data_cache: dict[str, Any] = coordinator.data.get(mac, {})
        self._attr_unique_id = f"{mac}_{description.key}"
        self._last_overdue_state: bool | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        self._device_data_cache = self.coordinator.data.get(self._mac, {})

        current_state = self.is_on
        if self._overdue_notification and current_state != self._last_overdue_state:
            if current_state is True:
                self.hass.async_create_task(self._async_create_notification())
            elif self._last_overdue_state is True and current_state is False:
                self.hass.async_create_task(self._async_dismiss_notification())

        self._last_overdue_state = current_state
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        self._device_data_cache = self.coordinator.data.get(self._mac, {})
        self._last_overdue_state = self.is_on

        if self._overdue_notification and self._last_overdue_state is True:
            await self._async_create_notification()

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

    def _expected_contact_minutes_ago(self) -> int | None:
        """Return minutes since expected contact time."""
        next_contact = self._parse_next_contact()
        if next_contact is None:
            return None

        delta_minutes = int((dt_util.now() - next_contact).total_seconds() // 60)
        return max(delta_minutes, 0)

    def _minutes_overdue(self) -> int | None:
        """Return how many minutes the panel is overdue after tolerance."""
        next_contact = self._parse_next_contact()
        if next_contact is None:
            return None

        overdue_after = next_contact + timedelta(
            minutes=self._overdue_tolerance_minutes
        )
        delta_minutes = int((dt_util.now() - overdue_after).total_seconds() // 60)
        return max(delta_minutes, 0)

    def _overdue_after(self) -> datetime | None:
        """Return datetime when panel becomes overdue."""
        next_contact = self._parse_next_contact()
        if next_contact is None:
            return None

        return next_contact + timedelta(minutes=self._overdue_tolerance_minutes)

    def _format_local_datetime(self, value: datetime | None) -> str | None:
        """Format datetime in local HA timezone."""
        if value is None:
            return None

        local_value = dt_util.as_local(value)
        return local_value.strftime("%d.%m.%Y %H:%M:%S")

    @property
    def is_on(self) -> bool | None:
        """Return whether the panel is overdue."""
        overdue_after = self._overdue_after()
        if overdue_after is None:
            return None

        return dt_util.now() > overdue_after

    def _notification_id(self) -> str:
        """Return persistent notification ID."""
        return f"zivy_obraz_overdue_{self._mac.replace(':', '').lower()}"

    async def _async_create_notification(self) -> None:
        """Create/update overdue notification."""
        caption = self._device_data.get("caption") or self._mac
        group_name = self._device_data.get("group_name")

        expected_contact_minutes_ago = self._expected_contact_minutes_ago()
        minutes_overdue = self._minutes_overdue()
        next_contact = self._parse_next_contact()
        overdue_after = self._overdue_after()

        lines: list[str] = []

        if expected_contact_minutes_ago is not None:
            lines.append(
                f'Displej "{caption}" je po očekávaném kontaktu již '
                f"{expected_contact_minutes_ago} minut."
            )
        else:
            lines.append(f'Displej "{caption}" se nehlásí v očekávaném čase.')

        if group_name:
            lines.append("")
            lines.append(f"Skupina: {group_name}")

        lines.append(f"Tolerance overdue: {self._overdue_tolerance_minutes} minut")

        if minutes_overdue is not None:
            lines.append(f"Po překročení tolerance: {minutes_overdue} minut")

        formatted_next_contact = self._format_local_datetime(next_contact)
        if formatted_next_contact:
            lines.append(f"Poslední očekávaný kontakt: {formatted_next_contact}")

        formatted_overdue_after = self._format_local_datetime(overdue_after)
        if formatted_overdue_after:
            lines.append(f"Za overdue označen od: {formatted_overdue_after}")

        persistent_notification.async_create(
            self.hass,
            message="\n".join(lines),
            title="Živý Obraz - Overdue displej",
            notification_id=self._notification_id(),
        )

    async def _async_dismiss_notification(self) -> None:
        """Dismiss overdue notification."""
        persistent_notification.async_dismiss(
            self.hass,
            notification_id=self._notification_id(),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for overdue sensor."""
        next_contact = self._parse_next_contact()
        overdue_after = self._overdue_after()

        if next_contact is None:
            return {
                "tolerance_minutes": self._overdue_tolerance_minutes,
                "next_contact": self._device_data.get("next_contact"),
                "minutes_since_expected_contact": None,
                "minutes_overdue": None,
            }

        expected_contact_minutes_ago = int(
            (dt_util.now() - next_contact).total_seconds() // 60
        )

        delta_minutes = 0
        if overdue_after is not None:
            delta_minutes = int((dt_util.now() - overdue_after).total_seconds() // 60)

        return {
            "tolerance_minutes": self._overdue_tolerance_minutes,
            "next_contact": next_contact.isoformat(),
            "overdue_after": overdue_after.isoformat() if overdue_after else None,
            "minutes_since_expected_contact": max(expected_contact_minutes_ago, 0),
            "minutes_overdue": max(delta_minutes, 0),
        }
