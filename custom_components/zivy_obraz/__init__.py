from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.helpers.config_validation as cv
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    ATTR_ENTRY_ID,
    ATTR_NAME,
    ATTR_SEND_ALL,
    ATTR_VALUE,
    ATTR_VALUES,
    ATTR_VARIABLE,
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
    CONF_SEND_ONLY_CHANGED,
    CONF_TIMEOUT,
    CONF_USE_GROUP_FILTER,
    DEFAULT_IMPORT_KEY,
    DEFAULT_LABEL,
    DEFAULT_NAME,
    DEFAULT_PREFIX,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SEND_ONLY_CHANGED,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_GROUP_FILTER,
    DOMAIN,
    PLATFORMS,
    SERVICE_PUSH,
    SERVICE_PUSH_VALUES,
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
        vol.Optional(ATTR_SEND_ALL): cv.boolean,
    }
)

PUSH_VALUES_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Required(ATTR_VALUES): vol.Any(
            vol.All(
                dict,
                vol.Length(min=1),
                vol.Schema({cv.string: vol.Any(str, int, float, bool)}),
            ),
            vol.All(
                list,
                vol.Length(min=1),
                [
                    vol.Schema(
                        {
                            vol.Required(ATTR_VARIABLE): cv.string,
                            vol.Required(ATTR_VALUE): vol.Any(str, int, float, bool),
                        }
                    )
                ],
            ),
        ),
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

    async def _async_handle_push_values_service(call: ServiceCall) -> None:
        await _async_handle_custom_push(
            hass,
            call,
            _normalize_custom_values(call.data[ATTR_VALUES]),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_PUSH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PUSH,
            _async_handle_push_service,
            schema=PUSH_SERVICE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_PUSH_VALUES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PUSH_VALUES,
            _async_handle_push_values_service,
            schema=PUSH_VALUES_SERVICE_SCHEMA,
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


def _diagnostic_device_identifier(entry: ConfigEntry) -> tuple[str, str]:
    """Return the diagnostic device identifier for a config entry."""
    return (DOMAIN, f"{entry.entry_id}_push")


def _diagnostic_device_name(entry_name: str) -> str:
    """Return the diagnostic device name."""
    return f"Živý Obraz - {entry_name}"


def _sync_diagnostic_device_name(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entry_name: str,
) -> None:
    """Keep the diagnostic device name aligned with the config entry name."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={_diagnostic_device_identifier(entry)}
    )

    if device is None:
        return

    new_name = _diagnostic_device_name(entry_name)
    if device.name != new_name:
        device_registry.async_update_device(device.id, name=new_name)


async def _async_handle_manual_push(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    """Handle manual push service call."""
    entry_id = call.data.get(ATTR_ENTRY_ID)
    name = call.data.get(ATTR_NAME)
    send_all = call.data.get(ATTR_SEND_ALL)

    if entry_id and name:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="push_entry_id_and_name",
        )

    if entry_id:
        entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if entry_data is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_entry_not_loaded",
                translation_placeholders={"entry": str(entry_id)},
            )

        await _async_push_entry(entry_id, entry_data, send_all=send_all)
        return

    if name:
        matches = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if _entry_name(entry) == name
        ]

        if not matches:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_name_not_found",
                translation_placeholders={"name": str(name)},
            )

        if len(matches) > 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_name_not_unique",
                translation_placeholders={"name": str(name)},
            )

        selected_entry = matches[0]
        entry_data = hass.data.get(DOMAIN, {}).get(selected_entry.entry_id)
        if entry_data is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_entry_not_loaded",
                translation_placeholders={"entry": str(name)},
            )

        await _async_push_entry(
            selected_entry.entry_id,
            entry_data,
            send_all=send_all,
        )
        return

    push_tasks = [
        _async_push_entry(entry_id, entry_data, send_all=send_all)
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items()
        if entry_data.get("push_manager") is not None
    ]

    if not push_tasks:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="push_no_entries_ready",
        )

    await asyncio.gather(*push_tasks)


async def _async_handle_custom_push(
    hass: HomeAssistant,
    call: ServiceCall,
    values: dict[str, str],
) -> None:
    """Handle custom value push service calls."""
    if not values:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="push_values_empty",
        )

    entry_id = call.data.get(ATTR_ENTRY_ID)
    name = call.data.get(ATTR_NAME)

    if entry_id and name:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="push_entry_id_and_name",
        )

    if entry_id:
        entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if entry_data is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_entry_not_loaded",
                translation_placeholders={"entry": str(entry_id)},
            )

        await _async_push_entry_values(entry_id, entry_data, values)
        return

    if name:
        matches = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if _entry_name(entry) == name
        ]

        if not matches:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_name_not_found",
                translation_placeholders={"name": str(name)},
            )

        if len(matches) > 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_name_not_unique",
                translation_placeholders={"name": str(name)},
            )

        selected_entry = matches[0]
        entry_data = hass.data.get(DOMAIN, {}).get(selected_entry.entry_id)
        if entry_data is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="push_entry_not_loaded",
                translation_placeholders={"entry": str(name)},
            )

        await _async_push_entry_values(
            selected_entry.entry_id,
            entry_data,
            values,
        )
        return

    push_tasks = [
        _async_push_entry_values(entry_id, entry_data, values)
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items()
        if entry_data.get("push_manager") is not None
    ]

    if not push_tasks:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="push_no_entries_ready",
        )

    await asyncio.gather(*push_tasks)


def _normalize_custom_values(
    values: (
        dict[str, str | int | float | bool]
        | list[dict[str, str | int | float | bool]]
    ),
) -> dict[str, str]:
    """Normalize custom service values from map or list form."""
    if isinstance(values, dict):
        raw_items = values.items()
    else:
        raw_items = (
            (item[ATTR_VARIABLE], item[ATTR_VALUE])
            for item in values
        )

    return {
        str(key).strip(): str(value)
        for key, value in raw_items
        if str(key).strip() and str(key).strip() != "import_key"
    }


async def _async_push_entry(
    entry_id: str,
    entry_data: dict,
    *,
    send_all: bool | None = None,
) -> None:
    """Push one loaded config entry."""
    push_manager = entry_data.get("push_manager")

    if push_manager is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="push_entry_not_ready",
            translation_placeholders={"entry": str(entry_id)},
        )

    await push_manager.async_push(send_all=send_all)


async def _async_push_entry_values(
    entry_id: str,
    entry_data: dict,
    values: dict[str, str],
) -> None:
    """Push custom values to one loaded config entry."""
    push_manager = entry_data.get("push_manager")

    if push_manager is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="push_entry_not_ready",
            translation_placeholders={"entry": str(entry_id)},
        )

    await push_manager.async_push_values(values)


async def async_setup_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Set up Zivy Obraz from a config entry."""
    entry_name = _entry_name(entry)
    if entry.title != entry_name:
        hass.config_entries.async_update_entry(entry, title=entry_name)
    _sync_diagnostic_device_name(hass, entry, entry_name)

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
    send_only_changed = bool(
        _get_config_value(
            entry,
            CONF_SEND_ONLY_CHANGED,
            DEFAULT_SEND_ONLY_CHANGED,
        )
    )

    coordinator = ZivyObrazCoordinator(
        hass=hass,
        url=url,
        config_entry=entry,
        timeout=timeout,
        update_interval_seconds=scan_interval,
    )

    await coordinator.async_refresh()

    if coordinator.data is None:
        coordinator.data = {}

    if not coordinator.last_update_success:
        _LOGGER.warning(
            "Živý Obraz initial refresh failed; setting up diagnostics with empty data"
        )

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
                send_only_changed=send_only_changed,
            )

            _LOGGER.debug(
                "Živý Obraz push ready with label '%s' (label_id=%s), prefix='%s', send_only_changed=%s",
                label,
                push_label_id,
                prefix,
                send_only_changed,
            )

            if push_enabled:
                push_unsub = _async_start_push_schedule(
                    hass,
                    entry,
                    push_manager,
                    push_interval,
                    entry_name,
                )
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
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if entry_data.pop("runtime_options_update", False):
        changed_keys = set(entry_data.pop("runtime_options_update_keys", set()))
        _LOGGER.debug(
            "Živý Obraz runtime options updated; applying without reload for %s",
            entry.entry_id,
        )
        _async_apply_runtime_options(hass, entry, changed_keys)
        return

    _LOGGER.debug("Živý Obraz options updated; reloading config entry %s", entry.entry_id)
    entry_name = _entry_name(entry)
    if entry.title != entry_name:
        hass.config_entries.async_update_entry(entry, title=entry_name)
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_start_push_schedule(
    hass: HomeAssistant,
    entry: ZivyObrazConfigEntry,
    push_manager: ZivyObrazPushManager,
    push_interval: int,
    entry_name: str,
) -> CALLBACK_TYPE:
    """Start scheduled push and return its unsubscribe callback."""
    _LOGGER.debug(
        "Živý Obraz scheduled push enabled for '%s', interval=%s",
        entry_name,
        push_interval,
    )

    async def _async_scheduled_push(_now) -> None:
        current_interval = int(
            _get_config_value(entry, CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL)
        )
        await push_manager.async_push()
        push_manager.set_next_push(dt_util.now() + timedelta(seconds=current_interval))

    push_manager.set_next_push(dt_util.now() + timedelta(seconds=push_interval))
    push_unsub = async_track_time_interval(
        hass,
        _async_scheduled_push,
        timedelta(seconds=push_interval),
    )
    entry.async_on_unload(push_unsub)
    return push_unsub


@callback
def _async_apply_runtime_options(
    hass: HomeAssistant,
    entry: ZivyObrazConfigEntry,
    changed_keys: set[str],
) -> None:
    """Apply config-entity option changes without reloading the integration."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not entry_data:
        return

    coordinator: ZivyObrazCoordinator | None = entry_data.get("coordinator")
    if coordinator is not None and CONF_SCAN_INTERVAL in changed_keys:
        scan_interval = int(
            _get_config_value(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        coordinator.async_set_update_interval(scan_interval)
    elif coordinator is not None and changed_keys:
        coordinator._notify_diagnostic_listeners()

    push_manager: ZivyObrazPushManager | None = entry_data.get("push_manager")
    if push_manager is None:
        return

    if CONF_SEND_ONLY_CHANGED in changed_keys:
        push_manager.send_only_changed = bool(
            _get_config_value(
                entry,
                CONF_SEND_ONLY_CHANGED,
                DEFAULT_SEND_ONLY_CHANGED,
            )
        )

    if not {CONF_PUSH_ENABLED, CONF_PUSH_INTERVAL} & changed_keys:
        return

    push_unsub = entry_data.get("push_unsub")
    if push_unsub is not None:
        push_unsub()
        entry_data["push_unsub"] = None
        push_manager.set_next_push(None)

    push_enabled = bool(
        _get_config_value(
            entry,
            CONF_PUSH_ENABLED,
            DEFAULT_PUSH_ENABLED,
        )
    )
    if not push_enabled:
        return

    push_interval = int(
        _get_config_value(entry, CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL)
    )
    entry_data["push_unsub"] = _async_start_push_schedule(
        hass,
        entry,
        push_manager,
        push_interval,
        _entry_name(entry),
    )


async def async_unload_entry(hass: HomeAssistant, entry: ZivyObrazConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unloaded
