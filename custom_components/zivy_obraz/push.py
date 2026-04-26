from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import re
from typing import Any, Callable
from urllib.parse import urlencode

from aiohttp import ClientError
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import MAX_PUSH_URL_LENGTH, ZIVY_OBRAZ_PUSH_URL

_LOGGER = logging.getLogger(__name__)

_INVALID_STATE_VALUES = {"unknown", "unavailable", "", None}
MAX_DIAGNOSTIC_VARIABLES = 50


@dataclass
class PushDiagnostics:
    """Diagnostic state for the last push attempt."""

    status: str = "idle"
    last_push: Any = None
    last_successful_push: Any = None
    pushed_entities: int = 0
    skipped_entities: int = 0
    request_batches: int = 0
    next_push: Any = None
    last_error: str | None = None
    variables: dict[str, str] = field(default_factory=dict)
    variables_total: int = 0
    variables_truncated: bool = False
    skipped_variables: dict[str, str] = field(default_factory=dict)
    skipped_variables_total: int = 0
    skipped_variables_truncated: bool = False


@dataclass
class _PushEntityCollection:
    """Collected push payload and diagnostics."""

    pairs: list[tuple[str, str]]
    skipped_entities: int
    skipped_pairs: list[tuple[str, str]]


class ZivyObrazPushManager:
    """Periodically push selected Home Assistant entity states to Živý Obraz import API."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        import_key: str,
        label_id: str,
        prefix: str,
        timeout: int,
    ) -> None:
        """Initialize the push manager."""
        self.hass = hass
        self.import_key = import_key
        self.label_id = label_id
        self.prefix = prefix.strip()
        self.timeout = timeout
        self.session = async_get_clientsession(hass)
        self.diagnostics = PushDiagnostics()
        self._listeners: list[Callable[[], None]] = []

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Listen for push diagnostic updates."""
        self._listeners.append(listener)

        @callback
        def _remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove_listener

    @callback
    def _notify_listeners(self) -> None:
        """Notify diagnostic entities about updated push state."""
        for listener in list(self._listeners):
            listener()

    def set_next_push(self, next_push: Any) -> None:
        """Set expected next scheduled push timestamp."""
        self.diagnostics.next_push = next_push
        self._notify_listeners()

    def _set_variable_preview(self, variables: dict[str, str]) -> None:
        """Store a bounded variable preview for HA state attributes."""
        self.diagnostics.variables_total = len(variables)
        self.diagnostics.variables = dict(
            list(variables.items())[:MAX_DIAGNOSTIC_VARIABLES]
        )
        self.diagnostics.variables_truncated = (
            len(variables) > MAX_DIAGNOSTIC_VARIABLES
        )

    def _set_skipped_variable_preview(self, variables: dict[str, str]) -> None:
        """Store a bounded skipped variable preview for HA state attributes."""
        self.diagnostics.skipped_variables_total = len(variables)
        self.diagnostics.skipped_variables = dict(
            list(variables.items())[:MAX_DIAGNOSTIC_VARIABLES]
        )
        self.diagnostics.skipped_variables_truncated = (
            len(variables) > MAX_DIAGNOSTIC_VARIABLES
        )

    async def async_push(self, _now: Any = None) -> None:
        """Push current labeled entity states to Živý Obraz."""
        pushed_at = dt_util.now()
        collection = self._get_labeled_entity_states()
        entity_pairs = collection.pairs
        await self._async_push_pairs(
            pushed_at=pushed_at,
            entity_pairs=entity_pairs,
            skipped_entities=collection.skipped_entities,
            skipped_pairs=collection.skipped_pairs,
            empty_status="no_entities",
            empty_log_message=(
                "Živý Obraz push skipped: no valid entities found for label_id '%s'",
                self.label_id,
            ),
        )

    async def async_push_values(self, values: dict[str, Any]) -> None:
        """Push custom values to Živý Obraz."""
        pushed_at = dt_util.now()
        entity_pairs = sorted(
            (str(key).strip(), str(value))
            for key, value in values.items()
            if str(key).strip()
        )
        await self._async_push_pairs(
            pushed_at=pushed_at,
            entity_pairs=entity_pairs,
            skipped_entities=0,
            skipped_pairs=[],
            empty_status="no_entities",
            empty_log_message=("Živý Obraz custom push skipped: no values provided",),
        )

    async def _async_push_pairs(
        self,
        *,
        pushed_at: Any,
        entity_pairs: list[tuple[str, str]],
        skipped_entities: int,
        skipped_pairs: list[tuple[str, str]],
        empty_status: str,
        empty_log_message: tuple[Any, ...],
    ) -> None:
        """Push prepared key/value pairs and update diagnostics."""
        self.diagnostics.last_push = pushed_at
        self._set_variable_preview(dict(entity_pairs))
        self.diagnostics.pushed_entities = 0
        self.diagnostics.skipped_entities = skipped_entities
        self._set_skipped_variable_preview(dict(skipped_pairs))
        self.diagnostics.request_batches = 0
        self.diagnostics.last_error = None

        if not entity_pairs:
            self.diagnostics.status = empty_status
            _LOGGER.debug(*empty_log_message)
            self._notify_listeners()
            return

        batches = self._build_param_batches(entity_pairs)
        self.diagnostics.request_batches = len(batches)
        self.diagnostics.pushed_entities = sum(len(batch) - 1 for batch in batches)
        sent_variables = {
            key: value
            for batch in batches
            for key, value in batch.items()
            if key != "import_key"
        }
        self._set_variable_preview(sent_variables)

        if not batches:
            self.diagnostics.status = "no_batches"
            _LOGGER.debug(
                "Živý Obraz push skipped: no request batches were generated for label_id '%s'",
                self.label_id,
            )
            self._notify_listeners()
            return

        failed_batches = 0
        last_error: str | None = None

        for batch in batches:
            error = await self._async_send_batch(batch)
            if error is not None:
                failed_batches += 1
                last_error = error

        if failed_batches == 0:
            self.diagnostics.status = "success"
            self.diagnostics.last_successful_push = pushed_at
        elif failed_batches == len(batches):
            self.diagnostics.status = "failed"
        else:
            self.diagnostics.status = "partial_failure"

        self.diagnostics.last_error = last_error
        self._notify_listeners()

    def _get_labeled_entity_states(self) -> _PushEntityCollection:
        """Return list of (param_name, state_value) for entities selected for push."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        pairs: list[tuple[str, str]] = []
        skipped_pairs: list[tuple[str, str]] = []
        skipped_entities = 0

        for entry in entity_registry.entities.values():
            if not self._is_selected_for_push(entry, device_registry):
                continue

            state_obj = self.hass.states.get(entry.entity_id)
            if state_obj is None or state_obj.state in _INVALID_STATE_VALUES:
                skipped_entities += 1
                skipped_pairs.append(
                    (self._make_param_name(entry.entity_id), "invalid_state")
                )
                continue

            param_name = self._make_param_name(entry.entity_id)
            pairs.append((param_name, state_obj.state))

        pairs.sort(key=lambda item: item[0])

        _LOGGER.debug(
            "Živý Obraz push collected %s entities for label_id '%s'",
            len(pairs),
            self.label_id,
        )

        return _PushEntityCollection(
            pairs=pairs,
            skipped_entities=skipped_entities,
            skipped_pairs=skipped_pairs,
        )

    def _is_selected_for_push(
        self,
        entry: er.RegistryEntry,
        device_registry: dr.DeviceRegistry,
    ) -> bool:
        """Return True if the entity is eligible for push for the configured label."""
        if self.label_id in entry.labels:
            return True

        if entry.hidden_by is not None or entry.disabled_by is not None:
            return False

        if not entry.device_id:
            return False

        device_entry = device_registry.async_get(entry.device_id)
        if device_entry is None:
            return False

        return self.label_id in getattr(device_entry, "labels", set())

    def _make_param_name(self, entity_id: str) -> str:
        """Convert entity_id into a safe query parameter name."""
        sanitized = entity_id.strip().lower()
        sanitized = sanitized.replace(".", "_")
        sanitized = re.sub(r"[^\w]+", "_", sanitized, flags=re.UNICODE)
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")

        if self.prefix:
            safe_prefix = self.prefix.strip()
            safe_prefix = re.sub(r"[^\w.-]+", "_", safe_prefix, flags=re.UNICODE)
            safe_prefix = re.sub(r"_+", "_", safe_prefix).strip("._-")
            if safe_prefix:
                return f"{safe_prefix}_{sanitized}"

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
                self.diagnostics.skipped_entities += 1
                skipped_variables = dict(self.diagnostics.skipped_variables)
                skipped_variables[key] = "url_too_long"
                self._set_skipped_variable_preview(skipped_variables)
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

    async def _async_send_batch(self, params: dict[str, str]) -> str | None:
        """Send one GET request batch and return an error message on failure."""
        try:
            async with asyncio.timeout(self.timeout):
                async with self.session.get(ZIVY_OBRAZ_PUSH_URL, params=params) as response:
                    response.raise_for_status()
                    _LOGGER.debug("Živý Obraz push payload sent: %s", params)
        except TimeoutError:
            _LOGGER.warning("Živý Obraz push timeout")
            return "Timeout"
        except ClientError as err:
            _LOGGER.warning("Živý Obraz push failed: %s", err)
            return str(err)

        return None
