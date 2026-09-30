"""Check the image entity against real Home Assistant base classes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.core import HomeAssistant
from custom_components.zivy_obraz.image import ZivyObrazPreview, async_setup_entry


@pytest.mark.asyncio
async def test_state_changes_only_for_contact_or_url(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    # HTTP is covered by test_preview; the ImageEntity client is unused here.
    monkeypatch.setattr(
        "homeassistant.components.image.get_async_client", lambda *a, **kw: Mock()
    )
    data = {
        "preview_url": "https://example.test/preview?k=private",
        "last_contact": "2026-09-30 12:00:00",
    }
    coordinator = SimpleNamespace(data={"panel": data}, last_update_success=True)
    entity = ZivyObrazPreview(hass, coordinator, "panel")
    entity.async_write_ha_state = Mock()
    original = entity.state
    assert entity.available and not entity.should_poll
    assert "private" not in str(entity.extra_state_attributes)
    data["battery_percent"] = 90
    entity._handle_coordinator_update()
    assert entity.state == original
    data["last_contact"] = "2026-09-30 13:00:00"
    entity._handle_coordinator_update()
    assert entity.state != original
    original = entity.state
    data["preview_url"] = "https://example.test/preview?k=rotated"
    entity._handle_coordinator_update()
    assert entity.state != original
    data["preview_url"] = None
    entity._handle_coordinator_update()
    assert not entity.available


@pytest.mark.asyncio
async def test_cooldown_wakes_frontend_and_timer_is_removed(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    monkeypatch.setattr(
        "homeassistant.components.image.get_async_client", lambda *a, **kw: Mock()
    )
    coordinator = SimpleNamespace(
        data={"panel": {"preview_url": "https://example.test/preview"}},
        last_update_success=True, session=Mock(), timeout=5,
    )
    entity = ZivyObrazPreview(hass, coordinator, "panel")
    entity.hass = hass
    entity.async_write_ha_state = Mock()
    entity._preview.async_image = AsyncMock(return_value=b"cached")
    original = entity.state
    assert await entity.async_image() == b"cached"
    timer = entity._refresh_timer
    assert timer is not None
    timer.cancel()
    entity._refresh_ready()
    assert entity.state != original
    entity.async_write_ha_state.assert_called_once()
    await entity.async_image()
    timer = entity._refresh_timer
    await entity.async_will_remove_from_hass()
    assert timer.cancelled()


@pytest.mark.asyncio
async def test_setup_discovers_devices_after_initial_empty_data():
    coordinator = SimpleNamespace(data={}, async_add_listener=Mock())
    entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=Mock())
    add_entities = Mock()
    await async_setup_entry(Mock(), entry, add_entities)
    add_entities.assert_not_called()
    listener = coordinator.async_add_listener.call_args.args[0]
    coordinator.data = {"new_panel": {}}
    listener()
    add_entities.assert_called_once()
    listener()
    add_entities.assert_called_once()
