from __future__ import annotations

import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr

from .i18n import localized_mapping

LABEL_DESCRIPTION_FALLBACK_TEXTS = {
    "description": (
        "Tagged entities or devices will be sent to the "
        "Živý Obraz {name} service."
    ),
}
LABEL_ICON = "mdi:panorama-variant"


def _normalize_label_name(value: str) -> str:
    """Normalize label name similarly to Home Assistant label registry."""
    value = value.strip().casefold()
    value = re.sub(r"[\s_-]+", "", value)
    return value


def _label_description(hass: HomeAssistant, instance_name: str | None) -> str:
    """Return label description for the configured Home Assistant language."""
    name = (instance_name or "").strip()
    texts = localized_mapping(
        hass,
        "labels",
        "push",
        LABEL_DESCRIPTION_FALLBACK_TEXTS,
    )
    return texts["description"].format(name=name)


def _ensure_label_metadata(
    label_registry: lr.LabelRegistry,
    label_id: str,
    entry: lr.LabelEntry,
    description: str,
) -> None:
    """Fill missing Živý Obraz metadata on an existing label."""
    changes = {}

    if not getattr(entry, "icon", None):
        changes["icon"] = LABEL_ICON

    if not getattr(entry, "description", None):
        changes["description"] = description

    if not changes:
        return

    try:
        label_registry.async_update(label_id, **changes)
    except TypeError:
        # Older Home Assistant versions may not support label metadata updates.
        return


async def async_ensure_label_exists(
    hass: HomeAssistant,
    label_name: str,
    instance_name: str | None = None,
) -> str | None:
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
    description = _label_description(hass, instance_name)

    for label_id, entry in label_registry.labels.items():
        normalized_name = getattr(entry, "normalized_name", None)
        if normalized_name is not None:
            if str(normalized_name) == wanted:
                _ensure_label_metadata(label_registry, label_id, entry, description)
                return label_id

        if _normalize_label_name(entry.name) == wanted:
            _ensure_label_metadata(label_registry, label_id, entry, description)
            return label_id

    try:
        created = label_registry.async_create(
            name=label_name,
            description=description,
            icon=LABEL_ICON,
        )
    except TypeError:
        created = label_registry.async_create(name=label_name)
        _ensure_label_metadata(
            label_registry,
            created.label_id,
            created,
            description,
        )

    return created.label_id


def get_label_id(hass: HomeAssistant, label_name: str) -> str | None:
    """Return label_id for an existing Home Assistant label without creating it."""
    label_name = label_name.strip()
    if not label_name:
        return None

    wanted = _normalize_label_name(label_name)
    label_registry = lr.async_get(hass)

    for label_id, entry in label_registry.labels.items():
        if _normalize_label_name(label_id) == wanted:
            return label_id

        if _normalize_label_name(entry.name) == wanted:
            return label_id

    return None


async def async_get_label_id(hass: HomeAssistant, label_name: str) -> str | None:
    """Return label_id for an existing Home Assistant label without creating it."""
    return get_label_id(hass, label_name)
