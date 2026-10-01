"""Verify local rotation, caching, persistence and preview control visibility."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.zivy_obraz.image import ZivyObrazPreview
from custom_components.zivy_obraz.preview_rotation import (
    CONF_PREVIEW_ROTATIONS, rotate_preview,
)
from custom_components.zivy_obraz.select import (
    ZivyObrazPreviewRotationSelect, _setup_preview_rotation,
)


def sample_image():
    image = Image.new("RGB", (2, 3))
    image.putdata([(n, 0, 0) for n in range(1, 7)])
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize("angle,size,pixels", [
    ("90", (3, 2), [5, 3, 1, 6, 4, 2]),
    ("180", (2, 3), [6, 5, 4, 3, 2, 1]),
    ("270", (3, 2), [2, 4, 6, 1, 3, 5]),
])
def test_exact_clockwise_pixels(angle, size, pixels):
    with Image.open(BytesIO(rotate_preview(sample_image(), angle))) as image:
        assert image.size == size
        assert [p[0] for p in image.getdata()] == pixels


@pytest.mark.asyncio
async def test_rotation_reuses_http_and_render_caches(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    monkeypatch.setattr(
        "homeassistant.components.image.get_async_client", lambda *a, **kw: Mock()
    )
    entry = SimpleNamespace(options={}, entry_id="entry")
    coordinator = SimpleNamespace(
        config_entry=entry, last_update_success=True, session=Mock(), timeout=5,
        data={"panel": {"preview_enabled": True,
                        "preview_url": "https://example.test/image",
                        "last_contact": "2026-09-30 12:00:00"}},
    )
    entity = ZivyObrazPreview(hass, coordinator, "panel", b"placeholder")
    entity.hass = hass
    entity.async_write_ha_state = Mock()
    original = sample_image()
    entity._preview.content = original
    entity._preview._completed_revision = entity._preview._revision
    assert await entity.async_image() == original
    render = Mock(wraps=rotate_preview)
    monkeypatch.setattr("custom_components.zivy_obraz.image.rotate_preview", render)
    entity._handle_rotation_update({CONF_PREVIEW_ROTATIONS: {"panel": "90"}})
    rotated = await entity.async_image()
    assert rotated != original
    assert entity.content_type == "image/png"
    assert await entity.async_image() == rotated
    assert render.call_count == 1
    assert entity._preview.content == original
    entity._handle_rotation_update({CONF_PREVIEW_ROTATIONS: {"panel": "0"}})
    assert await entity.async_image() == original
    coordinator.session.get.assert_not_called()


@pytest.mark.asyncio
async def test_select_visibility_and_saved_angle(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    entry = SimpleNamespace(entry_id="entry", options={}, data={})
    data = {"panel": {"preview_enabled": True,
                      "preview_url": "https://example.test/image"}}
    coordinator = SimpleNamespace(data=data, last_update_success=True)
    select = ZivyObrazPreviewRotationSelect(coordinator, entry, "panel")
    select.hass = hass
    select.entity_id = "select.panel_rotation"
    select.async_write_ha_state = Mock()
    def update_entry(config_entry, *, options):
        config_entry.options = options

    hass.config_entries = SimpleNamespace(async_update_entry=update_entry)
    await select.async_select_option("270")
    assert select.current_option == "270"
    assert entry.options[CONF_PREVIEW_ROTATIONS] == {"panel": "270"}
    assert hass.data["zivy_obraz"]["entry"]["runtime_options_update"]
    recreated = ZivyObrazPreviewRotationSelect(coordinator, entry, "panel")
    assert recreated.current_option == "270"



@pytest.mark.asyncio
async def test_select_removed_and_recreated_with_saved_angle(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    items = {}
    registry = Mock()
    registry.async_remove.side_effect = items.pop
    monkeypatch.setattr(er, "async_get", lambda _: registry)
    monkeypatch.setattr(er, "async_entries_for_config_entry", lambda *a: list(items.values()))
    coordinator = SimpleNamespace(
        data={"panel": {}}, last_update_success=True, async_add_listener=Mock()
    )
    entry = SimpleNamespace(
        runtime_data=coordinator, entry_id="entry",
        options={CONF_PREVIEW_ROTATIONS: {"panel": "270"}}, async_on_unload=Mock()
    )
    platform = SimpleNamespace(entities={})
    created = []

    async def add(entities):
        for entity in entities:
            entity.entity_id = "select.panel_rotation"
            assert entity.entity_id not in platform.entities
            platform.entities[entity.entity_id] = entity
            items[entity.entity_id] = SimpleNamespace(
                domain="select", unique_id=entity.unique_id,
                entity_id=entity.entity_id, hidden_by=None,
            )
            async def remove(*, force_remove):
                assert force_remove
                platform.entities.pop(entity.entity_id)
            entity.async_remove = AsyncMock(side_effect=remove)
            created.append(entity)

    platform.async_add_entities = AsyncMock(side_effect=add)
    await _setup_preview_rotation(hass, entry, platform)
    assert not created and not items
    listener = coordinator.async_add_listener.call_args.args[0]
    coordinator.data["panel"]["preview_enabled"] = True
    coordinator.data["panel"]["preview_url"] = "https://example.test/image"
    listener()
    await hass.async_block_till_done()
    assert len(created) == 1 and len(items) == 1
    assert created[-1].current_option == "270"
    listener()
    await hass.async_block_till_done()
    assert len(created) == 1

    # Failed polling is not equivalent to turning sharing off.
    coordinator.last_update_success = False
    coordinator.data["panel"]["preview_enabled"] = False
    coordinator.data["panel"]["preview_url"] = None
    listener()
    await hass.async_block_till_done()
    assert len(items) == 1
    coordinator.last_update_success = True
    listener()
    await hass.async_block_till_done()
    assert not items and not platform.entities
    created[0].async_remove.assert_awaited_once_with(force_remove=True)

    coordinator.data["panel"]["preview_enabled"] = True
    coordinator.data["panel"]["preview_url"] = "https://example.test/image"
    listener()
    await hass.async_block_till_done()
    assert len(created) == 2 and len(items) == 1
    assert created[-1].current_option == "270"


@pytest.mark.asyncio
async def test_startup_removes_old_hidden_rotation_select(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    item = SimpleNamespace(
        domain="select", unique_id="entry_panel_preview_rotation",
        entity_id="select.panel_rotation", hidden_by=er.RegistryEntryHider.INTEGRATION,
    )
    registry = Mock()
    monkeypatch.setattr(er, "async_get", lambda _: registry)
    monkeypatch.setattr(er, "async_entries_for_config_entry", lambda *a: [item])
    coordinator = SimpleNamespace(
        data={"panel": {"preview_enabled": False, "preview_url": None}},
        last_update_success=True,
        async_add_listener=Mock(),
    )
    entry = SimpleNamespace(runtime_data=coordinator, entry_id="entry", async_on_unload=Mock())
    platform = SimpleNamespace(entities={}, async_add_entities=AsyncMock())
    await _setup_preview_rotation(hass, entry, platform)
    registry.async_update_entity.assert_called_once_with(item.entity_id, hidden_by=None)
    registry.async_remove.assert_called_once_with(item.entity_id)
    platform.async_add_entities.assert_not_awaited()
