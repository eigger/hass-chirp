"""Diagnostics for the Chirp integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ChirpConfigEntry
from .const import CONF_API_KEY, CONF_HOST

TO_REDACT = {
    CONF_API_KEY,
    CONF_HOST,
    "serial",
    "serial_number",
    "wwn",
    "devicePath",
    "id",
    "hostname",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChirpConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT
        ),
        "coordinator": {
            "update_interval": str(coordinator.update_interval),
            "last_update_success": coordinator.last_update_success,
            "consecutive_errors": coordinator.consecutive_errors,
            "last_error": coordinator.last_error,
            "last_error_at": coordinator.last_error_at,
            "last_success_at": coordinator.last_success_at,
        },
        "status": async_redact_data(coordinator.data, TO_REDACT),
    }
