"""Cached screen previews from the Živý Obraz Export API."""

from __future__ import annotations

import asyncio
from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ZIVY_OBRAZ_CLIENT_HEADERS
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info
from .preview import PreviewCache
from .config_helpers import options_update_signal
from .preview_rotation import CONF_PREVIEW_ROTATIONS, rotate_preview, rotation_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create previews, including devices discovered on later refreshes."""
    coordinator: ZivyObrazCoordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_devices() -> None:
        new = set(coordinator.data or {}) - known
        if new:
            known.update(new)
            async_add_entities(
                ZivyObrazPreview(hass, coordinator, mac) for mac in sorted(new)
            )

    add_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_devices))


class ZivyObrazPreview(CoordinatorEntity[ZivyObrazCoordinator], ImageEntity):
    """Serve a lazy preview through HA, without exposing its source URL."""

    _attr_has_entity_name = True
    _attr_translation_key = "preview"
    _attr_icon = "mdi:image-outline"

    def __init__(
        self, hass: HomeAssistant, coordinator: ZivyObrazCoordinator, mac: str
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass, verify_ssl=True)
        self._mac = mac
        self._attr_unique_id = f"{mac}_preview"
        self._preview = PreviewCache()
        self._rotation = rotation_for(coordinator.config_entry.options, mac)
        self._render_lock = asyncio.Lock()
        self._rendered_key: tuple[bytes, str] | None = None
        self._rendered_content: bytes | None = None
        self._refresh_timer: asyncio.TimerHandle | None = None
        self._sync_preview()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(
            self.hass,
            options_update_signal(self.coordinator.config_entry.entry_id),
            self._handle_rotation_update,
        ))

    @callback
    def _handle_rotation_update(self, changes: dict) -> None:
        if CONF_PREVIEW_ROTATIONS not in changes:
            return
        rotation = rotation_for(changes, self._mac)
        if rotation == self._rotation:
            return
        self._rotation = rotation
        self._rendered_key = self._rendered_content = None
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return super().available and bool(self._preview.url)

    @callback
    def _sync_preview(self) -> None:
        data = (self.coordinator.data or {}).get(self._mac, {})
        self._attr_device_info = build_device_info(self._mac, data)
        url = data.get("preview_url") or None
        contact = data.get("last_contact") or None
        if not self._preview.update(url, contact):
            return
        if not url or (self._rendered_key and self._preview.content is None):
            self._rendered_key = self._rendered_content = None
        if self._refresh_timer is not None:
            self._refresh_timer.cancel()
            self._refresh_timer = None
        try:
            updated = datetime.fromisoformat(str(contact))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            updated = dt_util.as_utc(updated)
        except (ValueError, TypeError):
            updated = dt_util.utcnow()
        # URL rotation must also wake the frontend when contact is unchanged.
        if updated == self._attr_image_last_updated:
            updated = dt_util.utcnow()
        self._attr_image_last_updated = updated

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync_preview()
        super()._handle_coordinator_update()

    @callback
    def _refresh_ready(self) -> None:
        self._refresh_timer = None
        if self._preview.pending:
            self._attr_image_last_updated = dt_util.utcnow()
            self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        async with self._render_lock:
            return await self._async_render_image()

    async def _async_render_image(self) -> bytes | None:
        url = self._preview.url
        content = await self._preview.async_image(
            self.coordinator.session,
            self.coordinator.timeout,
            ZIVY_OBRAZ_CLIENT_HEADERS,
        )
        self._attr_content_type = self._preview.content_type
        if self._preview.pending and self._refresh_timer is None:
            self._refresh_timer = self.hass.loop.call_later(
                self._preview.delay, self._refresh_ready
            )
        if content is None:
            return None
        while self._rotation != "0":
            angle = self._rotation
            key = (content, angle)
            if self._rendered_key == key:
                self._attr_content_type = "image/png"
                return self._rendered_content
            try:
                rendered = await self.hass.async_add_executor_job(
                    rotate_preview, content, angle
                )
            except (OSError, ValueError):
                return None
            if self._preview.url != url:
                return None
            if self._rotation != angle:
                continue
            self._rendered_key, self._rendered_content = key, rendered
            self._attr_content_type = "image/png"
            return rendered
        return content

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.cancel()
            self._refresh_timer = None
        await super().async_will_remove_from_hass()
