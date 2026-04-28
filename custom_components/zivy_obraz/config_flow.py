from __future__ import annotations

import asyncio
import math
from typing import Any

import voluptuous as vol
from aiohttp import ClientError, ContentTypeError
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import normalize_export_payload
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
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SEND_ONLY_CHANGED,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_GROUP_FILTER,
    DOMAIN,
    ZIVY_OBRAZ_EXPORT_URL,
)

MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 86400
MIN_PUSH_INTERVAL = 60
MAX_PUSH_INTERVAL = 86400
MIN_TIMEOUT = 5
MAX_TIMEOUT = 120
MIN_OVERDUE_TOLERANCE = 0
MAX_OVERDUE_TOLERANCE = 10080


_VALUE_ERROR_TO_FIELD: dict[str, tuple[str, str]] = {
    "invalid_group_id": (CONF_GROUP_ID, "invalid_group_id"),
    "group_id_required": (CONF_GROUP_ID, "group_id_required"),
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

    url = f"{ZIVY_OBRAZ_EXPORT_URL}?export_key={data[CONF_EXPORT_KEY]}&epapers=json"

    if data.get(CONF_USE_GROUP_FILTER):
        group_id = data.get(CONF_GROUP_ID)
        if group_id is None:
            raise ValueError("group_id_required")
        url += f"&group_id={group_id}"

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
    prepared[CONF_USE_GROUP_FILTER] = bool(user_input.get(CONF_USE_GROUP_FILTER, False))
    prepared[CONF_GROUP_ID] = _normalize_group_id(user_input.get(CONF_GROUP_ID))
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


def _build_schema(
    *,
    show_export_key: bool = True,
    show_import_key: bool = True,
    name: str = DEFAULT_NAME,
    export_key: str | None = None,
    use_group_filter: bool = DEFAULT_USE_GROUP_FILTER,
    group_id: str = "",
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    timeout: int = DEFAULT_TIMEOUT,
    overdue_tolerance: int = DEFAULT_OVERDUE_TOLERANCE,
    overdue_notification: bool = DEFAULT_OVERDUE_NOTIFICATION,
    push_enabled: bool = DEFAULT_PUSH_ENABLED,
    import_key: str = DEFAULT_IMPORT_KEY,
    label: str = DEFAULT_LABEL,
    prefix: str = DEFAULT_PREFIX,
    push_interval: int = DEFAULT_PUSH_INTERVAL,
    send_only_changed: bool = DEFAULT_SEND_ONLY_CHANGED,
) -> vol.Schema:
    """Build config schema."""
    schema: dict[Any, Any] = {}

    schema[vol.Required(CONF_NAME, default=name)] = str

    if show_export_key:
        schema[vol.Required(CONF_EXPORT_KEY, default=export_key or "")] = str

    schema[vol.Optional(CONF_USE_GROUP_FILTER, default=use_group_filter)] = bool
    schema[vol.Optional(CONF_GROUP_ID, default=group_id)] = str
    schema[vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval)] = vol.All(
        vol.Coerce(int),
    )
    schema[vol.Required(CONF_TIMEOUT, default=timeout)] = vol.All(
        vol.Coerce(int),
    )
    schema[vol.Optional(CONF_OVERDUE_NOTIFICATION, default=overdue_notification)] = bool
    schema[vol.Optional(CONF_OVERDUE_TOLERANCE, default=overdue_tolerance)] = vol.All(
        vol.Coerce(int),
    )
    schema[vol.Optional(CONF_PUSH_ENABLED, default=push_enabled)] = bool
    schema[vol.Optional(CONF_SEND_ONLY_CHANGED, default=send_only_changed)] = bool

    if show_import_key:
        schema[vol.Optional(CONF_IMPORT_KEY, default=import_key)] = str

    schema[vol.Optional(CONF_LABEL, default=label)] = str
    schema[vol.Optional(CONF_PREFIX)] = str
    schema[vol.Optional(CONF_PUSH_INTERVAL, default=push_interval)] = vol.All(
        vol.Coerce(int),
    )

    return vol.Schema(schema)


class ZivyObrazConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zivy Obraz."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                prepared_input = _prepare_user_input(user_input)
                _validate_push_settings(prepared_input)

                unique_group = (
                    str(prepared_input[CONF_GROUP_ID])
                    if prepared_input.get(CONF_USE_GROUP_FILTER)
                    and prepared_input[CONF_GROUP_ID] is not None
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
                return self.async_create_entry(
                    title=prepared_input[CONF_NAME],
                    data=prepared_input,
                )

        schema = _build_schema()
        schema = self.add_suggested_values_to_schema(
            schema,
            {CONF_PREFIX: DEFAULT_PREFIX},
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
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

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors: dict[str, str] = {}

        current_name = _get_config_value(
            self._config_entry,
            CONF_NAME,
            self._config_entry.title or DEFAULT_NAME,
        )
        current_export_key = _get_config_value(self._config_entry, CONF_EXPORT_KEY, "")
        current_use_group_filter = _get_config_value(
            self._config_entry,
            CONF_USE_GROUP_FILTER,
            DEFAULT_USE_GROUP_FILTER,
        )

        if CONF_GROUP_ID in self._config_entry.options:
            current_group_id = _display_group_id(
                self._config_entry.options.get(CONF_GROUP_ID)
            )
        else:
            current_group_id = _display_group_id(
                self._config_entry.data.get(CONF_GROUP_ID)
            )

        current_scan_interval = _get_config_value(
            self._config_entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_timeout = _get_config_value(
            self._config_entry, CONF_TIMEOUT, DEFAULT_TIMEOUT
        )
        current_overdue_tolerance = _get_config_value(
            self._config_entry,
            CONF_OVERDUE_TOLERANCE,
            DEFAULT_OVERDUE_TOLERANCE,
        )
        current_overdue_notification = _get_config_value(
            self._config_entry,
            CONF_OVERDUE_NOTIFICATION,
            DEFAULT_OVERDUE_NOTIFICATION,
        )
        current_push_enabled = _get_config_value(
            self._config_entry, CONF_PUSH_ENABLED, DEFAULT_PUSH_ENABLED
        )
        current_import_key = _get_config_value(
            self._config_entry, CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY
        )
        current_label = _get_config_value(self._config_entry, CONF_LABEL, DEFAULT_LABEL)
        current_prefix = _get_current_prefix(self._config_entry)
        current_push_interval = _get_config_value(
            self._config_entry, CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL
        )
        current_send_only_changed = _get_config_value(
            self._config_entry, CONF_SEND_ONLY_CHANGED, DEFAULT_SEND_ONLY_CHANGED
        )

        has_export_key = bool(_normalize_api_key(current_export_key))
        has_import_key = bool(_normalize_api_key(current_import_key))

        if user_input is not None:
            try:
                merged_input = {
                    CONF_EXPORT_KEY: _normalize_api_key(current_export_key),
                    CONF_IMPORT_KEY: _normalize_api_key(current_import_key),
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
                prepared_input[CONF_PREFIX_OVERRIDE] = True
                return self.async_create_entry(title="", data=prepared_input)

        schema = _build_schema(
            show_export_key=not has_export_key,
            show_import_key=not has_import_key,
            name=current_name,
            export_key=current_export_key,
            use_group_filter=current_use_group_filter,
            group_id=current_group_id,
            scan_interval=current_scan_interval,
            timeout=current_timeout,
            overdue_tolerance=current_overdue_tolerance,
            overdue_notification=current_overdue_notification,
            push_enabled=current_push_enabled,
            import_key=current_import_key,
            label=current_label,
            prefix=current_prefix,
            push_interval=current_push_interval,
            send_only_changed=current_send_only_changed,
        )
        schema = self.add_suggested_values_to_schema(
            schema,
            {CONF_PREFIX: current_prefix},
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
