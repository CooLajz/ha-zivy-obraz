from __future__ import annotations

import asyncio

import voluptuous as vol
from aiohttp import ClientError, ContentTypeError
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_OVERDUE_TOLERANCE,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_URL,
    DEFAULT_OVERDUE_TOLERANCE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


async def _validate_input(hass, data: dict) -> dict:
    """Validate the user input."""
    session = async_get_clientsession(hass)
    url = data[CONF_URL]
    timeout = data[CONF_TIMEOUT]

    async with asyncio.timeout(timeout):
        async with session.get(url, headers={"Accept": "application/json"}) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)

    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON must be an object/dict")

    return {"title": "Živý Obraz"}


def _build_schema(
    *,
    url: str | None = None,
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    timeout: int = DEFAULT_TIMEOUT,
    overdue_tolerance: int = DEFAULT_OVERDUE_TOLERANCE,
) -> vol.Schema:
    """Build config schema."""
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=url or ""): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int), vol.Range(min=30, max=86400)
            ),
            vol.Optional(CONF_TIMEOUT, default=timeout): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=120)
            ),
            vol.Optional(CONF_OVERDUE_TOLERANCE, default=overdue_tolerance): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=10080)
            ),
        }
    )


class ZivyObrazConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zivy Obraz."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_URL])
            self._abort_if_unique_id_configured()

            try:
                info = await _validate_input(self.hass, user_input)
            except TimeoutError:
                errors["base"] = "timeout"
            except ClientError:
                errors["base"] = "cannot_connect"
            except ContentTypeError:
                errors["base"] = "invalid_json"
            except ValueError:
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

        current_url = self._config_entry.options.get(
            CONF_URL,
            self._config_entry.data.get(CONF_URL, ""),
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

        if user_input is not None:
            try:
                await _validate_input(self.hass, user_input)
            except TimeoutError:
                errors["base"] = "timeout"
            except ClientError:
                errors["base"] = "cannot_connect"
            except ContentTypeError:
                errors["base"] = "invalid_json"
            except ValueError:
                errors["base"] = "invalid_json"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(
                url=current_url,
                scan_interval=current_scan_interval,
                timeout=current_timeout,
                overdue_tolerance=current_overdue_tolerance,
            ),
            errors=errors,
        )