from __future__ import annotations

import asyncio
import math
from typing import Any

import voluptuous as vol
from aiohttp import ClientError, ContentTypeError
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import build_export_url, normalize_export_payload
from .const import (
    CONF_EXPORT_KEY,
    CONF_GROUP_ID,
    CONF_IMPORT_KEY,
    CONF_LABEL,
    CONF_NAME,
    CONF_OVERDUE_NOTIFICATION,
    CONF_OVERDUE_TOLERANCE,
    CONF_PREFIX,
    CONF_PREFIX_OVERRIDE,
    CONF_PUSH_ENABLED,
    CONF_PUSH_INTERVAL,
    CONF_REPLACE_INVALID_STATES_WITH_NA,
    CONF_SCAN_INTERVAL,
    CONF_SEND_ONLY_CHANGED,
    CONF_TIMEOUT,
    CONF_USE_GROUP_FILTER,
    DEFAULT_IMPORT_KEY,
    DEFAULT_LABEL,
    DEFAULT_NAME,
    DEFAULT_OVERDUE_NOTIFICATION,
    DEFAULT_OVERDUE_TOLERANCE,
    DEFAULT_PREFIX,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_REPLACE_INVALID_STATES_WITH_NA,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SEND_ONLY_CHANGED,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MAX_OVERDUE_TOLERANCE,
    MAX_PUSH_INTERVAL,
    MAX_SCAN_INTERVAL,
    MAX_TIMEOUT,
    MIN_OVERDUE_TOLERANCE,
    MIN_PUSH_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_TIMEOUT,
)

_VALUE_ERROR_TO_FIELD: dict[str, tuple[str, str]] = {
    "invalid_group_id": (CONF_GROUP_ID, "invalid_group_id"),
    "scan_interval_range": (CONF_SCAN_INTERVAL, "scan_interval_range"),
    "push_interval_range": (CONF_PUSH_INTERVAL, "push_interval_range"),
    "timeout_range": (CONF_TIMEOUT, "timeout_range"),
    "overdue_tolerance_range": (
        CONF_OVERDUE_TOLERANCE,
        "overdue_tolerance_range",
    ),
}


async def _validate_input(hass, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input."""
    session = async_get_clientsession(hass)
    timeout = data[CONF_TIMEOUT]

    url = build_export_url(
        data[CONF_EXPORT_KEY],
        data.get(CONF_GROUP_ID) is not None,
        data.get(CONF_GROUP_ID),
    )

    async with asyncio.timeout(timeout):
        async with session.get(url, headers={"Accept": "application/json"}) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)

    normalize_export_payload(payload)

    return {"title": "Živý Obraz"}


def _validate_push_settings(data: dict[str, Any]) -> None:
    """Validate push-related settings."""
    if data.get(CONF_PUSH_ENABLED) and not _normalize_api_key(data.get(CONF_IMPORT_KEY)):
        data[CONF_PUSH_ENABLED] = False


def _normalize_api_key(value: Any) -> str:
    """Normalize optional API key values from UI/storage."""
    if value is None:
        return ""
    return str(value).strip()


def _normalize_prefix(value: Any) -> str:
    """Normalize optional variable prefix from UI/storage."""
    if value is None:
        return ""
    return str(value).strip()


def _normalize_name(value: Any) -> str:
    """Normalize config entry display name."""
    if value is None:
        return DEFAULT_NAME

    name = str(value).strip()
    return name or DEFAULT_NAME


def _normalize_group_id(value: str | None) -> int | None:
    """Normalize optional group_id from UI input."""
    if value is None:
        return None

    value = str(value).strip()
    if value == "":
        return None

    try:
        group_id = int(value)
    except (TypeError, ValueError) as err:
        raise ValueError("invalid_group_id") from err

    if group_id < 0:
        raise ValueError("invalid_group_id")

    return group_id


def _coerce_int(value: Any, error: str) -> int:
    """Coerce value to int and raise a translated config-flow error key."""
    try:
        return int(value)
    except (TypeError, ValueError) as err:
        raise ValueError(error) from err


def _validate_range(value: int, minimum: int, maximum: int, error: str) -> None:
    """Validate numeric range and raise a translated config-flow error key."""
    if value < minimum or value > maximum:
        raise ValueError(error)


def _set_value_error(errors: dict[str, str], err: ValueError) -> None:
    """Map internal ValueError keys to field/base config-flow errors."""
    error_key = str(err)
    field_error = _VALUE_ERROR_TO_FIELD.get(error_key)

    if field_error is None:
        errors["base"] = "invalid_json"
        return

    field, translation_key = field_error
    errors[field] = translation_key


def _prepare_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Ensure fields are stored in a predictable format."""
    prepared = dict(user_input)

    prepared[CONF_NAME] = _normalize_name(user_input.get(CONF_NAME, DEFAULT_NAME))
    prepared[CONF_GROUP_ID] = _normalize_group_id(user_input.get(CONF_GROUP_ID))
    prepared[CONF_USE_GROUP_FILTER] = prepared[CONF_GROUP_ID] is not None
    prepared[CONF_OVERDUE_NOTIFICATION] = bool(
        user_input.get(CONF_OVERDUE_NOTIFICATION, DEFAULT_OVERDUE_NOTIFICATION)
    )
    prepared[CONF_IMPORT_KEY] = _normalize_api_key(
        user_input.get(CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY)
    )
    prepared[CONF_PREFIX] = _normalize_prefix(user_input.get(CONF_PREFIX, DEFAULT_PREFIX))
    prepared[CONF_PUSH_ENABLED] = bool(
        user_input.get(CONF_PUSH_ENABLED, DEFAULT_PUSH_ENABLED)
    )
    prepared[CONF_SEND_ONLY_CHANGED] = bool(
        user_input.get(CONF_SEND_ONLY_CHANGED, DEFAULT_SEND_ONLY_CHANGED)
    )
    prepared[CONF_REPLACE_INVALID_STATES_WITH_NA] = bool(
        user_input.get(
            CONF_REPLACE_INVALID_STATES_WITH_NA,
            DEFAULT_REPLACE_INVALID_STATES_WITH_NA,
        )
    )

    scan_interval = _coerce_int(
        user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        "scan_interval_range",
    )
    push_interval = _coerce_int(
        user_input.get(CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL),
        "push_interval_range",
    )
    timeout = _coerce_int(
        user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        "timeout_range",
    )

    _validate_range(
        scan_interval,
        MIN_SCAN_INTERVAL,
        MAX_SCAN_INTERVAL,
        "scan_interval_range",
    )
    _validate_range(
        push_interval,
        MIN_PUSH_INTERVAL,
        MAX_PUSH_INTERVAL,
        "push_interval_range",
    )
    _validate_range(timeout, MIN_TIMEOUT, MAX_TIMEOUT, "timeout_range")

    prepared[CONF_SCAN_INTERVAL] = scan_interval
    prepared[CONF_PUSH_INTERVAL] = push_interval
    prepared[CONF_TIMEOUT] = timeout

    # overdue_tolerance is in minutes and must be at least the scan interval
    overdue_tolerance = _coerce_int(
        user_input.get(CONF_OVERDUE_TOLERANCE, DEFAULT_OVERDUE_TOLERANCE),
        "overdue_tolerance_range",
    )
    _validate_range(
        overdue_tolerance,
        MIN_OVERDUE_TOLERANCE,
        MAX_OVERDUE_TOLERANCE,
        "overdue_tolerance_range",
    )
    min_overdue_tolerance = math.ceil(scan_interval / 60)
    prepared[CONF_OVERDUE_TOLERANCE] = max(overdue_tolerance, min_overdue_tolerance)

    return prepared


def _display_group_id(value: Any) -> str:
    """Convert stored group_id to UI value."""
    if value is None:
        return ""
    return str(value)


def _get_config_value(
    config_entry,
    key: str,
    default: Any,
) -> Any:
    """Return options value when present, otherwise fallback to entry data/default."""
    if key in config_entry.options:
        return config_entry.options[key]
    return config_entry.data.get(key, default)


def _get_current_prefix(config_entry) -> str:
    """Return the effective stored prefix, preserving explicit empty override."""
    if config_entry.options.get(CONF_PREFIX_OVERRIDE):
        return _normalize_prefix(config_entry.options.get(CONF_PREFIX))
    return _normalize_prefix(_get_config_value(config_entry, CONF_PREFIX, DEFAULT_PREFIX))


def _build_export_schema(
    *,
    show_export_key: bool = True,
    name: str = DEFAULT_NAME,
    export_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> vol.Schema:
    """Build Export API config schema."""
    schema: dict[Any, Any] = {}

    schema[vol.Required(CONF_NAME, default=name)] = str

    if show_export_key:
        schema[vol.Required(CONF_EXPORT_KEY, default=export_key or "")] = str

    schema[vol.Optional(CONF_GROUP_ID)] = str
    schema[vol.Required(CONF_TIMEOUT, default=timeout)] = vol.All(
        vol.Coerce(int),
    )

    return vol.Schema(schema)


def _build_import_schema(
    *,
    show_import_key: bool = True,
    import_key: str = DEFAULT_IMPORT_KEY,
    label: str = DEFAULT_LABEL,
    prefix: str = DEFAULT_PREFIX,
) -> vol.Schema:
    """Build Import API config schema."""
    schema: dict[Any, Any] = {}

    if show_import_key:
        schema[vol.Optional(CONF_IMPORT_KEY, default=import_key)] = str

    schema[vol.Optional(CONF_LABEL, default=label)] = str
    schema[vol.Optional(CONF_PREFIX)] = str

    return vol.Schema(schema)


class ZivyObrazConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zivy Obraz."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._export_input: dict[str, Any] | None = None

    async def async_step_user(self, user_input=None):
        """Handle Export API setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                user_input.setdefault(CONF_GROUP_ID, "")
                prepared_input = _prepare_user_input(user_input)
                _validate_push_settings(prepared_input)

                unique_group = (
                    str(prepared_input[CONF_GROUP_ID])
                    if prepared_input[CONF_GROUP_ID] is not None
                    else "all"
                )

                await self.async_set_unique_id(
                    f"{prepared_input[CONF_EXPORT_KEY]}::{unique_group}"
                )
                self._abort_if_unique_id_configured()

                await _validate_input(self.hass, prepared_input)

            except TimeoutError:
                errors["base"] = "timeout"
            except ClientError:
                errors["base"] = "cannot_connect"
            except ContentTypeError:
                errors["base"] = "invalid_json"
            except ValueError as err:
                if str(err) == "import_key_required":
                    errors["base"] = "import_key_required"
                else:
                    _set_value_error(errors, err)
            except Exception:
                errors["base"] = "unknown"
            else:
                self._export_input = prepared_input
                return await self.async_step_import()

        schema = _build_export_schema()
        schema = self.add_suggested_values_to_schema(
            schema,
            {CONF_GROUP_ID: ""},
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    async def async_step_import(self, user_input=None):
        """Handle Import API setup."""
        if self._export_input is None:
            return await self.async_step_user()

        if user_input is not None:
            user_input.setdefault(CONF_PREFIX, "")
            prepared_input = _prepare_user_input(
                {
                    **self._export_input,
                    **user_input,
                }
            )
            _validate_push_settings(prepared_input)
            return self.async_create_entry(
                title=prepared_input[CONF_NAME],
                data=prepared_input,
            )

        schema = _build_import_schema()
        schema = self.add_suggested_values_to_schema(
            schema,
            {CONF_PREFIX: DEFAULT_PREFIX},
        )

        return self.async_show_form(
            step_id="import",
            data_schema=schema,
            errors={},
            last_step=True,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return options flow."""
        return ZivyObrazOptionsFlow(config_entry)


class ZivyObrazOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Zivy Obraz."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry
        self._export_input: dict[str, Any] | None = None

    def _current_values(self) -> dict[str, Any]:
        """Return current options merged with stored entry data."""
        if CONF_GROUP_ID in self._config_entry.options:
            current_group_id = _display_group_id(
                self._config_entry.options.get(CONF_GROUP_ID)
            )
        else:
            current_group_id = _display_group_id(
                self._config_entry.data.get(CONF_GROUP_ID)
            )

        return {
            CONF_NAME: _get_config_value(
                self._config_entry,
                CONF_NAME,
                self._config_entry.title or DEFAULT_NAME,
            ),
            CONF_EXPORT_KEY: _normalize_api_key(
                _get_config_value(self._config_entry, CONF_EXPORT_KEY, "")
            ),
            CONF_GROUP_ID: current_group_id,
            CONF_SCAN_INTERVAL: _get_config_value(
                self._config_entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            ),
            CONF_TIMEOUT: _get_config_value(
                self._config_entry, CONF_TIMEOUT, DEFAULT_TIMEOUT
            ),
            CONF_OVERDUE_TOLERANCE: _get_config_value(
                self._config_entry,
                CONF_OVERDUE_TOLERANCE,
                DEFAULT_OVERDUE_TOLERANCE,
            ),
            CONF_OVERDUE_NOTIFICATION: _get_config_value(
                self._config_entry,
                CONF_OVERDUE_NOTIFICATION,
                DEFAULT_OVERDUE_NOTIFICATION,
            ),
            CONF_PUSH_ENABLED: _get_config_value(
                self._config_entry, CONF_PUSH_ENABLED, DEFAULT_PUSH_ENABLED
            ),
            CONF_IMPORT_KEY: _normalize_api_key(
                _get_config_value(
                    self._config_entry, CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY
                )
            ),
            CONF_LABEL: _get_config_value(
                self._config_entry, CONF_LABEL, DEFAULT_LABEL
            ),
            CONF_PREFIX: _get_current_prefix(self._config_entry),
            CONF_PUSH_INTERVAL: _get_config_value(
                self._config_entry, CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL
            ),
            CONF_SEND_ONLY_CHANGED: _get_config_value(
                self._config_entry, CONF_SEND_ONLY_CHANGED, DEFAULT_SEND_ONLY_CHANGED
            ),
            CONF_REPLACE_INVALID_STATES_WITH_NA: _get_config_value(
                self._config_entry,
                CONF_REPLACE_INVALID_STATES_WITH_NA,
                DEFAULT_REPLACE_INVALID_STATES_WITH_NA,
            ),
        }

    async def async_step_init(self, user_input=None):
        """Manage Export API options."""
        errors: dict[str, str] = {}
        current_values = self._current_values()
        has_export_key = bool(current_values[CONF_EXPORT_KEY])

        if user_input is not None:
            try:
                user_input.setdefault(CONF_GROUP_ID, "")
                merged_input = {
                    **current_values,
                    **user_input,
                }
                prepared_input = _prepare_user_input(merged_input)
                _validate_push_settings(prepared_input)
                await _validate_input(self.hass, prepared_input)
            except TimeoutError:
                errors["base"] = "timeout"
            except ClientError:
                errors["base"] = "cannot_connect"
            except ContentTypeError:
                errors["base"] = "invalid_json"
            except ValueError as err:
                if str(err) == "import_key_required":
                    errors["base"] = "import_key_required"
                else:
                    _set_value_error(errors, err)
            except Exception:
                errors["base"] = "unknown"
            else:
                self._export_input = prepared_input
                return await self.async_step_import()

        schema = _build_export_schema(
            show_export_key=not has_export_key,
            name=current_values[CONF_NAME],
            export_key=current_values[CONF_EXPORT_KEY],
            timeout=current_values[CONF_TIMEOUT],
        )
        schema = self.add_suggested_values_to_schema(
            schema,
            {CONF_GROUP_ID: current_values[CONF_GROUP_ID]},
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    async def async_step_import(self, user_input=None):
        """Manage Import API options."""
        current_values = self._export_input or self._current_values()
        has_import_key = bool(_normalize_api_key(current_values[CONF_IMPORT_KEY]))

        if user_input is not None:
            user_input.setdefault(CONF_PREFIX, "")
            prepared_input = _prepare_user_input(
                {
                    **current_values,
                    **user_input,
                }
            )
            _validate_push_settings(prepared_input)
            prepared_input[CONF_PREFIX_OVERRIDE] = True
            return self.async_create_entry(title="", data=prepared_input)

        schema = _build_import_schema(
            show_import_key=not has_import_key,
            import_key=current_values[CONF_IMPORT_KEY],
            label=current_values[CONF_LABEL],
            prefix=current_values[CONF_PREFIX],
        )
        schema = self.add_suggested_values_to_schema(
            schema,
            {CONF_PREFIX: current_values[CONF_PREFIX]},
        )

        return self.async_show_form(
            step_id="import",
            data_schema=schema,
            errors={},
            last_step=True,
        )
