from __future__ import annotations

import asyncio

import voluptuous as vol
from aiohttp import ClientError, ContentTypeError
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_EXPORT_KEY,
    CONF_IMPORT_KEY,
    CONF_LABEL,
    CONF_OVERDUE_TOLERANCE,
    CONF_PREFIX,
    CONF_PUSH_ENABLED,
    CONF_PUSH_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    DEFAULT_IMPORT_KEY,
    DEFAULT_LABEL,
    DEFAULT_OVERDUE_TOLERANCE,
    DEFAULT_PREFIX,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    ZIVY_OBRAZ_EXPORT_URL,
)


async def _validate_input(hass, data: dict) -> dict:
    """Validate the user input."""
    session = async_get_clientsession(hass)
    timeout = data[CONF_TIMEOUT]
    url = f"{ZIVY_OBRAZ_EXPORT_URL}?export_key={data[CONF_EXPORT_KEY]}&epapers=json"

    async with asyncio.timeout(timeout):
        async with session.get(url, headers={"Accept": "application/json"}) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)

    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON must be an object/dict")

    return {"title": "Živý Obraz"}


def _validate_push_settings(data: dict) -> None:
    """Validate push-related settings."""
    if data.get(CONF_PUSH_ENABLED) and not data.get(CONF_IMPORT_KEY, "").strip():
        raise ValueError("import_key_required")


def _build_schema(
    *,
    export_key: str | None = None,
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    timeout: int = DEFAULT_TIMEOUT,
    overdue_tolerance: int = DEFAULT_OVERDUE_TOLERANCE,
    push_enabled: bool = DEFAULT_PUSH_ENABLED,
    import_key: str = DEFAULT_IMPORT_KEY,
    label: str = DEFAULT_LABEL,
    prefix: str = DEFAULT_PREFIX,
    push_interval: int = DEFAULT_PUSH_INTERVAL,
) -> vol.Schema:
    """Build config schema."""
    return vol.Schema(
        {
            vol.Required(CONF_EXPORT_KEY, default=export_key or ""): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int),
                vol.Range(min=30, max=86400),
            ),
            vol.Optional(CONF_TIMEOUT, default=timeout): vol.All(
                vol.Coerce(int),
                vol.Range(min=5, max=120),
            ),
            vol.Optional(CONF_OVERDUE_TOLERANCE, default=overdue_tolerance): vol.All(
                vol.Coerce(int),
                vol.Range(min=0, max=10080),
            ),
            vol.Optional(CONF_PUSH_ENABLED, default=push_enabled): bool,
            vol.Optional(CONF_IMPORT_KEY, default=import_key): str,
            vol.Optional(CONF_LABEL, default=label): str,
            vol.Optional(CONF_PREFIX, default=prefix): str,
            vol.Optional(CONF_PUSH_INTERVAL, default=push_interval): vol.All(
                vol.Coerce(int),
                vol.Range(min=30, max=86400),
            ),
        }
    )


class ZivyObrazConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zivy Obraz."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EXPORT_KEY])
            self._abort_if_unique_id_configured()

            try:
                _validate_push_settings(user_input)
                info = await _validate_input(self.hass, user_input)
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
                    errors["base"] = "invalid_json"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return ZivyObrazOptionsFlow(config_entry)


class ZivyObrazOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Zivy Obraz."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}

        current_export_key = self._config_entry.options.get(
            CONF_EXPORT_KEY,
            self._config_entry.data.get(CONF_EXPORT_KEY, ""),
        )
        current_scan_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_timeout = self._config_entry.options.get(
            CONF_TIMEOUT,
            self._config_entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        )
        current_overdue_tolerance = self._config_entry.options.get(
            CONF_OVERDUE_TOLERANCE,
            self._config_entry.data.get(CONF_OVERDUE_TOLERANCE, DEFAULT_OVERDUE_TOLERANCE),
        )
        current_push_enabled = self._config_entry.options.get(
            CONF_PUSH_ENABLED,
            self._config_entry.data.get(CONF_PUSH_ENABLED, DEFAULT_PUSH_ENABLED),
        )
        current_import_key = self._config_entry.options.get(
            CONF_IMPORT_KEY,
            self._config_entry.data.get(CONF_IMPORT_KEY, DEFAULT_IMPORT_KEY),
        )
        current_label = self._config_entry.options.get(
            CONF_LABEL,
            self._config_entry.data.get(CONF_LABEL, DEFAULT_LABEL),
        )
        current_prefix = self._config_entry.options.get(
            CONF_PREFIX,
            self._config_entry.data.get(CONF_PREFIX, DEFAULT_PREFIX),
        )
        current_push_interval = self._config_entry.options.get(
            CONF_PUSH_INTERVAL,
            self._config_entry.data.get(CONF_PUSH_INTERVAL, DEFAULT_PUSH_INTERVAL),
        )

        if user_input is not None:
            try:
                _validate_push_settings(user_input)
                await _validate_input(self.hass, user_input)
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
                    errors["base"] = "invalid_json"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(
                export_key=current_export_key,
                scan_interval=current_scan_interval,
                timeout=current_timeout,
                overdue_tolerance=current_overdue_tolerance,
                push_enabled=current_push_enabled,
                import_key=current_import_key,
                label=current_label,
                prefix=current_prefix,
                push_interval=current_push_interval,
            ),
            errors=errors,
        )
