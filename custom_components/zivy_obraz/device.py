from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def build_device_info(mac: str, data: dict[str, Any]) -> DeviceInfo:
    """Build Home Assistant device info for a Živý Obraz device."""
    caption = data.get("caption") or mac

    fw = data.get("fw")
    fw_build = data.get("fw_build")
    board_type = data.get("board_type")
    display_type = data.get("display_type")
    x = data.get("x")
    y = data.get("y")
    colors = data.get("colors")

    sw_version = None
    if fw and fw_build:
        sw_version = f"{fw} ({fw_build})"
    elif fw:
        sw_version = str(fw)

    model_parts: list[str] = []
    if display_type:
        model_parts.append(str(display_type))
    if x and y:
        model_parts.append(f"{x}x{y}")
    if colors:
        model_parts.append(str(colors))

    return DeviceInfo(
        identifiers={(DOMAIN, mac)},
        name=caption,
        manufacturer="Živý Obraz",
        model=" ".join(model_parts) if model_parts else None,
        hw_version=str(board_type) if board_type is not None else None,
        sw_version=sw_version,
    )
