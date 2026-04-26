from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_ENTRY_ID,
    ATTR_NAME,
    CONF_EXPORT_KEY,
    CONF_GROUP_ID,
    CONF_IMPORT_KEY,
    CONF_LABEL,
    CONF_NAME,
    CONF_PREFIX,
    CONF_PREFIX_OVERRIDE,
    CONF_PUSH_ENABLED,
    CONF_PUSH_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USE_GROUP_FILTER,
    DEFAULT_IMPORT_KEY,
    DEFAULT_LABEL,
    DEFAULT_NAME,
    DEFAULT_PREFIX,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_GROUP_FILTER,
    DOMAIN,
    PLATFORMS,
    SERVICE_PUSH,
    ZIVY_OBRAZ_EXPORT_URL,
)
from .coordinator import ZivyObrazCoordinator
from .label_helper import async_ensure_label_exists
from .push import ZivyObrazPushManager

_LOGGER = logging.getLogger(__name__)

ZivyObrazConfigEntry: TypeAlias = ConfigEntry[ZivyObrazCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PUSH_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
    }
)


def _get_config_value(entry: ConfigEntry, key: str, default):
    """Return options value when present, otherwise fallback to entry data/default."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _get_prefix_value(entry: ConfigEntry) -> str:
    """Return effective prefix, preserving explicit empty override from options."""
    if entry.options.get(CONF_PREFIX_OVERRIDE):
        return str(entry.options.get(CONF_PREFIX, "") or "").strip()
    return str(_get_config_value(entry, CONF_PREFIX, DEFAULT_PREFIX) or "").strip()


def _build_export_url(export_key: str, use_group_filter: bool, group_id) -> str:
    """Build export URL from config."""
    url = f"{ZIVY_OBRAZ_EXPORT_URL}?export_key={export_key}&epapers=json"
    if use_group_filter and group_id is not None:
        url += f"&group_id={group_id}"
    return url


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})

    async def _async_handle_push_service(call: ServiceCall) -> None:
        await _async_handle_manual_push(hass, call)

    if not hass.services.has_service(DOMAIN, SERVICE_PUSH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PUSH,
            _async_handle_push_service,
            schema=PUSH_SERVICE_SCHEMA,
        )

    return True


def _entry_name(entry: ConfigEntry) -> str:
    """Return user-facing name for a config entry."""
    return str(
        _get_config_value(
            entry,
            CONF_NAME,
            entry.title or DEFAULT_NAME,
        )
        or DEFAULT_NAME
    ).strip()


async def _async_handle_manual_push(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    """Handle manual push service call."""
    entry_id = call.data.get(ATTR_ENTRY_ID)
    name = call.data.get(ATTR_NAME)

    if entry_id and name:
        raise HomeAssistantError("Use either entry_id or name, not both")

    if entry_id:
        entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if entry_data is None:
            raise HomeAssistantError(
                f"Živý Obraz config entry '{entry_id}' is not loaded"
            )

        await _async_push_entry(entry_id, entry_data)
        return

    if name:
        matches = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if _entry_name(entry) == name
        ]

        if not matches:
            raise HomeAssistantError(
                f"Živý Obraz config entry named '{name}' was not found"
            )

        if len(matches) > 1:
            raise HomeAssistantError(
                f"Živý Obraz config entry name '{name}' is not unique; use entry_id"
            )

        selected_entry = matches[0]
        entry_data = hass.data.get(DOMAIN, {}).get(selected_entry.entry_id)
        if entry_data is None:
            raise HomeAssistantError(
                f"Živý Obraz config entry '{name}' is not loaded"
            )

        await _async_push_entry(selected_entry.entry_id, entry_data)
        return

    push_tasks = [
        _async_push_entry(entry_id, entry_data)
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items()
        if entry_data.get("push_manager") is not None
    ]

    if not push_tasks:
        raise HomeAssistantError(
            "No loaded Živý Obraz config entries are ready for push"
        )

    await asyncio.gather(*push_tasks)


async def _async_push_entry(entry_id: str, entry_data: dict) -> None:
    """Push one loaded config entry."""
    push_manager = entry_data.get("push_manager")

    if push_manager is None:
        raise HomeAssistantError(
            f"Živý Obraz config entry '{entry_id}' is not ready for push"
        )

    await push_manager.async_push()


async def async_setup_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Set up Zivy Obraz from a config entry."""
    entry_name = _entry_name(entry)
    if entry.title != entry_name:
        hass.config_entries.async_update_entry(entry, title=entry_name)

    export_key = str(
        _get_config_value(entry, CONF_EXPORT_KEY, entry.data[CONF_EXPORT_KEY])
    ).strip()

    use_group_filter = _get_config_value(
        entry,
        CONF_USE_GROUP_FILTER,
        DEFAULT_USE_GROUP_FILTER,
    )

    if CONF_GROUP_ID in entry.options:
        raw_group_id = entry.options[CONF_GROUP_ID]
    else:
        raw_group_id = entry.data.get(CONF_GROUP_ID)

    group_id = raw_group_id if use_group_filter else None

    timeout = _get_config_value(entry, CONF_TIMEOUT, DEFAULT_TIMEOUT)
    scan_interval = _get_config_value(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    url = _build_export_url(export_key, use_group_filter, group_id)

    push_enabled = bool(
        _get_config_value(
            entry,
            CONF_PUSH_ENABLED,
            DEFAULT_PUSH_ENABLED,
        )
    )
    import_key = str(
        _get_config_value(
            entry,
            CONF_IMPORT_KEY,
            DEFAULT_IMPORT_KEY,
        )
        or ""
    ).strip()
    label = _get_config_value(entry, CONF_LABEL, DEFAULT_LABEL)
    prefix = _get_prefix_value(entry)
    push_interval = _get_config_value(entry, CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL)

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
    push_manager = None

    if import_key:
        push_label_id = await async_ensure_label_exists(hass, label)

        if push_label_id:
            push_manager = ZivyObrazPushManager(
                hass=hass,
                import_key=import_key,
                label_id=push_label_id,
                prefix=prefix,
                timeout=timeout,
            )

            _LOGGER.debug(
                "Živý Obraz push ready with label '%s' (label_id=%s), prefix='%s'",
                label,
                push_label_id,
                prefix,
            )

            if push_enabled:
                _LOGGER.debug(
                    "Živý Obraz scheduled push enabled for '%s', interval=%s",
                    entry_name,
                    push_interval,
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
                "Živý Obraz push is configured, but label '%s' could not be resolved or created",
                label,
            )
    elif push_enabled:
        _LOGGER.debug(
            "Živý Obraz push is enabled in config, but import_key is empty; push will not start"
        )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "push_manager": push_manager,
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
