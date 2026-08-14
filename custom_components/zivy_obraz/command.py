from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .const import ZIVY_OBRAZ_COMMAND_URL

COMMAND_BOOLEAN_PROPERTIES = {
    "force_wifi_full_scan",
    "ota",
    "invert_screen",
    "rotate_180",
    "show_ap_connect_screen",
    "refresh_screen",
}

COMMAND_LOCAL_PROPERTY_MAP = {
    "caption": "caption",
    "force_wifi_full_scan": "force_wifi_full_scan",
    "note": "note",
    "ota": "ota",
    "invert_screen": "invert_screen",
    "rotate_180": "rotate_180",
    "show_ap_connect_screen": "show_ap_connect_screen",
    "refresh_screen": "refresh_screen",
    "sleep_forced": "sleep_forced",
}

DEVICE_ID_KEYS = ("id", "device_id", "epaper_id")
MASKED_COMMAND_KEY = "********"
MASKED_SECRET_VALUE = "********"


class ZivyObrazCommandError(Exception):
    """Raised when Command API request fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        """Initialize Command API error."""
        super().__init__(message)
        self.code = code
        self.response = response


def normalize_command_target(
    target: str | None,
    configured_group_id: Any | None,
) -> tuple[str, str]:
    """Normalize command target and rewrite HA scoped all to configured group."""
    requested_target = str(target or "all").strip() or "all"
    target_lower = requested_target.lower()

    if target_lower == "all":
        if configured_group_id is not None and str(configured_group_id).strip():
            return "all", f"group:{configured_group_id}"
        return "all", "all"

    if target_lower in {"default", "group:default"}:
        return requested_target, "group:0"

    if target_lower.startswith("group:"):
        group_id = requested_target.split(":", 1)[1].strip()
        if not group_id:
            raise ValueError("invalid_target")
        try:
            parsed_group_id = int(group_id)
        except (TypeError, ValueError) as err:
            raise ValueError("invalid_target") from err
        if parsed_group_id < 0:
            raise ValueError("invalid_target")
        return requested_target, f"group:{parsed_group_id}"

    if target_lower.startswith("device:"):
        device_identifier = requested_target.split(":", 1)[1].strip()
        if not device_identifier:
            raise ValueError("invalid_target")
        return requested_target, f"device:{device_identifier}"

    raise ValueError("invalid_target")


def command_target_macs(
    devices: dict[str, dict[str, Any]],
    target: str,
    *,
    requested_target: str | None = None,
) -> set[str]:
    """Return locally known device MACs affected by a command target."""
    normalized_target = str(target).strip()
    normalized_target_lower = normalized_target.lower()
    requested_target_lower = str(requested_target or "").strip().lower()

    if normalized_target_lower == "all" or requested_target_lower == "all":
        return set(devices)

    if normalized_target_lower.startswith("group:"):
        group_id = normalized_target.split(":", 1)[1].strip()
        if group_id == "0":
            return {
                mac
                for mac, device_data in devices.items()
                if device_data.get("group_id") is None
            }
        return {
            mac
            for mac, device_data in devices.items()
            if str(device_data.get("group_id")) == group_id
        }

    if normalized_target_lower.startswith("device:"):
        device_identifier = normalized_target.split(":", 1)[1].strip()
        device_identifier_lower = device_identifier.lower()
        if device_identifier_lower in devices:
            return {device_identifier_lower}

        return {
            mac
            for mac, device_data in devices.items()
            if any(
                str(device_data.get(key, "")).lower() == device_identifier_lower
                for key in DEVICE_ID_KEYS
            )
        }

    return set()


def command_properties_for_local_data(
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Map command API property names to Export API/local data keys."""
    local_properties: dict[str, Any] = {}

    for property_name, value in properties.items():
        local_key = COMMAND_LOCAL_PROPERTY_MAP.get(property_name)
        if local_key is None:
            continue
        if property_name == "invert_screen" and value is None:
            local_properties[local_key] = None
        elif property_name in COMMAND_BOOLEAN_PROPERTIES:
            local_properties[local_key] = bool(value)
        else:
            local_properties[local_key] = value

    return local_properties


def command_properties_for_response(properties: dict[str, Any]) -> dict[str, Any]:
    """Return properties in the shape expected from Command API."""
    response_properties: dict[str, Any] = {}

    for property_name, value in properties.items():
        if property_name == "invert_screen" and value is None:
            response_properties[property_name] = None
        elif property_name in COMMAND_BOOLEAN_PROPERTIES:
            response_properties[property_name] = 1 if bool(value) else 0
        else:
            response_properties[property_name] = value

    return response_properties


def command_properties_for_diagnostics(properties: dict[str, Any]) -> dict[str, Any]:
    """Return command properties without exposing write-only secrets."""
    diagnostics = command_properties_for_response(properties)
    if "pin_key" in diagnostics:
        diagnostics["pin_key"] = MASKED_SECRET_VALUE
    return diagnostics


def build_masked_command_url(target: str, properties: dict[str, Any]) -> str:
    """Build a diagnostic Command API URL without exposing the Command key."""
    diagnostic_properties = command_properties_for_diagnostics(properties)
    if (
        "invert_screen" in diagnostic_properties
        and diagnostic_properties["invert_screen"] is None
    ):
        diagnostic_properties["invert_screen"] = "null"
    params = {
        "command_key": MASKED_COMMAND_KEY,
        "target": target,
        **diagnostic_properties,
    }

    return f"{ZIVY_OBRAZ_COMMAND_URL}?{urlencode(params, safe='*:')}"


def build_command_payload(
    command_key: str,
    target: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Build Command API query parameters."""
    payload = {
        "command_key": command_key,
        "target": target,
        **command_properties_for_response(properties),
    }
    if payload.get("invert_screen") is None and "invert_screen" in payload:
        payload["invert_screen"] = "null"
    return payload
