from __future__ import annotations

from typing import Any


def normalize_export_payload(payload: Any) -> dict[str, Any]:
    """Normalize Export API payload variants to the internal object shape."""
    if isinstance(payload, dict):
        return payload

    if isinstance(payload, list):
        return {"epapers": payload}

    raise ValueError("Top-level JSON must be an object/dict or list")
