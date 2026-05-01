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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .config_helpers import get_config_value, options_update_signal
from .const import (
    CONF_OVERDUE_NOTIFICATION,
    CONF_OVERDUE_TOLERANCE,
    DEFAULT_OVERDUE_NOTIFICATION,
    DEFAULT_OVERDUE_TOLERANCE,
    DOMAIN,
)
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info, diagnostic_device_identifier
from .push import PUSH_PROBLEM_STATUSES, ZivyObrazPushManager


@dataclass(frozen=True, kw_only=True)
class ZivyObrazBinarySensorDescription(BinarySensorEntityDescription):
    """Description for Zivy Obraz binary sensor."""


BINARY_SENSOR_DESCRIPTIONS: tuple[ZivyObrazBinarySensorDescription, ...] = (
    ZivyObrazBinarySensorDescription(
        key="overdue",
        name="Overdue",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:timer-alert-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

SYNC_PROBLEM_STATUSES = {"failed"}


class ZivyObrazProblemNotificationMixin:
    """Notification handling shared by integration problem sensors."""

    _entry: ConfigEntry
    _last_problem_state: bool | None = None
    _problem_notification_active: bool = False

    @property
    def _problem_notification_enabled(self) -> bool:
        """Return whether problem notifications are enabled."""
        return bool(
            get_config_value(
                self._entry,
                CONF_OVERDUE_NOTIFICATION,
                DEFAULT_OVERDUE_NOTIFICATION,
            )
        )

    @callback
    def _handle_problem_update(self) -> None:
        """Handle updated diagnostic state."""
        self._sync_problem_notification()
        self.async_write_ha_state()

    @callback
    def _handle_problem_options_update(self, changed_options: dict[str, object]) -> None:
        """Handle runtime option changes affecting problem notifications."""
        if CONF_OVERDUE_NOTIFICATION not in changed_options:
            return

        self._sync_problem_notification()

    def _sync_problem_notification(self) -> None:
        """Create or dismiss the problem notification for current state."""
        current_state = self.is_on
        notification_enabled = self._problem_notification_enabled

        if notification_enabled and current_state is True:
            if (
                self._last_problem_state is not True
                or not self._problem_notification_active
            ):
                self.hass.async_create_task(self._async_create_problem_notification())
                self._problem_notification_active = True
        else:
            if (
                self._problem_notification_active
                or (current_state is False and self._last_problem_state is True)
                or (
                    not notification_enabled
                    and current_state is True
                    and self._last_problem_state is not True
                )
            ):
                self.hass.async_create_task(self._async_dismiss_problem_notification())
            self._problem_notification_active = False

        self._last_problem_state = current_state

    def _format_problem_datetime(self, value: Any) -> str | None:
        """Format a diagnostic datetime in local HA timezone."""
        if value is None:
            return None

        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value))
            except (TypeError, ValueError):
                return str(value)

        return dt_util.as_local(parsed).strftime("%d.%m.%Y %H:%M:%S")

    async def _async_create_problem_notification(self) -> None:
        """Create/update the problem notification."""
        raise NotImplementedError

    async def _async_dismiss_problem_notification(self) -> None:
        """Dismiss the problem notification."""
        persistent_notification.async_dismiss(
            self.hass,
            notification_id=self._problem_notification_id,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zivy Obraz binary sensors from a config entry."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data
    push_manager: ZivyObrazPushManager | None = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("push_manager")
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
                        entry,
                        coordinator,
                        mac,
                        description,
                    )
                )

        return entities

    def _registered_macs_for_description(
        description: ZivyObrazBinarySensorDescription,
    ) -> set[str]:
        """Return MACs for previously registered binary sensors of this entry."""
        entity_registry = er.async_get(hass)
        suffix = f"_{description.key}"
        macs: set[str] = set()

        for entity_entry in er.async_entries_for_config_entry(
            entity_registry,
            entry.entry_id,
        ):
            if entity_entry.domain != "binary_sensor":
                continue
            if not entity_entry.unique_id.endswith(suffix):
                continue
            mac = entity_entry.unique_id.removesuffix(suffix)
            if mac:
                macs.add(mac)

        return macs

    def _build_restored_entities() -> list[ZivyObrazOverdueBinarySensor]:
        """Recreate previously registered overdue sensors before fresh data arrives."""
        entities: list[ZivyObrazOverdueBinarySensor] = []

        for description in BINARY_SENSOR_DESCRIPTIONS:
            for mac in _registered_macs_for_description(description):
                unique_id = f"{mac}_{description.key}"
                if unique_id in known_entity_ids:
                    continue

                known_entity_ids.add(unique_id)
                entities.append(
                    ZivyObrazOverdueBinarySensor(
                        entry,
                        coordinator,
                        mac,
                        description,
                    )
                )

        return entities

    initial_entities = _build_entities_for_macs(set(coordinator.data.keys()))
    initial_entities.extend(_build_restored_entities())
    initial_entities.append(ZivyObrazSyncProblemBinarySensor(entry, coordinator))
    if push_manager is not None:
        initial_entities.append(ZivyObrazPushProblemBinarySensor(entry, push_manager))

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
    RestoreEntity,
):
    """Binary sensor indicating whether the panel is overdue."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ZivyObrazCoordinator,
        mac: str,
        description: ZivyObrazBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._mac = mac
        self._device_data_cache: dict[str, Any] = coordinator.data.get(mac, {})
        self._restored_is_on: bool | None = None
        self._attr_unique_id = f"{mac}_{description.key}"
        self._last_overdue_state: bool | None = None

    @property
    def _overdue_tolerance_minutes(self) -> int:
        """Return current overdue tolerance in minutes."""
        return int(
            get_config_value(
                self._entry,
                CONF_OVERDUE_TOLERANCE,
                DEFAULT_OVERDUE_TOLERANCE,
            )
        )

    @property
    def _overdue_notification(self) -> bool:
        """Return whether overdue notifications are enabled."""
        return bool(
            get_config_value(
                self._entry,
                CONF_OVERDUE_NOTIFICATION,
                DEFAULT_OVERDUE_NOTIFICATION,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        if self._mac in self.coordinator.data:
            self._device_data_cache = self.coordinator.data[self._mac]
        elif self.coordinator.last_update_success:
            self._device_data_cache = {}

        current_state = self.is_on
        if self._overdue_notification and current_state != self._last_overdue_state:
            if current_state is True:
                self.hass.async_create_task(self._async_create_notification())
            elif self._last_overdue_state is True and current_state is False:
                self.hass.async_create_task(self._async_dismiss_notification())
        elif not self._overdue_notification and self._last_overdue_state is True:
            self.hass.async_create_task(self._async_dismiss_notification())

        self._last_overdue_state = current_state
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._restored_is_on = self._restore_is_on(last_state.state)
            next_contact = last_state.attributes.get("next_contact")
            if next_contact:
                self._device_data_cache = {"next_contact": next_contact}
        fresh_device_data = self.coordinator.data.get(self._mac, {})
        if fresh_device_data:
            self._device_data_cache = fresh_device_data
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
        if not self._device_data or set(self._device_data) == {"next_contact"}:
            return DeviceInfo(identifiers={(DOMAIN, self._mac)})
        return build_device_info(self._mac, self._device_data)

    @property
    def available(self) -> bool:
        """Return availability."""
        return bool(self._device_data) or self._restored_is_on is not None

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
        if not self._device_data and self._restored_is_on is not None:
            return self._restored_is_on

        overdue_after = self._overdue_after()
        if overdue_after is None:
            return None

        return dt_util.now() > overdue_after

    def _restore_is_on(self, state: str) -> bool | None:
        """Convert restored HA state to a binary sensor value."""
        if state == "on":
            return True
        if state == "off":
            return False
        return None

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


class ZivyObrazPushProblemBinarySensor(
    ZivyObrazProblemNotificationMixin,
    BinarySensorEntity,
):
    """Binary sensor indicating whether the last push attempt had a problem."""

    _attr_has_entity_name = True
    _attr_name = "Push problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:cloud-alert-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: ConfigEntry,
        push_manager: ZivyObrazPushManager,
    ) -> None:
        """Initialize the push problem binary sensor."""
        self._entry = entry
        self._push_manager = push_manager
        self._attr_unique_id = f"{entry.entry_id}_push_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={diagnostic_device_identifier(entry)},
            name=f"Živý Obraz - {entry.title}",
            manufacturer="Živý Obraz",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._push_manager.async_add_listener(self._handle_problem_update)
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                options_update_signal(self._entry.entry_id),
                self._handle_problem_options_update,
            )
        )
        self._sync_problem_notification()

    @property
    def is_on(self) -> bool:
        """Return whether the last push attempt had a problem."""
        return self._push_manager.diagnostics.status in PUSH_PROBLEM_STATUSES

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return current push problem details."""
        diagnostics = self._push_manager.diagnostics
        return {
            "status": diagnostics.status,
            "last_error": diagnostics.last_error,
            "last_push": diagnostics.last_push.isoformat()
            if diagnostics.last_push
            else None,
        }

    @property
    def _problem_notification_id(self) -> str:
        """Return persistent notification ID."""
        return f"zivy_obraz_push_problem_{self._entry.entry_id}"

    async def _async_create_problem_notification(self) -> None:
        """Create/update push problem notification."""
        diagnostics = self._push_manager.diagnostics
        lines = [
            "Odesílání hodnot do Živého Obrazu hlásí problém.",
            "",
            f"Instance: {self._entry.title}",
            f"Stav: {diagnostics.status}",
        ]

        if diagnostics.last_error:
            lines.append(f"Důvod: {diagnostics.last_error}")

        formatted_last_push = self._format_problem_datetime(diagnostics.last_push)
        if formatted_last_push:
            lines.append(f"Poslední pokus o odeslání: {formatted_last_push}")

        if diagnostics.failed_entities:
            lines.append(f"Neodeslané entity: {diagnostics.failed_entities}")

        persistent_notification.async_create(
            self.hass,
            message="\n".join(lines),
            title=f"Živý Obraz - Problém odesílání ({self._entry.title})",
            notification_id=self._problem_notification_id,
        )


class ZivyObrazSyncProblemBinarySensor(
    ZivyObrazProblemNotificationMixin,
    BinarySensorEntity,
):
    """Binary sensor indicating whether the last sync attempt had a problem."""

    _attr_has_entity_name = True
    _attr_name = "Sync problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:sync-alert"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ZivyObrazCoordinator,
    ) -> None:
        """Initialize the sync problem binary sensor."""
        self._entry = entry
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_sync_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={diagnostic_device_identifier(entry)},
            name=f"Živý Obraz - {entry.title}",
            manufacturer="Živý Obraz",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_problem_update)
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                options_update_signal(self._entry.entry_id),
                self._handle_problem_options_update,
            )
        )
        self._sync_problem_notification()

    @property
    def is_on(self) -> bool:
        """Return whether the last sync attempt had a problem."""
        return self._coordinator.diagnostics.status in SYNC_PROBLEM_STATUSES

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return current sync problem details."""
        diagnostics = self._coordinator.diagnostics
        return {
            "status": diagnostics.status,
            "last_error": diagnostics.last_error,
            "last_sync": diagnostics.last_sync.isoformat()
            if diagnostics.last_sync
            else None,
        }

    @property
    def _problem_notification_id(self) -> str:
        """Return persistent notification ID."""
        return f"zivy_obraz_sync_problem_{self._entry.entry_id}"

    async def _async_create_problem_notification(self) -> None:
        """Create/update sync problem notification."""
        diagnostics = self._coordinator.diagnostics
        lines = [
            "Synchronizace dat ze Živého Obrazu hlásí problém.",
            "",
            f"Instance: {self._entry.title}",
            f"Stav: {diagnostics.status}",
        ]

        if diagnostics.last_error:
            lines.append(f"Důvod: {diagnostics.last_error}")

        formatted_last_sync = self._format_problem_datetime(diagnostics.last_sync)
        if formatted_last_sync:
            lines.append(f"Poslední pokus o synchronizaci: {formatted_last_sync}")

        persistent_notification.async_create(
            self.hass,
            message="\n".join(lines),
            title=f"Živý Obraz - Problém synchronizace ({self._entry.title})",
            notification_id=self._problem_notification_id,
        )
