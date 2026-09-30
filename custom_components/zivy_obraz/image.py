"""Cached screen previews from the Živý Obraz Export API."""

from __future__ import annotations

import asyncio
from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ZIVY_OBRAZ_CLIENT_HEADERS
from .coordinator import ZivyObrazCoordinator
from .device import build_device_info
from .preview import PreviewCache


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
        self._refresh_timer: asyncio.TimerHandle | None = None
        self._sync_preview()

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
        return content

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.cancel()
            self._refresh_timer = None
        await super().async_will_remove_from_hass()
