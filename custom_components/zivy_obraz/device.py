from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def _build_sw_version(data: dict[str, Any]) -> str | None:
    """Build firmware version string."""
    fw = data.get("fw")
    fw_build = data.get("fw_build")

    if fw and fw_build:
        return f"{fw} ({fw_build})"
    if fw:
        return str(fw)

    return None


def _build_model(data: dict[str, Any]) -> str | None:
    """Build model string."""
    display_type = data.get("display_type")
    x = data.get("x")
    y = data.get("y")
    colors = data.get("colors")

    model_parts: list[str] = []
    if display_type:
        model_parts.append(str(display_type))
    if x and y:
        model_parts.append(f"{x}x{y}")
    if colors:
        model_parts.append(str(colors))

    return " ".join(model_parts) if model_parts else None


def _build_hw_version(data: dict[str, Any]) -> str | None:
    """Build hardware version string."""
    board_type = data.get("board_type")
    if board_type is None:
        return None
    return str(board_type)


def build_device_registry_metadata(data: dict[str, Any]) -> dict[str, str | None]:
    """Build metadata used for Home Assistant device registry updates."""
    return {
        "manufacturer": "Živý Obraz",
        "model": _build_model(data),
        "hw_version": _build_hw_version(data),
        "sw_version": _build_sw_version(data),
    }


def build_device_info(mac: str, data: dict[str, Any]) -> DeviceInfo:
    """Build Home Assistant device info for a Živý Obraz device."""
    caption = data.get("caption") or mac
    metadata = build_device_registry_metadata(data)

    return DeviceInfo(
        identifiers={(DOMAIN, mac)},
        name=caption,
        manufacturer=metadata["manufacturer"],
        model=metadata["model"],
        hw_version=metadata["hw_version"],
        sw_version=metadata["sw_version"],
    )
