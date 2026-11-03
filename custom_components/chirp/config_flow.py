"""Config flow for the Chirp integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    ChirpApi,
    ChirpAuthError,
    ChirpConnectionError,
    ChirpError,
    normalize_host,
)
from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

# Newer Home Assistant reloads the entry itself when options change; older
# releases need the update listener registered in ``__init__``.
_OptionsFlowBase: type[OptionsFlow] = getattr(
    config_entries, "OptionsFlowWithReload", OptionsFlow
)

_PORT = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
_API_KEY = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _connection_schema(*, with_key: bool) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): _PORT,
    }
    if with_key:
        fields[vol.Required(CONF_API_KEY)] = _API_KEY
    fields[vol.Required(CONF_SSL, default=DEFAULT_SSL)] = bool
    return vol.Schema(fields)


async def _validate(
    flow: ConfigFlow,
    host: str,
    port: int,
    api_key: str,
    use_ssl: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(status, None)`` on success or ``(None, error_key)``."""
    try:
        api = ChirpApi(async_get_clientsession(flow.hass), host, port, api_key, use_ssl)
    except ValueError:
        return None, "invalid_host"
    try:
        return await api.async_get_status(), None
    except ChirpAuthError:
        return None, "invalid_auth"
    except ChirpConnectionError:
        return None, "cannot_connect"
    except ChirpError:
        return None, "unknown"


class ChirpConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect Home Assistant to one Chirp server."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host, port, API key and SSL flag."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            api_key = user_input[CONF_API_KEY].strip()
            use_ssl = bool(user_input[CONF_SSL])
            status, error = await _validate(self, host, port, api_key, use_ssl)
            if status is None:
                errors["base"] = error or "unknown"
            else:
                instance = status["instance"]
                await self.async_set_unique_id(str(instance["id"]))
                host = normalize_host(host).strip("[]")
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host, CONF_PORT: port, CONF_SSL: use_ssl}
                )
                return self.async_create_entry(
                    title=str(instance.get("hostname") or "Chirp"),
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_API_KEY: api_key,
                        CONF_SSL: use_ssl,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(with_key=True), user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start re-authentication after the server rejected the API key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a replacement API key for the same Chirp instance."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            status, error = await _validate(
                self,
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                api_key,
                entry.data[CONF_SSL],
            )
            if status is None:
                errors["base"] = error or "unknown"
            elif str(status["instance"]["id"]) != entry.unique_id:
                errors["base"] = "wrong_instance"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _API_KEY}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of an existing Chirp server."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            use_ssl = bool(user_input[CONF_SSL])
            status, error = await _validate(
                self, host, port, entry.data[CONF_API_KEY], use_ssl
            )
            if status is None:
                errors["base"] = error or "unknown"
            else:
                await self.async_set_unique_id(str(status["instance"]["id"]))
                self._abort_if_unique_id_mismatch(reason="wrong_instance")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: normalize_host(host).strip("[]"),
                        CONF_PORT: port,
                        CONF_SSL: use_ssl,
                    },
                )

        suggested = user_input or {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PORT: entry.data[CONF_PORT],
            CONF_SSL: entry.data[CONF_SSL],
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(with_key=False), suggested
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return ChirpOptionsFlow()


class ChirpOptionsFlow(_OptionsFlowBase):
    """Let the user tune the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the polling interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
