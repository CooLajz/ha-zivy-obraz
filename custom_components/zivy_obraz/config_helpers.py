from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN


def options_update_signal(entry_id: str) -> str:
    """Return dispatcher signal for runtime option updates."""
    return f"{DOMAIN}_{entry_id}_runtime_options_updated"


def get_config_value(config_entry: ConfigEntry, key: str, default: Any) -> Any:
    """Return options value when present, otherwise fallback to entry data/default."""
    if key in config_entry.options:
        return config_entry.options[key]
    return config_entry.data.get(key, default)


@callback
def migrate_entry_entity_unique_ids(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    entity_domain: str,
    unique_id_suffixes: set[str],
) -> None:
    """Scope matching legacy entity unique IDs to their config entry."""
    entity_registry = er.async_get(hass)
    entry_prefix = f"{config_entry.entry_id}_"

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        config_entry.entry_id,
    ):
        if entity_entry.domain != entity_domain:
            continue
        if entity_entry.unique_id.startswith(entry_prefix):
            continue
        if not any(
            entity_entry.unique_id.endswith(suffix)
            for suffix in unique_id_suffixes
        ):
            continue
        entity_registry.async_update_entity(
            entity_entry.entity_id,
            new_unique_id=f"{entry_prefix}{entity_entry.unique_id}",
        )


async def async_update_option(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    key: str,
    value: Any,
) -> None:
    """Persist one runtime option and reload the entry through the update listener."""
    await async_update_options(hass, config_entry, {key: value})


async def async_update_options(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    values: dict[str, Any],
) -> None:
    """Persist runtime options and reload the entry through the update listener."""
    if all(
        get_config_value(config_entry, key, None) == value
        and key in config_entry.options
        for key, value in values.items()
    ):
        return

    options = dict(config_entry.options)
    options.update(values)
    entry_data = hass.data.setdefault(DOMAIN, {}).setdefault(config_entry.entry_id, {})
    entry_data["runtime_options_update"] = True
    entry_data["runtime_options_update_keys"] = (
        set(entry_data.get("runtime_options_update_keys", set())) | set(values)
    )
    async_dispatcher_send(hass, options_update_signal(config_entry.entry_id), values)
    hass.config_entries.async_update_entry(config_entry, options=options)
