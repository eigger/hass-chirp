"""Diagnostics for the Chirp integration."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant

from . import ChirpConfigEntry
from .const import CONF_API_KEY, CONF_HOST

TO_REDACT = {
    "group_disabled_entities",
    "path",
    CONF_API_KEY,
    CONF_HOST,
    "serial",
    "serial_number",
    "wwn",
    "devicePath",
    "id",
    "hostname",
}

# Predictable interface names of USB/onboard NICs can embed the MAC address
# (``enx001122334455``, ``wlx001122334455``). Mask any 12-hex-digit run or
# colon-separated MAC in an interface name. The ``id`` key is already redacted.
_MAC_RE = re.compile(r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|[0-9a-f]{12}")


def _redact_interface_names(status: dict[str, Any]) -> dict[str, Any]:
    network = status.get("network")
    if not isinstance(network, dict) or not isinstance(network.get("interfaces"), list):
        return status
    interfaces = [
        {**item, "name": _MAC_RE.sub(REDACTED, item["name"])}
        if isinstance(item, dict) and isinstance(item.get("name"), str)
        else item
        for item in network["interfaces"]
    ]
    return {**status, "network": {**network, "interfaces": interfaces}}


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
        "status": _redact_interface_names(
            async_redact_data(coordinator.data, TO_REDACT)
        ),
    }
