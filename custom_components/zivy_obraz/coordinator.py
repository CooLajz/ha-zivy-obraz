from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import json
import logging
import re
from typing import Any, Callable

from aiohttp import ClientError, ClientResponseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import normalize_export_payload
from .battery import BatteryChargeTracker
from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, DOMAIN
from .device import build_device_name, build_device_registry_metadata
from .display_activity import DisplayActivityTracker

_LOGGER = logging.getLogger(__name__)
BATTERY_STORAGE_VERSION = 1
DISPLAY_ACTIVITY_STORAGE_VERSION = 1

_PANEL_MAC_RE = re.compile(
    r"^(?:"
    r"[0-9a-f]{12}|"
    r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}|"
    r"[0-9a-f]{2}(?:-[0-9a-f]{2}){5}"
    r")$"
)


def _is_panel_mac(value: str) -> bool:
    """Return True when an identifier looks like a panel MAC address."""
    return _PANEL_MAC_RE.fullmatch(value.lower()) is not None


@dataclass
class SyncDiagnostics:
    """Diagnostic state for Export API synchronization."""

    status: str = "idle"
    last_sync: Any = None
    last_successful_sync: Any = None
    next_sync: Any = None
    device_count: int = 0
    last_error: str | None = None


class ZivyObrazCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for Živý Obraz endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        config_entry: ConfigEntry,
        timeout: int | None = None,
        update_interval_seconds: int | None = None,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=update_interval_seconds or DEFAULT_SCAN_INTERVAL
            ),
            always_update=False,
        )
        self.url = url
        self.config_entry = config_entry
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.session = async_get_clientsession(hass)
        self.known_macs: set[str] = set()
        self._new_device_listeners: list[Callable[[set[str]], None]] = []
        self.diagnostics = SyncDiagnostics()
        self.battery_tracker = BatteryChargeTracker()
        self.display_activity_tracker = DisplayActivityTracker()
        self._battery_store = Store(
            hass,
            BATTERY_STORAGE_VERSION,
            f"{DOMAIN}_battery_charge_{config_entry.entry_id}",
        )
        self._display_activity_store = Store(
            hass,
            DISPLAY_ACTIVITY_STORAGE_VERSION,
            f"{DOMAIN}_display_activity_{config_entry.entry_id}",
        )

    async def async_load_battery_state(self) -> None:
        """Load persisted battery charge diagnostics."""
        data = await self._battery_store.async_load()
        self.battery_tracker.load_storage_data(data)

    async def async_save_battery_state(self) -> None:
        """Persist battery charge diagnostics."""
        await self._battery_store.async_save(self.battery_tracker.as_storage_data())

    async def async_load_display_activity_state(self) -> None:
        """Load persisted display activity diagnostics."""
        data = await self._display_activity_store.async_load()
        self.display_activity_tracker.load_storage_data(data)

    async def async_save_display_activity_state(self) -> None:
        """Persist display activity diagnostics."""
        await self._display_activity_store.async_save(
            self.display_activity_tracker.as_storage_data()
        )

    def _set_next_sync(self) -> None:
        """Set expected next sync timestamp."""
        self.diagnostics.next_sync = dt_util.now() + self.update_interval

    async def async_request_manual_refresh(self) -> None:
        """Refresh data on demand without changing the scheduled refresh time."""
        next_sync = self.diagnostics.next_sync
        try:
            await self.async_request_refresh()
        finally:
            self.diagnostics.next_sync = next_sync
            self._notify_diagnostic_listeners()

    @callback
    def async_set_update_interval(self, update_interval_seconds: int) -> None:
        """Update polling interval and reschedule the next refresh from now."""
        self.update_interval = timedelta(seconds=update_interval_seconds)
        self._set_next_sync()

        unsub_refresh = getattr(self, "_unsub_refresh", None)
        if unsub_refresh is not None:
            unsub_refresh()
            self._unsub_refresh = None

        schedule_refresh = getattr(self, "_schedule_refresh", None)
        if schedule_refresh is not None:
            schedule_refresh()

        self._notify_diagnostic_listeners()

    @callback
    def _notify_diagnostic_listeners(self) -> None:
        """Notify coordinator listeners about diagnostic-only changes."""
        self.async_update_listeners()

    @callback
    def async_add_new_device_listener(
        self, listener: Callable[[set[str]], None]
    ) -> CALLBACK_TYPE:
        """Listen for newly discovered devices."""
        self._new_device_listeners.append(listener)

        @callback
        def _remove_listener() -> None:
            if listener in self._new_device_listeners:
                self._new_device_listeners.remove(listener)

        return _remove_listener

    @callback
    def _notify_new_devices(self, new_macs: set[str]) -> None:
        """Notify listeners about new devices."""
        for listener in list(self._new_device_listeners):
            listener(new_macs)

    async def _async_fetch_json(self) -> dict[str, Any]:
        """Fetch JSON payload from endpoint."""
        try:
            async with asyncio.timeout(self.timeout):
                async with self.session.get(
                    self.url,
                    headers={"Accept": "application/json"},
                ) as response:
                    response.raise_for_status()
                    raw_text = await response.text()
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching data from Export API") from err
        except ClientResponseError as err:
            raise UpdateFailed(
                f"HTTP error fetching data: {err.status} {err.message}"
            ) from err
        except ClientError as err:
            raise UpdateFailed("Connection error fetching data from Export API") from err

        raw_text = raw_text.strip()
        if not raw_text:
            raise UpdateFailed("Endpoint returned an empty response instead of JSON")

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as err:
            preview = raw_text[:200].replace("\n", " ").replace("\r", " ")
            raise UpdateFailed(
                f"Endpoint did not return valid JSON. First 200 chars: {preview}"
            ) from err

        try:
            return normalize_export_payload(data)
        except ValueError as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def _async_registry_macs_for_entry(self) -> set[str]:
        """Return MACs of devices currently stored for this config entry."""
        device_registry = dr.async_get(self.hass)
        macs: set[str] = set()

        for device in dr.async_entries_for_config_entry(
            device_registry,
            self.config_entry.entry_id,
        ):
            for domain, identifier in device.identifiers:
                identifier = str(identifier).lower()
                if domain == DOMAIN and _is_panel_mac(identifier):
                    macs.add(identifier)

        return macs

    async def _async_remove_devices(self, removed_macs: set[str]) -> None:
        """Remove devices and all their entities if they disappeared from JSON."""
        if not removed_macs:
            return

        device_registry = dr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)

        for mac in removed_macs:
            device = device_registry.async_get_device(identifiers={(DOMAIN, mac)})
            if device is None:
                continue

            entity_entries = er.async_entries_for_device(
                entity_registry,
                device.id,
                include_disabled_entities=True,
            )

            for entity_entry in entity_entries:
                if entity_entry.config_entry_id != self.config_entry.entry_id:
                    continue
                entity_registry.async_remove(entity_entry.entity_id)
                _LOGGER.info(
                    "Removed stale Živý Obraz entity %s for device %s",
                    entity_entry.entity_id,
                    mac,
                )

            device_registry.async_update_device(
                device.id,
                remove_config_entry_id=self.config_entry.entry_id,
            )

            remaining_device = device_registry.async_get(device.id)
            if remaining_device is None:
                _LOGGER.info("Removed stale Živý Obraz device: %s", mac)
            else:
                _LOGGER.info(
                    "Detached stale Živý Obraz device %s from config entry %s",
                    mac,
                    self.config_entry.entry_id,
                )

    async def _async_sync_device_metadata(
        self,
        normalized: dict[str, dict[str, Any]],
    ) -> None:
        """Synchronize device registry metadata with current JSON data."""
        device_registry = dr.async_get(self.hass)

        for mac, data in normalized.items():
            device = device_registry.async_get_device(identifiers={(DOMAIN, mac)})
            if device is None:
                continue

            new_metadata = build_device_registry_metadata(data)
            new_name = build_device_name(mac, data)

            updates: dict[str, str | None] = {}

            if device.name_by_user is None and device.name != new_name:
                updates["name"] = new_name

            if device.manufacturer != new_metadata["manufacturer"]:
                updates["manufacturer"] = new_metadata["manufacturer"]

            if device.model != new_metadata["model"]:
                updates["model"] = new_metadata["model"]

            if device.hw_version != new_metadata["hw_version"]:
                updates["hw_version"] = new_metadata["hw_version"]

            if device.sw_version != new_metadata["sw_version"]:
                updates["sw_version"] = new_metadata["sw_version"]

            if not updates:
                continue

            device_registry.async_update_device(device.id, **updates)

            _LOGGER.info(
                "Updated Živý Obraz device metadata for %s: %s",
                mac,
                ", ".join(f"{key}={value}" for key, value in updates.items()),
            )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from remote JSON endpoint."""
        sync_started_at = dt_util.now()
        self.diagnostics.last_sync = sync_started_at
        self.diagnostics.status = "syncing"
        self.diagnostics.last_error = None
        self._notify_diagnostic_listeners()

        try:
            data = await self._async_fetch_json()
        except UpdateFailed as err:
            self.diagnostics.status = "failed"
            self.diagnostics.last_error = str(err)
            self._set_next_sync()
            self._notify_diagnostic_listeners()
            raise

        normalized: dict[str, dict[str, Any]] = {}
        epapers = data.get("epapers")

        if isinstance(epapers, list):
            for item in epapers:
                if not isinstance(item, dict):
                    continue
                mac = item.get("mac")
                if not mac:
                    continue
                normalized[str(mac).lower()] = item
        else:
            for mac, device_data in data.items():
                if not isinstance(device_data, dict):
                    continue
                normalized[str(mac).lower()] = device_data

        current_macs = set(normalized.keys())

        registry_macs = self._async_registry_macs_for_entry()
        removed_macs = registry_macs - current_macs
        new_macs = current_macs - registry_macs

        if new_macs:
            self._notify_new_devices(new_macs)

        if removed_macs:
            await self._async_remove_devices(removed_macs)

        await self._async_sync_device_metadata(normalized)

        battery_tracker_changed = False
        display_activity_tracker_changed = False
        for mac, device_data in normalized.items():
            if self.battery_tracker.process_device(mac, device_data):
                battery_tracker_changed = True
            if self.display_activity_tracker.process_device(mac, device_data):
                display_activity_tracker_changed = True

        if battery_tracker_changed:
            await self.async_save_battery_state()
        if display_activity_tracker_changed:
            await self.async_save_display_activity_state()

        data_changed = normalized != (self.data or {})

        self.known_macs = current_macs
        self.diagnostics.status = "success" if data_changed else "no_new_data"
        self.diagnostics.last_successful_sync = sync_started_at
        self.diagnostics.device_count = len(normalized)
        self.diagnostics.last_error = None
        self._set_next_sync()
        self._notify_diagnostic_listeners()
        return normalized
