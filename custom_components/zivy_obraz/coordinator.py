from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, ZIVY_OBRAZ_EXPORT_URL

_LOGGER = logging.getLogger(__name__)


class ZivyObrazCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching Živý Obraz data."""

    def __init__(
        self,
        hass: HomeAssistant,
        export_key: str,
        timeout: int,
        update_interval_seconds: int,
    ) -> None:
        self.hass = hass
        self._timeout = timeout
        self._url = f"{ZIVY_OBRAZ_EXPORT_URL}?export_key={export_key}&epapers=json"
        self._session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
        )

    async def _async_update_data(self):
        """Fetch data from Živý Obraz."""
        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.get(
                    self._url,
                    headers={"Accept": "application/json"},
                ) as response:
                    response.raise_for_status()
                    data = await response.json(content_type=None)

            if not isinstance(data, dict):
                raise UpdateFailed("Top-level JSON must be an object/dict")

            return data

        except TimeoutError as err:
            raise UpdateFailed("Timeout while fetching Živý Obraz data") from err
        except ClientError as err:
            raise UpdateFailed(f"Error communicating with Živý Obraz: {err}") from err
        except ValueError as err:
            raise UpdateFailed(f"Invalid JSON from Živý Obraz: {err}") from err
