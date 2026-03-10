from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, ZIVY_OBRAZ_EXPORT_URL

_LOGGER = logging.getLogger(__name__)


class ZivyObrazCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for fetching Živý Obraz data."""

    def __init__(
        self,
        hass: HomeAssistant,
        export_key: str,
        timeout: int,
        update_interval_seconds: int,
    ) -> None:
        """Initialize coordinator."""
        self.hass = hass
        self._timeout = timeout
        self._url = f"{ZIVY_OBRAZ_EXPORT_URL}?export_key={export_key}&epapers=json"
        self._session = async_get_clientsession(hass)
        self._known_macs: set[str] = set()
        self._new_device_listeners: list = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
            always_update=False,
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from Živý Obraz."""
        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.get(
                    self._url,
                    headers={"Accept": "application/json"},
                ) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)

            data = self._normalize_payload(payload)

            new_macs = set(data) - self._known_macs
            if new_macs:
                self._known_macs.update(new_macs)
                for listener in list(self._new_device_listeners):
                    listener(new_macs)

            return data

        except TimeoutError as err:
            raise UpdateFailed("Timeout while fetching Živý Obraz data") from err
        except ClientError as err:
            raise UpdateFailed(f"Error communicating with Živý Obraz: {err}") from err
        except ValueError as err:
            raise UpdateFailed(f"Invalid JSON from Živý Obraz: {err}") from err

    def _normalize_payload(self, payload: Any) -> dict[str, dict[str, Any]]:
        """Normalize API payload into dict keyed by MAC."""
        epapers: list[dict[str, Any]] | None = None

        if isinstance(payload, dict):
            raw_epapers = payload.get("epapers")

            if isinstance(raw_epapers, list):
                epapers = [item for item in raw_epapers if isinstance(item, dict)]

            elif all(isinstance(v, dict) for v in payload.values()):
                # Already keyed by something like MAC -> device data
                data: dict[str, dict[str, Any]] = {}
                for key, value in payload.items():
                    mac = value.get("mac") or key
                    if mac:
                        data[str(mac)] = value
                return data

        elif isinstance(payload, list):
            epapers = [item for item in payload if isinstance(item, dict)]

        if epapers is None:
            raise UpdateFailed("Unsupported JSON structure returned by Živý Obraz")

        data: dict[str, dict[str, Any]] = {}
        for epaper in epapers:
            mac = epaper.get("mac")
            if not mac:
                continue
            data[str(mac)] = epaper

        return data

    def async_add_new_device_listener(self, listener):
        """Register listener for newly discovered devices."""
        self._new_device_listeners.append(listener)

        def _remove_listener() -> None:
            if listener in self._new_device_listeners:
                self._new_device_listeners.remove(listener)

        return _remove_listener
