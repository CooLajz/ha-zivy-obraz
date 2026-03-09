from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Callable

from aiohttp import ClientError, ClientResponseError
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ZivyObrazCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for Živý Obraz endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        timeout: int | None = None,
        update_interval_seconds: int | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds or DEFAULT_SCAN_INTERVAL),
            always_update=False,
        )
        self.url = url
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.session = async_get_clientsession(hass)

        self.known_macs: set[str] = set()
        self._new_device_listeners: list[Callable[[set[str]], None]] = []

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

            # Smaž všechny entity svázané se zařízením, včetně disabled
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

            # Až potom smaž device
            removed = device_registry.async_remove_device(device.id)
            if removed:
                _LOGGER.info("Removed stale Živý Obraz device: %s", mac)
            else:
                _LOGGER.warning(
                    "Could not remove stale Živý Obraz device %s from device registry",
                    mac,
                )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from remote JSON endpoint."""
        data = await self._async_fetch_json()

        normalized: dict[str, dict[str, Any]] = {}
        for mac, device_data in data.items():
            if not isinstance(device_data, dict):
                continue
            normalized[str(mac).lower()] = device_data

        current_macs = set(normalized.keys())
        new_macs = current_macs - self.known_macs
        removed_macs = self.known_macs - current_macs

        if new_macs:
            self._notify_new_devices(new_macs)

        if removed_macs:
            await self._async_remove_devices(removed_macs)

        self.known_macs = current_macs
        return normalized