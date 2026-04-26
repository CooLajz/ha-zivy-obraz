from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import json
import logging
from typing import Any, Callable

from aiohttp import ClientError, ClientResponseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, DOMAIN
from .device import build_device_name, build_device_registry_metadata

_LOGGER = logging.getLogger(__name__)


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

    def _set_next_sync(self) -> None:
        """Set expected next sync timestamp."""
        self.diagnostics.next_sync = dt_util.now() + self.update_interval

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
            raise UpdateFailed(f"Timeout fetching data from {self.url}") from err
        except ClientResponseError as err:
            raise UpdateFailed(
                f"HTTP error fetching data: {err.status} {err.message}"
            ) from err
        except ClientError as err:
            raise UpdateFailed(f"Connection error fetching data: {err}") from err

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

        if not isinstance(data, dict):
            raise UpdateFailed("Top-level JSON must be an object/dict")

        return data

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
                if domain == DOMAIN:
                    macs.add(str(identifier).lower())

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

        try:
            data = await self._async_fetch_json()
        except UpdateFailed as err:
            self.diagnostics.status = "failed"
            self.diagnostics.last_error = str(err)
            self._set_next_sync()
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

        self.known_macs = current_macs
        self.diagnostics.status = "success"
        self.diagnostics.last_successful_sync = sync_started_at
        self.diagnostics.device_count = len(normalized)
        self.diagnostics.last_error = None
        self._set_next_sync()
        return normalized
