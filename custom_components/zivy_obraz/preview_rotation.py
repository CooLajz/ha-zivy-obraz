"""Local preview orientation, independent of device commands and HTTP cache."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

CONF_PREVIEW_ROTATIONS = "preview_rotations"
ROTATION_OPTIONS = ["0", "90", "180", "270"]


def rotation_for(options: dict, mac: str) -> str:
    """Read a validated angle, defaulting to the original orientation."""
    rotations = options.get(CONF_PREVIEW_ROTATIONS, {})
    value = str(rotations.get(mac, "0")) if isinstance(rotations, dict) else "0"
    return value if value in ROTATION_OPTIONS else "0"


def rotate_preview(content: bytes, angle: str) -> bytes:
    """Rotate clockwise without cropping or resampling; run in an executor."""
    operation = {
        "90": Image.Transpose.ROTATE_270,
        "180": Image.Transpose.ROTATE_180,
        "270": Image.Transpose.ROTATE_90,
    }[angle]
    with Image.open(BytesIO(content)) as source:
        with source.transpose(operation) as rotated:
            output = BytesIO()
            rotated.save(output, format="PNG")
            return output.getvalue()
