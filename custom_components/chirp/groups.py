"""Select entity groups while preserving registry settings across reloads."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity

GROUPS = ("cpu", "ram", "smart", "network", "hardware", "storage")
_DISABLED = "group_disabled_entities"
_EntityT = TypeVar("_EntityT", bound=Entity)


def group_options(options: dict) -> dict[str, bool]:
    """Existing entries enable every group by default."""
    return {
        f"monitor_{group}": options.get(f"monitor_{group}", True) for group in GROUPS
    }


def entity_group(unique_id: str, instance_id: str) -> str | None:
    """Classify the stable unique ID, independent of translated display names."""
    key = unique_id.removeprefix(f"{instance_id}_")
    if key in ("boot_time", "fetch_errors", "data_scope"):
        return None
    for group, prefixes in (
        ("network", ("net_",)),
        ("cpu", ("cpu_", "load_", "io_wait_percent")),
        ("ram", ("memory_", "swap_")),
        (
            "hardware",
            (
                "hardware_temperature_",
                "package_power",
                "power_source_",
                "fan_",
                "voltage_",
            ),
        ),
        ("storage", ("filesystem_", "zfs_pool_")),
    ):
        if key.startswith(prefixes):
            return group
    return "smart"


def selected_entities(
    entry: ConfigEntry, entities: Iterable[_EntityT]
) -> list[_EntityT]:
    """Only instantiate entities belonging to selected groups."""
    options = group_options(dict(entry.options))
    return [
        entity
        for entity in entities
        if (
            (group := entity_group(str(entity.unique_id), str(entry.unique_id))) is None
            or options[f"monitor_{group}"]
        )
    ]


@callback
def sync_group_registry(
    hass: HomeAssistant, entry: ConfigEntry, instance_id: str
) -> None:
    """Disable excluded groups and restore only entities disabled by this feature."""
    registry = er.async_get(hass)
    managed = set(entry.data.get(_DISABLED, []))
    previous = managed.copy()
    options = group_options(dict(entry.options))
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        group = entity_group(entity.unique_id, instance_id)
        enabled = group is None or options[f"monitor_{group}"]
        if not enabled and entity.disabled_by is None:
            managed.add(entity.unique_id)
            registry.async_update_entity(
                entity.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
            )
        elif enabled and entity.unique_id in managed:
            if entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(entity.entity_id, disabled_by=None)
            managed.discard(entity.unique_id)
    existing = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    managed.intersection_update(existing)
    if managed != previous:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, _DISABLED: sorted(managed)}
        )
