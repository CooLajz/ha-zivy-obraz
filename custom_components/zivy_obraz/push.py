from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import MAX_PUSH_URL_LENGTH, ZIVY_OBRAZ_PUSH_URL

_LOGGER = logging.getLogger(__name__)

_INVALID_STATE_VALUES = {"unknown", "unavailable", "", None}


class ZivyObrazPushManager:
    """Periodically push selected Home Assistant entity states to Živý Obraz import API."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        import_key: str,
        label_name: str,
        prefix: str,
        timeout: int,
    ) -> None:
        self.hass = hass
        self.import_key = import_key
        self.label_name = label_name.strip()
        self.prefix = prefix.strip()
        self.timeout = timeout
        self.session = async_get_clientsession(hass)

    async def async_push(self, _now: Any = None) -> None:
        """Push current labeled entity states to Živý Obraz."""
        entity_pairs = self._get_labeled_entity_states()

        if not entity_pairs:
            _LOGGER.debug(
                "Živý Obraz push skipped: no valid entities found for label '%s'",
                self.label_name,
            )
            return

        batches = self._build_param_batches(entity_pairs)

        if not batches:
            _LOGGER.debug(
                "Živý Obraz push skipped: no request batches were generated for label '%s'",
                self.label_name,
            )
            return

        for batch in batches:
            await self._async_send_batch(batch)

    def _get_labeled_entity_states(self) -> list[tuple[str, str]]:
        """Return list of (param_name, state_value) for entities having the target label."""
        label_registry = lr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)

        target_label_id: str | None = None
        for label_id, entry in label_registry.labels.items():
            if entry.name == self.label_name:
                target_label_id = label_id
                break

        if target_label_id is None:
            _LOGGER.debug("Živý Obraz label '%s' was not found", self.label_name)
            return []

        pairs: list[tuple[str, str]] = []

        for entry in entity_registry.entities.values():
            if target_label_id not in entry.labels:
                continue

            state_obj = self.hass.states.get(entry.entity_id)
            if state_obj is None or state_obj.state in _INVALID_STATE_VALUES:
                continue

            param_name = self._make_param_name(entry.entity_id)
            pairs.append((param_name, state_obj.state))

        pairs.sort(key=lambda item: item[0])

        _LOGGER.debug(
            "Živý Obraz push collected %s entities for label '%s'",
            len(pairs),
            self.label_name,
        )

        return pairs

    def _make_param_name(self, entity_id: str) -> str:
        """Convert entity_id into a safe query parameter name."""
        sanitized = entity_id.strip().lower()
        sanitized = sanitized.replace(".", "_")
        sanitized = re.sub(r"[^a-z0-9_]+", "_", sanitized)
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")

        if self.prefix:
            safe_prefix = re.sub(r"[^a-zA-Z0-9_.-]+", "_", self.prefix).strip("._-")
            if safe_prefix:
                return f"{safe_prefix}.{sanitized}"

        return sanitized

    def _build_param_batches(
        self,
        entity_pairs: list[tuple[str, str]],
    ) -> list[dict[str, str]]:
        """Split payload into multiple requests if URL would become too long."""
        batches: list[dict[str, str]] = []
        current_batch: dict[str, str] = {"import_key": self.import_key}

        for key, value in entity_pairs:
            candidate = {**current_batch, key: value}
            encoded = urlencode(candidate)

            if len(f"{ZIVY_OBRAZ_PUSH_URL}?{encoded}") <= MAX_PUSH_URL_LENGTH:
                current_batch[key] = value
                continue

            if len(current_batch) > 1:
                batches.append(current_batch)
                current_batch = {"import_key": self.import_key}

            single_candidate = {**current_batch, key: value}
            single_encoded = urlencode(single_candidate)

            if len(f"{ZIVY_OBRAZ_PUSH_URL}?{single_encoded}") > MAX_PUSH_URL_LENGTH:
                _LOGGER.warning(
                    "Živý Obraz push skipped entity '%s' because a single parameter exceeds URL length limit",
                    key,
                )
                continue

            current_batch[key] = value

        if len(current_batch) > 1:
            batches.append(current_batch)

        if len(batches) > 1:
            _LOGGER.debug("Živý Obraz push split into %s batches", len(batches))

        return batches

    async def _async_send_batch(self, params: dict[str, str]) -> None:
        """Send one GET request batch."""
        try:
            async with asyncio.timeout(self.timeout):
                async with self.session.get(ZIVY_OBRAZ_PUSH_URL, params=params) as response:
                    response.raise_for_status()
                    _LOGGER.debug("Živý Obraz push payload sent: %s", params)
        except TimeoutError:
            _LOGGER.warning("Živý Obraz push timeout")
        except ClientError as err:
            _LOGGER.warning("Živý Obraz push failed: %s", err)
