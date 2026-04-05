from __future__ import annotations

import asyncio
import math
from typing import Any

import voluptuous as vol
from aiohttp import ClientError, ContentTypeError
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_EXPORT_KEY,
    CONF_GROUP_ID,
    CONF_IMPORT_KEY,
    CONF_LABEL,
    CONF_OVERDUE_NOTIFICATION,
    CONF_OVERDUE_TOLERANCE,
    CONF_PREFIX,
    CONF_PREFIX_OVERRIDE,
    CONF_PUSH_ENABLED,
    CONF_PUSH_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USE_GROUP_FILTER,
    DEFAULT_IMPORT_KEY,
    DEFAULT_LABEL,
    DEFAULT_OVERDUE_NOTIFICATION,
    DEFAULT_OVERDUE_TOLERANCE,
    DEFAULT_PREFIX,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_GROUP_FILTER,
    DOMAIN,
    ZIVY_OBRAZ_EXPORT_URL,
)


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

    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON must be an object/dict")

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


def _normalize_group_id(value: str | None) -> int | None:
    """Normalize optional group_id from UI input."""
    if value is None:
        return None

    value = str(value).strip()
    if value == "":
        return None

    group_id = int(value)
    if group_id < 0:
        raise ValueError("invalid_group_id")

    return group_id


def _prepare_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Ensure fields are stored in a predictable format."""
    prepared = dict(user_input)

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

    # Enforce minimum interval of 60 seconds
    scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    push_interval = int(user_input.get(CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL))

    scan_interval = max(scan_interval, 60)
    push_interval = max(push_interval, 60)

    prepared[CONF_SCAN_INTERVAL] = scan_interval
    prepared[CONF_PUSH_INTERVAL] = push_interval

    # overdue_tolerance is in minutes and must be at least the scan interval
    overdue_tolerance = int(
        user_input.get(CONF_OVERDUE_TOLERANCE, DEFAULT_OVERDUE_TOLERANCE)
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
) -> vol.Schema:
    """Build config schema."""
    schema: dict[Any, Any] = {}

    if show_export_key:
        schema[vol.Required(CONF_EXPORT_KEY, default=export_key or "")] = str

    schema[vol.Optional(CONF_USE_GROUP_FILTER, default=use_group_filter)] = bool
    schema[vol.Optional(CONF_GROUP_ID, default=group_id)] = str
    schema[vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval)] = vol.All(
        vol.Coerce(int),
        vol.Range(min=60, max=86400),
    )
    schema[vol.Required(CONF_TIMEOUT, default=timeout)] = vol.All(
        vol.Coerce(int),
        vol.Range(min=5, max=120),
    )
    schema[vol.Optional(CONF_OVERDUE_NOTIFICATION, default=overdue_notification)] = bool
    schema[vol.Optional(CONF_OVERDUE_TOLERANCE, default=overdue_tolerance)] = vol.All(
        vol.Coerce(int),
        vol.Range(min=0, max=10080),
    )
    schema[vol.Optional(CONF_PUSH_ENABLED, default=push_enabled)] = bool

    if show_import_key:
        schema[vol.Optional(CONF_IMPORT_KEY, default=import_key)] = str

    schema[vol.Optional(CONF_LABEL, default=label)] = str
    schema[vol.Optional(CONF_PREFIX)] = str
    schema[vol.Optional(CONF_PUSH_INTERVAL, default=push_interval)] = vol.All(
        vol.Coerce(int),
        vol.Range(min=60, max=86400),
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

                info = await _validate_input(self.hass, prepared_input)

            except TimeoutError:
                errors["base"] = "timeout"
            except ClientError:
                errors["base"] = "cannot_connect"
            except ContentTypeError:
                errors["base"] = "invalid_json"
            except ValueError as err:
                if str(err) == "import_key_required":
                    errors["base"] = "import_key_required"
                elif str(err) == "invalid_group_id":
                    errors["base"] = "invalid_group_id"
                elif str(err) == "group_id_required":
                    errors["base"] = "group_id_required"
                else:
                    errors["base"] = "invalid_json"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=prepared_input)

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
                elif str(err) == "invalid_group_id":
                    errors["base"] = "invalid_group_id"
                elif str(err) == "group_id_required":
                    errors["base"] = "group_id_required"
                else:
                    errors["base"] = "invalid_json"
            except Exception:
                errors["base"] = "unknown"
            else:
                prepared_input[CONF_PREFIX_OVERRIDE] = True
                return self.async_create_entry(title="", data=prepared_input)

        schema = _build_schema(
            show_export_key=not has_export_key,
            show_import_key=not has_import_key,
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
