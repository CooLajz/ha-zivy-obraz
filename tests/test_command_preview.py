"""Test Command API preview payloads and local response mapping."""

import pytest

pytest.importorskip("homeassistant")

from custom_components.zivy_obraz.command import (  # noqa: E402
    build_command_payload,
    preview_urls_from_command_response,
)


def test_preview_command_payload_preserves_action():
    """Preview actions must be sent as strings, not booleans."""
    assert build_command_payload(
        "secret",
        "group:6",
        {"preview": "regenerate"},
    ) == {
        "command_key": "secret",
        "target": "group:6",
        "preview": "regenerate",
    }


def test_preview_response_maps_urls_by_mac_and_device_id():
    """Bulk responses update the matching local panel only."""
    devices = {
        "aa:bb:cc:dd:ee:01": {"device_id": "101", "preview_url": None},
        "aa:bb:cc:dd:ee:02": {"device_id": "102", "preview_url": "old"},
    }
    response = {
        "previews": [
            {
                "id": 101,
                "mac": "AA:BB:CC:DD:EE:01",
                "preview_url": "https://example.test/preview/one",
            },
            {
                "id": 102,
                "preview_url": None,
            },
            {
                "id": 999,
                "mac": "AA:BB:CC:DD:EE:99",
                "preview_url": "https://example.test/preview/unknown",
            },
        ]
    }

    assert preview_urls_from_command_response(devices, response) == {
        "aa:bb:cc:dd:ee:01": "https://example.test/preview/one",
        "aa:bb:cc:dd:ee:02": None,
    }
