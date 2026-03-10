from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr


def _normalize_label_name(value: str) -> str:
    """Normalize label name for comparison."""
    return value.strip().casefold()


async def async_ensure_label_exists(hass: HomeAssistant, label_name: str) -> str | None:
    """Ensure a Home Assistant label exists and return its label_id.

    Matching is case-insensitive, so e.g. 'ZivyObraz' and 'zivyobraz'
    are treated as the same label.
    """
    label_name = label_name.strip()
    if not label_name:
        return None

    wanted = _normalize_label_name(label_name)
    label_registry = lr.async_get(hass)

    for label_id, entry in label_registry.labels.items():
        if _normalize_label_name(entry.name) == wanted:
            return label_id

    created = label_registry.async_create(name=label_name)
    return created.label_id
