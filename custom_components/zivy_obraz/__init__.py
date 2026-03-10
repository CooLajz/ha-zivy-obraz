from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_EXPORT_KEY,
    CONF_IMPORT_KEY,
    CONF_LABEL,
    CONF_PREFIX,
    CONF_PUSH_ENABLED,
    CONF_PUSH_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    DEFAULT_IMPORT_KEY,
    DEFAULT_LABEL,
    DEFAULT_PREFIX,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ZivyObrazCoordinator
from .push import ZivyObrazPushManager

type ZivyObrazConfigEntry = ConfigEntry[ZivyObrazCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Set up Zivy Obraz from a config entry."""
    export_key = entry.options.get(CONF_EXPORT_KEY, entry.data[CONF_EXPORT_KEY])
    timeout = entry.options.get(CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    push_enabled = entry.options.get(
        CONF_PUSH_ENABLED,
        entry.data.get(CONF_PUSH_ENABLED, DEFAULT_PUSH_ENABLED),
    )
    import_key = entry.options.get(
        CONF_IMPORT_KEY,
        entry.data.get(CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY),
    )
    label = entry.options.get(
        CONF_LABEL,
        entry.data.get(CONF_LABEL, DEFAULT_LABEL),
    )
    prefix = entry.options.get(
        CONF_PREFIX,
        entry.data.get(CONF_PREFIX, DEFAULT_PREFIX),
    )
    push_interval = entry.options.get(
        CONF_PUSH_INTERVAL,
        entry.data.get(CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL),
    )

    coordinator = ZivyObrazCoordinator(
        hass=hass,
        export_key=export_key,
        timeout=timeout,
        update_interval_seconds=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Initial refresh failed")

    entry.runtime_data = coordinator

    push_unsub = None
    if push_enabled and import_key.strip():
        push_manager = ZivyObrazPushManager(
            hass=hass,
            import_key=import_key.strip(),
            label_name=label,
            prefix=prefix,
            timeout=timeout,
        )

        push_unsub = async_track_time_interval(
            hass,
            push_manager.async_push,
            timedelta(seconds=push_interval),
        )

        entry.async_on_unload(push_unsub)
        hass.async_create_task(push_manager.async_push())

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "push_unsub": push_unsub,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unloaded
