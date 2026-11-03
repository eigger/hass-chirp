"""Problem binary sensors for the monitored host and its disks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ChirpConfigEntry
from .const import HEALTH_FAILING, HEALTH_OK, HEALTH_WARNING
from .coordinator import ChirpCoordinator
from .entity import ChirpDiskEntity, ChirpEntity, is_provisional_disk
from .sensor import _health_reasons, _health_status

PARALLEL_UPDATES = 0

_PROBLEM_STATES = (HEALTH_WARNING, HEALTH_FAILING)


@dataclass(frozen=True, kw_only=True)
class ChirpBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a host-level binary sensor."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]


@dataclass(frozen=True, kw_only=True)
class ChirpDiskBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a per-disk binary sensor."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _disk_problem(disk: dict[str, Any]) -> bool | None:
    status = _health_status(disk)
    if status in _PROBLEM_STATES:
        return True
    return False if status == HEALTH_OK else None


HOST_BINARY_SENSORS: tuple[ChirpBinarySensorDescription, ...] = (
    ChirpBinarySensorDescription(
        key="any_disk_problem",
        translation_key="any_disk_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda status: any(
            _disk_problem(disk) is True for disk in status["disks"]
        ),
    ),
)

DISK_BINARY_SENSORS: tuple[ChirpDiskBinarySensorDescription, ...] = (
    ChirpDiskBinarySensorDescription(
        key="smart_problem",
        translation_key="smart_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=_disk_problem,
        attrs_fn=lambda disk: {
            "reasons": _health_reasons(disk),
            "smart_passed": disk.get("smartPassed"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChirpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create binary sensors now and for disks that appear later."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        status = coordinator.data
        instance_id = coordinator.instance_id
        new: list[BinarySensorEntity] = []
        for host_description in HOST_BINARY_SENSORS:
            unique_id = f"{instance_id}_{host_description.key}"
            if unique_id not in known:
                known.add(unique_id)
                new.append(ChirpHostBinarySensor(coordinator, entry, host_description))
        for disk in status["disks"]:
            if is_provisional_disk(disk):
                continue
            for disk_description in DISK_BINARY_SENSORS:
                unique_id = f"{instance_id}_{disk['id']}_{disk_description.key}"
                if unique_id not in known:
                    known.add(unique_id)
                    new.append(
                        ChirpDiskBinarySensor(
                            coordinator, entry, disk_description, disk
                        )
                    )
        if new:
            async_add_entities(new)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class ChirpHostBinarySensor(ChirpEntity, BinarySensorEntity):
    """A binary sensor describing the monitored host."""

    entity_description: ChirpBinarySensorDescription

    def __init__(
        self,
        coordinator: ChirpCoordinator,
        entry: ChirpConfigEntry,
        description: ChirpBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description)

    @property
    def is_on(self) -> bool | None:
        """Return True when any disk reports a problem."""
        return self.entity_description.is_on_fn(self.status)


class ChirpDiskBinarySensor(ChirpDiskEntity, BinarySensorEntity):
    """A binary sensor describing one disk."""

    entity_description: ChirpDiskBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return True when the disk is in warning or failing state."""
        disk = self.disk
        return None if disk is None else self.entity_description.is_on_fn(disk)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the health reasons and the raw SMART verdict."""
        disk = self.disk
        attrs_fn = self.entity_description.attrs_fn
        if disk is None or attrs_fn is None:
            return None
        return attrs_fn(disk)
