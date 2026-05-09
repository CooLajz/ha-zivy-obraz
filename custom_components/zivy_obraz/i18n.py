from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from homeassistant.core import HomeAssistant

SUPPORTED_LANGUAGES = {"cs", "en", "sk"}


def _translation_language(language: str) -> str:
    """Return a supported runtime translation language."""
    language = (
        (language or "en").replace("_", "-").split("-", maxsplit=1)[0].casefold()
    )
    return language if language in SUPPORTED_LANGUAGES else "en"


@lru_cache(maxsize=16)
def _load_translations(language: str) -> dict[str, Any]:
    """Load runtime translations for the selected language."""
    language = _translation_language(language)
    filename = f"{language}.json"

    try:
        raw_translations = (
            resources.files(__package__)
            .joinpath("runtime_translations", filename)
            .read_text(encoding="utf-8")
        )
        translations = json.loads(raw_translations)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    return translations if isinstance(translations, dict) else {}


async def async_preload_runtime_translations(hass: HomeAssistant) -> None:
    """Preload runtime translations outside the event loop."""
    await hass.async_add_executor_job(
        lambda: [_load_translations(language) for language in SUPPORTED_LANGUAGES]
    )


def _language(hass: HomeAssistant) -> str:
    """Return configured Home Assistant language."""
    return str(getattr(hass.config, "language", "") or "en")


def localized_mapping(
    hass: HomeAssistant,
    section: str,
    key: str,
    fallback: dict[str, str],
) -> dict[str, str]:
    """Return a localized mapping with English fallback values."""
    language = _translation_language(_language(hass))
    texts = {**fallback}

    english_section = _load_translations("en").get(section, {})
    if isinstance(english_section, dict):
        english_mapping = english_section.get(key, {})
        if isinstance(english_mapping, dict):
            texts.update(
                {
                    map_key: map_value
                    for map_key, map_value in english_mapping.items()
                    if isinstance(map_key, str) and isinstance(map_value, str)
                }
            )

    if not language.casefold().startswith("en"):
        localized_section = _load_translations(language).get(section, {})
        if isinstance(localized_section, dict):
            localized = localized_section.get(key, {})
            if isinstance(localized, dict):
                texts.update(
                    {
                        map_key: map_value
                        for map_key, map_value in localized.items()
                        if isinstance(map_key, str) and isinstance(map_value, str)
                    }
                )

    return texts
