"""Home Assistant integration for the Chirp disk and CPU monitor."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChirpApi
from .const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL, DOMAIN
from .coordinator import ChirpCoordinator, scan_interval_from_options
from .entity import host_device_info

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


@dataclass
class ChirpRuntimeData:
    """Objects shared by the integration platforms."""

    coordinator: ChirpCoordinator


ChirpConfigEntry = ConfigEntry[ChirpRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ChirpConfigEntry) -> bool:
    """Set up Chirp from a config entry."""
    api = ChirpApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_API_KEY],
        entry.data[CONF_SSL],
    )
    coordinator = ChirpCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = ChirpRuntimeData(coordinator)

    # Disk devices reference the host through via_device, so create it first.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **host_device_info(entry, coordinator.data)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hasattr(config_entries, "OptionsFlowWithReload"):
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChirpConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ChirpConfigEntry) -> None:
    """Reload when the polling interval option changes."""
    coordinator = entry.runtime_data.coordinator
    if scan_interval_from_options(entry.options) != coordinator.update_interval:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ChirpConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow deleting only disk devices that are gone from the server."""
    coordinator = entry.runtime_data.coordinator
    instance_id = coordinator.instance_id
    prefix = f"{instance_id}_"
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == instance_id or not identifier.startswith(prefix):
            return False
        return coordinator.get_disk(identifier[len(prefix) :]) is None
    return False
