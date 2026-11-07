"""Home Assistant integration for the Chirp disk and host monitor."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChirpApi
from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PORT,
    CONF_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import ChirpCoordinator, scan_interval_from_options
from .entity import INTERFACE_DEVICE_INFIX, host_device_info
from .groups import group_options, sync_group_registry

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

# Entities earlier releases created that are gone now: (platform, unique ID suffix).
# "Any disk problem" on the host duplicated every disk's own SMART problem sensor;
# each disk's "Last successful SMART read" timestamp (logged every SMART cycle) is
# now the `last_read_at` attribute of its "SMART collection problem" sensor.
_RETIRED_HOST_ENTITIES = ((Platform.BINARY_SENSOR, "any_disk_problem"),)
_RETIRED_DISK_ENTITIES = ((Platform.SENSOR, "last_read_at"),)


@dataclass
class ChirpRuntimeData:
    """Objects shared by the integration platforms."""

    coordinator: ChirpCoordinator
    sensor_groups: dict[str, bool] = field(default_factory=lambda: group_options({}))
    # Each platform registers a callback that forgets the unique IDs it created
    # for a removed disk or interface device, so they are created again if
    # that disk or interface comes back later in the same session.
    forget_device_callbacks: list[Callable[[str, str], None]] = field(
        default_factory=list
    )
    # Devices the user asked to delete, by device ID: (kind, disk/interface ID).
    # The unique IDs are forgotten only once the registry really removed them.
    pending_device_removals: dict[str, tuple[str, str]] = field(default_factory=dict)


ChirpConfigEntry = ConfigEntry[ChirpRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ChirpConfigEntry) -> bool:
    """Set up Chirp from a config entry."""
    api = ChirpApi(
        async_get_clientsession(
            hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        ),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_API_KEY],
        entry.data[CONF_SSL],
    )
    coordinator = ChirpCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = ChirpRuntimeData(
        coordinator, sensor_groups=group_options(dict(entry.options))
    )
    _remove_retired_entities(hass, entry, coordinator.instance_id)
    sync_group_registry(hass, entry, coordinator.instance_id)

    # Disk devices reference the host through via_device, so create it first.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **host_device_info(entry, coordinator.data)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            partial(_async_device_registry_updated, entry),
        )
    )
    if not hasattr(config_entries, "OptionsFlowWithReload"):
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChirpConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ChirpConfigEntry) -> None:
    """Reload older HA releases when the interval or selected groups change."""
    coordinator = entry.runtime_data.coordinator
    if (
        scan_interval_from_options(entry.options) != coordinator.update_interval
        or group_options(dict(entry.options)) != entry.runtime_data.sensor_groups
    ):
        await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_device_registry_updated(
    entry: ChirpConfigEntry, event: Event[dr.EventDeviceRegistryUpdatedData]
) -> None:
    """Forget the unique IDs of a disk or interface device once it is removed.

    ``async_remove_config_entry_device`` only allows the removal; Home
    Assistant may still not remove the device. Forgetting the IDs earlier
    would re-add entities that are still registered when the item returns.
    """
    if event.data["action"] != "remove":
        return
    removal = entry.runtime_data.pending_device_removals.pop(
        event.data["device_id"], None
    )
    if removal is None:
        return
    for forget in entry.runtime_data.forget_device_callbacks:
        forget(*removal)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ChirpConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow deleting only disk and interface devices gone from the server."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    instance_id = coordinator.instance_id
    interface_prefix = f"{instance_id}{INTERFACE_DEVICE_INFIX}"
    disk_prefix = f"{instance_id}_"
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == instance_id:
            return False
        if identifier.startswith(interface_prefix):
            kind, child = "interface", identifier[len(interface_prefix) :]
            present = coordinator.get_interface(child) is not None
        elif identifier.startswith(disk_prefix):
            kind, child = "disk", identifier[len(disk_prefix) :]
            present = coordinator.get_disk(child) is not None
        else:
            return False
        if present:
            return False
        runtime_data.pending_device_removals[device_entry.id] = (kind, child)
        return True
    return False


@callback
def _remove_retired_entities(
    hass: HomeAssistant, entry: ConfigEntry, instance_id: str
) -> None:
    """Drop registry entries of entities this integration no longer creates."""
    registry = er.async_get(hass)
    retired_host = {
        f"{instance_id}_{key}": domain for domain, key in _RETIRED_HOST_ENTITIES
    }
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if retired_host.get(entity.unique_id) == entity.domain or any(
            entity.domain == domain
            and entity.unique_id.startswith(f"{instance_id}_")
            and entity.unique_id.endswith(f"_{key}")
            for domain, key in _RETIRED_DISK_ENTITIES
        ):
            _LOGGER.warning(
                "Removing %s: this entity was retired (see the release notes)",
                entity.entity_id,
            )
            registry.async_remove(entity.entity_id)
