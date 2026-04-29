from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .const import ZIVY_OBRAZ_EXPORT_URL


def build_export_url(export_key: str, use_group_filter: bool, group_id) -> str:
    """Build Export API URL with safely encoded query parameters."""
    params: dict[str, str | int] = {
        "export_key": export_key,
        "epapers": "json",
    }
    if use_group_filter and group_id is not None:
        params["group_id"] = group_id

    return f"{ZIVY_OBRAZ_EXPORT_URL}?{urlencode(params)}"


def normalize_export_payload(payload: Any) -> dict[str, Any]:
    """Normalize Export API payload variants to the internal object shape."""
    if isinstance(payload, dict):
        return payload

    if isinstance(payload, list):
        return {"epapers": payload}

    raise ValueError("Top-level JSON must be an object/dict or list")
