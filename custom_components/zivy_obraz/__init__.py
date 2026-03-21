from __future__ import annotations

from datetime import timedelta
import logging
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_EXPORT_KEY,
    CONF_GROUP_ID,
    CONF_IMPORT_KEY,
    CONF_LABEL,
    CONF_PREFIX,
    CONF_PUSH_ENABLED,
    CONF_PUSH_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USE_GROUP_FILTER,
    DEFAULT_IMPORT_KEY,
    DEFAULT_LABEL,
    DEFAULT_PREFIX,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_GROUP_FILTER,
    DOMAIN,
    PLATFORMS,
    ZIVY_OBRAZ_EXPORT_URL,
)
from .coordinator import ZivyObrazCoordinator
from .label_helper import async_ensure_label_exists
from .push import ZivyObrazPushManager

_LOGGER = logging.getLogger(__name__)

ZivyObrazConfigEntry: TypeAlias = ConfigEntry[ZivyObrazCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _build_export_url(export_key: str, use_group_filter: bool, group_id) -> str:
    """Build export URL from config."""
    url = f"{ZIVY_OBRAZ_EXPORT_URL}?export_key={export_key}&epapers=json"
    if use_group_filter and group_id is not None:
        url += f"&group_id={group_id}"
    return url


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Set up Zivy Obraz from a config entry."""
    export_key = str(entry.options.get(CONF_EXPORT_KEY, entry.data[CONF_EXPORT_KEY])).strip()

    use_group_filter = entry.options.get(
        CONF_USE_GROUP_FILTER,
        entry.data.get(CONF_USE_GROUP_FILTER, DEFAULT_USE_GROUP_FILTER),
    )

    if CONF_GROUP_ID in entry.options:
        raw_group_id = entry.options[CONF_GROUP_ID]
    else:
        raw_group_id = entry.data.get(CONF_GROUP_ID)

    group_id = raw_group_id if use_group_filter else None

    timeout = entry.options.get(
        CONF_TIMEOUT,
        entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    url = _build_export_url(export_key, use_group_filter, group_id)

    push_enabled = bool(
        entry.options.get(
        CONF_PUSH_ENABLED,
        entry.data.get(CONF_PUSH_ENABLED, DEFAULT_PUSH_ENABLED),
    )
    )
    import_key = str(
        entry.options.get(
            CONF_IMPORT_KEY,
            entry.data.get(CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY),
        )
        or ""
    ).strip()
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
        url=url,
        config_entry=entry,
        timeout=timeout,
        update_interval_seconds=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Initial refresh failed")

    entry.runtime_data = coordinator

    push_unsub = None
    push_label_id = None

    if push_enabled:
        if import_key:
            push_label_id = await async_ensure_label_exists(hass, label)

            if push_label_id:
                _LOGGER.debug(
                    "Živý Obraz push enabled with label '%s' (label_id=%s), prefix='%s', interval=%s",
                    label,
                    push_label_id,
                    prefix,
                    push_interval,
                )

                push_manager = ZivyObrazPushManager(
                    hass=hass,
                    import_key=import_key,
                    label_id=push_label_id,
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
            else:
                _LOGGER.warning(
                    "Živý Obraz push is enabled, but label '%s' could not be resolved or created",
                    label,
                )
        else:
            _LOGGER.debug(
                "Živý Obraz push is enabled in config, but import_key is empty; push will not start"
            )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "push_unsub": push_unsub,
        "push_label_id": push_label_id,
        "push_label_name": label,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> None:
    """Handle options update by fully reloading the config entry."""
    _LOGGER.debug("Živý Obraz options updated; reloading config entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unloaded
