from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def get_config_value(config_entry: ConfigEntry, key: str, default: Any) -> Any:
    """Return options value when present, otherwise fallback to entry data/default."""
    if key in config_entry.options:
        return config_entry.options[key]
    return config_entry.data.get(key, default)


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
    hass.config_entries.async_update_entry(config_entry, options=options)
