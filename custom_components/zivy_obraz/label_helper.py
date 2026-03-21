from __future__ import annotations

import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr


def _normalize_label_name(value: str) -> str:
    """Normalize label name similarly to Home Assistant label registry."""
    value = value.strip().casefold()
    value = re.sub(r"[\s_-]+", "", value)
    return value


async def async_ensure_label_exists(hass: HomeAssistant, label_name: str) -> str | None:
    """Ensure a Home Assistant label exists and return its label_id.

    Matching is case-insensitive and whitespace-insensitive, so labels like:
    - ZivyObraz
    - zivyobraz
    - Zivy Obraz
    are treated as the same logical label.
    """
    label_name = label_name.strip()
    if not label_name:
        return None

    wanted = _normalize_label_name(label_name)
    label_registry = lr.async_get(hass)

    for label_id, entry in label_registry.labels.items():
        normalized_name = getattr(entry, "normalized_name", None)
        if normalized_name is not None:
            if str(normalized_name) == wanted:
                return label_id

        if _normalize_label_name(entry.name) == wanted:
            return label_id

    created = label_registry.async_create(name=label_name)
    return created.label_id
