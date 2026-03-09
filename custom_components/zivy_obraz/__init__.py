from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    PLATFORMS,
)
from .coordinator import ZivyObrazCoordinator

type ZivyObrazConfigEntry = ConfigEntry[ZivyObrazCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Set up Zivy Obraz from a config entry."""
    url = entry.options.get(CONF_URL, entry.data[CONF_URL])
    timeout = entry.options.get(CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    coordinator = ZivyObrazCoordinator(
        hass=hass,
        url=url,
        timeout=timeout,
        update_interval_seconds=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Initial refresh failed")

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)