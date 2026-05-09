from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import re
from typing import Any, Callable
from urllib.parse import urlencode

from aiohttp import ClientError, ClientResponseError

try:
    from homeassistant.components.sensor import async_rounded_state
except ImportError:
    async_rounded_state = None
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_INVALID_STATE_FALLBACK,
    MAX_PUSH_URL_LENGTH,
    ZIVY_OBRAZ_PUSH_URL,
)
from .label_helper import get_label_id

_LOGGER = logging.getLogger(__name__)

_INVALID_STATE_VALUES = {"unknown", "unavailable", None}
MAX_DIAGNOSTIC_VARIABLES = 50
PUSH_PROBLEM_STATUSES = {
    "failed",
    "partial_failure",
    "no_batches",
    "no_valid_entities",
}
_REDACTED = "********"


@dataclass
class PushDiagnostics:
    """Diagnostic state for the last push attempt."""

    status: str = "idle"
    last_push: Any = None
    last_successful_push: Any = None
    pushed_entities: int = 0
    skipped_entities: int = 0
    failed_entities: int = 0
    request_batches: int = 0
    next_push: Any = None
    last_error: str | None = None
    variables: dict[str, str] = field(default_factory=dict)
    variables_total: int = 0
    variables_truncated: bool = False
    skipped_variables: dict[str, str] = field(default_factory=dict)
    skipped_variables_total: int = 0
    skipped_variables_truncated: bool = False
    failed_variables: dict[str, str] = field(default_factory=dict)
    failed_variables_total: int = 0
    failed_variables_truncated: bool = False


@dataclass
class _PushEntityCollection:
    """Collected push payload and diagnostics."""

    pairs: list[tuple[str, str]]
    failed_pairs: list[tuple[str, str]]
    always_send_keys: set[str] = field(default_factory=set)


class ZivyObrazPushManager:
    """Periodically push selected Home Assistant entity states to Živý Obraz import API."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        import_key: str,
        label_id: str,
        always_label_name: str,
        prefix: str,
        timeout: int,
        send_only_changed: bool,
        replace_invalid_states_with_na: bool,
        invalid_state_fallback: str,
    ) -> None:
        """Initialize the push manager."""
        self.hass = hass
        self.import_key = import_key
        self.label_id = label_id
        self.always_label_name = always_label_name.strip()
        self.prefix = prefix.strip()
        self.timeout = timeout
        self.send_only_changed = send_only_changed
        self.replace_invalid_states_with_na = replace_invalid_states_with_na
        self.invalid_state_fallback = (
            invalid_state_fallback
            if invalid_state_fallback is not None
            else DEFAULT_INVALID_STATE_FALLBACK
        )
        self.session = async_get_clientsession(hass)
        self.diagnostics = PushDiagnostics()
        self._listeners: list[Callable[[], None]] = []
        self._last_sent_states: dict[str, str] = {}

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

    def _set_failed_variable_preview(self, variables: dict[str, str]) -> None:
        """Store a bounded failed variable preview for HA state attributes."""
        self.diagnostics.failed_variables_total = len(variables)
        self.diagnostics.failed_variables = dict(
            list(variables.items())[:MAX_DIAGNOSTIC_VARIABLES]
        )
        self.diagnostics.failed_variables_truncated = (
            len(variables) > MAX_DIAGNOSTIC_VARIABLES
        )

    async def async_push(
        self,
        _now: Any = None,
        *,
        send_all: bool | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Push current labeled entity states to Živý Obraz."""
        pushed_at = dt_util.now()
        collection = self._get_labeled_entity_states()
        entity_pairs = collection.pairs
        failed_pairs = list(collection.failed_pairs)
        always_send_keys = collection.always_send_keys
        unchanged_pairs: list[tuple[str, str]] = []
        send_only_changed = self.send_only_changed if send_all is None else not send_all

        if send_only_changed:
            changed_pairs: list[tuple[str, str]] = []
            for key, value in entity_pairs:
                if (
                    key not in always_send_keys
                    and self._last_sent_states.get(key) == value
                ):
                    unchanged_pairs.append((key, value))
                    continue
                changed_pairs.append((key, value))
            entity_pairs = changed_pairs

        if dry_run:
            return self._build_push_result(
                status=self._preview_status(entity_pairs, unchanged_pairs, failed_pairs),
                dry_run=True,
                send_only_changed=send_only_changed,
                pushed_pairs=entity_pairs,
                skipped_pairs=unchanged_pairs,
                failed_pairs=failed_pairs,
            )

        return await self._async_push_pairs(
            pushed_at=pushed_at,
            entity_pairs=entity_pairs,
            skipped_pairs=unchanged_pairs,
            failed_pairs=failed_pairs,
            empty_status="no_new_data" if unchanged_pairs else "no_entities",
            empty_log_message=(
                "Živý Obraz push skipped: no valid entities found for label_id '%s'",
                self.label_id,
            ),
            update_cache=True,
            send_only_changed=send_only_changed,
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
            skipped_pairs=[],
            failed_pairs=[],
            empty_status="no_entities",
            empty_log_message=("Živý Obraz custom push skipped: no values provided",),
            update_cache=False,
        )

    async def _async_push_pairs(
        self,
        *,
        pushed_at: Any,
        entity_pairs: list[tuple[str, str]],
        skipped_pairs: list[tuple[str, str]],
        failed_pairs: list[tuple[str, str]],
        empty_status: str,
        empty_log_message: tuple[Any, ...],
        update_cache: bool,
        send_only_changed: bool | None = None,
    ) -> dict[str, Any]:
        """Push prepared key/value pairs and update diagnostics."""
        self.diagnostics.last_push = pushed_at
        self.diagnostics.status = "sending"
        self.diagnostics.last_error = None
        self._set_variable_preview(dict(entity_pairs))
        self.diagnostics.skipped_entities = len(skipped_pairs)
        self.diagnostics.failed_entities = 0
        self._set_skipped_variable_preview(dict(skipped_pairs))
        self._set_failed_variable_preview(dict(failed_pairs))
        self.diagnostics.request_batches = 0

        if not entity_pairs:
            self.diagnostics.pushed_entities = 0
            if failed_pairs:
                self.diagnostics.failed_entities = len(failed_pairs)
                self.diagnostics.status = (
                    "partial_failure" if skipped_pairs else "no_valid_entities"
                )
                self.diagnostics.last_error = (
                    "Selected entities were unavailable or unknown"
                )
            elif empty_status == "no_new_data":
                self.diagnostics.status = "no_new_data"
                self.diagnostics.last_successful_push = pushed_at
                self.diagnostics.last_error = None
            elif self.diagnostics.status not in PUSH_PROBLEM_STATUSES:
                self.diagnostics.status = empty_status
                self.diagnostics.last_error = None
            _LOGGER.debug(*empty_log_message)
            self._notify_listeners()
            return self._build_push_result(
                status=self.diagnostics.status,
                dry_run=False,
                send_only_changed=(
                    self.send_only_changed
                    if send_only_changed is None
                    else send_only_changed
                ),
                pushed_pairs=[],
                skipped_pairs=skipped_pairs,
                failed_pairs=failed_pairs,
                request_batches=0,
            )

        self.diagnostics.last_error = None

        failed_variables: dict[str, str] = dict(failed_pairs)
        batches = self._build_param_batches(entity_pairs, failed_variables)
        self.diagnostics.request_batches = len(batches)
        self.diagnostics.pushed_entities = sum(len(batch) - 1 for batch in batches)
        sent_variables = {
            key: value
            for batch in batches
            for key, value in batch.items()
            if key != "import_key"
        }
        self._set_variable_preview(sent_variables)
        self._notify_listeners()

        if not batches:
            self.diagnostics.failed_entities = len(failed_variables)
            self._set_failed_variable_preview(failed_variables)
            self.diagnostics.status = "no_batches"
            _LOGGER.debug(
                "Živý Obraz push skipped: no request batches were generated for label_id '%s'",
                self.label_id,
            )
            self._notify_listeners()
            return self._build_push_result(
                status=self.diagnostics.status,
                dry_run=False,
                send_only_changed=(
                    self.send_only_changed
                    if send_only_changed is None
                    else send_only_changed
                ),
                pushed_pairs=[],
                skipped_pairs=skipped_pairs,
                failed_pairs=list(failed_variables.items()),
                request_batches=0,
            )

        failed_batches = 0
        successful_variables: dict[str, str] = {}
        failed_reasons: dict[str, str] = dict(failed_variables)
        last_error: str | None = None

        for batch in batches:
            error = await self._async_send_batch(batch)
            batch_variables = {
                key: value for key, value in batch.items() if key != "import_key"
            }
            if error is not None:
                failed_batches += 1
                failed_variables.update(batch_variables)
                failed_reasons.update(
                    {key: error for key in batch_variables}
                )
                last_error = error
                continue

            successful_variables.update(batch_variables)
            if update_cache:
                self._last_sent_states.update(batch_variables)

        if failed_batches == 0 and not failed_variables:
            self.diagnostics.status = "success"
            self.diagnostics.last_successful_push = pushed_at
        elif failed_batches == len(batches):
            self.diagnostics.status = "failed"
        else:
            self.diagnostics.status = "partial_failure"

        self.diagnostics.pushed_entities = len(successful_variables)
        self.diagnostics.failed_entities = len(failed_variables)
        self._set_variable_preview(successful_variables)
        self._set_failed_variable_preview(failed_variables)
        self.diagnostics.last_error = last_error
        self._notify_listeners()
        return self._build_push_result(
            status=self.diagnostics.status,
            dry_run=False,
            send_only_changed=(
                self.send_only_changed
                if send_only_changed is None
                else send_only_changed
            ),
            pushed_pairs=list(successful_variables.items()),
            skipped_pairs=skipped_pairs,
            failed_pairs=list(failed_reasons.items()),
            request_batches=len(batches),
        )

    def _preview_status(
        self,
        pushed_pairs: list[tuple[str, str]],
        skipped_pairs: list[tuple[str, str]],
        failed_pairs: list[tuple[str, str]],
    ) -> str:
        """Return the status for a dry-run push result."""
        if pushed_pairs:
            return "would_push"
        if failed_pairs:
            return "no_valid_entities"
        if skipped_pairs:
            return "no_new_data"
        return "no_entities"

    def _build_push_result(
        self,
        *,
        status: str,
        dry_run: bool,
        send_only_changed: bool,
        pushed_pairs: list[tuple[str, str]],
        skipped_pairs: list[tuple[str, str]],
        failed_pairs: list[tuple[str, str]],
        request_batches: int | None = None,
    ) -> dict[str, Any]:
        """Build service response data for a push or dry-run push."""
        failed_variables: dict[str, str] = dict(failed_pairs)
        batches = self._build_param_batches(pushed_pairs, failed_variables)
        pushed_variables = {
            key: value
            for batch in batches
            for key, value in batch.items()
            if key != "import_key"
        }
        skipped_variables = dict(skipped_pairs)
        result_status = status

        if dry_run and not pushed_variables:
            if failed_variables:
                result_status = "no_batches" if pushed_pairs else "no_valid_entities"
            elif skipped_variables:
                result_status = "no_new_data"
            else:
                result_status = "no_entities"

        return {
            "status": result_status,
            "dry_run": dry_run,
            "send_only_changed": send_only_changed,
            "request_batches": len(batches)
            if request_batches is None
            else request_batches,
            "pushed_entities": len(pushed_variables),
            "skipped_entities": len(skipped_variables),
            "failed_entities": len(failed_variables),
            "pushed": [
                {"variable": key, "value": value}
                for key, value in pushed_variables.items()
            ],
            "skipped": [
                {"variable": key, "value": value, "reason": "unchanged"}
                for key, value in skipped_variables.items()
            ],
            "failed": [
                {"variable": key, "reason": reason}
                for key, reason in failed_variables.items()
            ],
        }

    def _get_labeled_entity_states(self) -> _PushEntityCollection:
        """Return list of (param_name, state_value) for entities selected for push."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        pairs: list[tuple[str, str]] = []
        failed_pairs: list[tuple[str, str]] = []
        always_send_keys: set[str] = set()
        always_label_id = self._get_always_label_id()

        for entry in entity_registry.entities.values():
            if not self._is_selected_for_push(entry, device_registry):
                continue

            param_name = self._make_param_name(entry.entity_id)
            if self._is_always_send_entity(entry, always_label_id):
                always_send_keys.add(param_name)

            state_obj = self.hass.states.get(entry.entity_id)
            if state_obj is None or state_obj.state in _INVALID_STATE_VALUES:
                if self.replace_invalid_states_with_na:
                    pairs.append(
                        (
                            param_name,
                            self.invalid_state_fallback,
                        )
                    )
                else:
                    failed_pairs.append((param_name, "invalid_state"))
                continue

            pairs.append((param_name, self._format_state_for_push(entry, state_obj)))

        pairs.sort(key=lambda item: item[0])

        _LOGGER.debug(
            "Živý Obraz push collected %s entities for label_id '%s'",
            len(pairs),
            self.label_id,
        )

        return _PushEntityCollection(
            pairs=pairs,
            failed_pairs=failed_pairs,
            always_send_keys=always_send_keys,
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

    def _is_always_send_entity(
        self,
        entry: er.RegistryEntry,
        always_label_id: str | None,
    ) -> bool:
        """Return True if the entity should bypass unchanged-value filtering."""
        return (
            always_label_id is not None
            and self.label_id in entry.labels
            and always_label_id in entry.labels
        )

    def _get_always_label_id(self) -> str | None:
        """Return the existing always-send label id without creating it."""
        return get_label_id(self.hass, self.always_label_name)

    def _format_state_for_push(
        self,
        entry: er.RegistryEntry,
        state_obj: Any,
    ) -> str:
        """Return entity state formatted for push."""
        if async_rounded_state is None or entry.domain != "sensor":
            return state_obj.state

        try:
            return async_rounded_state(self.hass, entry.entity_id, state_obj)
        except (TypeError, ValueError):
            return state_obj.state

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
        failed_variables: dict[str, str],
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
                failed_variables[key] = "url_too_long"
                _LOGGER.warning(
                    "Živý Obraz push failed entity '%s' because a single parameter exceeds URL length limit",
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
                async with self.session.get(
                    ZIVY_OBRAZ_PUSH_URL,
                    params=params,
                ) as response:
                    response.raise_for_status()
                    _LOGGER.debug(
                        "Živý Obraz push payload sent: %s",
                        self._redact_params(params),
                    )
        except TimeoutError:
            _LOGGER.warning("Živý Obraz push timeout")
            return "Timeout"
        except ClientResponseError as err:
            message = f"HTTP error: {err.status} {err.message}"
            _LOGGER.warning("Živý Obraz push failed: %s", message)
            return message
        except ClientError as err:
            _LOGGER.warning(
                "Živý Obraz push connection error: %s",
                err.__class__.__name__,
            )
            return "Connection error"

        return None

    def _redact_params(self, params: dict[str, str]) -> dict[str, str]:
        """Return request params safe for logs."""
        return {
            key: _REDACTED if key == "import_key" else value
            for key, value in params.items()
        }
