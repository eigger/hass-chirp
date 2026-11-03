"""Shared base entities and device helpers for Chirp."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import build_base_url
from .const import CONF_HOST, CONF_PORT, CONF_SSL, DOMAIN, MANUFACTURER
from .coordinator import ChirpCoordinator


def dashboard_url(entry: ConfigEntry) -> str:
    """Return the Chirp dashboard URL for an entry."""
    host = entry.data[CONF_HOST]
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return build_base_url(host, int(entry.data[CONF_PORT]), bool(entry.data[CONF_SSL]))


def host_device_info(entry: ConfigEntry, status: dict[str, Any]) -> DeviceInfo:
    """Build the DeviceInfo of the monitored host."""
    instance = status["instance"]
    return DeviceInfo(
        identifiers={(DOMAIN, str(instance["id"]))},
        name=str(instance.get("hostname") or "Chirp"),
        manufacturer=MANUFACTURER,
        model=(status.get("cpu") or {}).get("model"),
        sw_version=instance.get("version"),
        configuration_url=dashboard_url(entry),
    )


def is_provisional_disk(disk: dict[str, Any]) -> bool:
    """Return True for a disk whose ID is only a placeholder.

    Chirp normally derives a disk's final ID (WWN or model+serial) without
    reading the disk. Only when the identity cannot be derived (for example a
    disk behind a SAS HBA or USB bridge that is in standby at server start) does
    it use ``dev_<device name>`` until the first read. The real ID then replaces
    it, so creating entities for the placeholder would leave orphaned devices
    behind and could later attach another disk that reuses the device name. A ``dev_`` ID of a disk that has been read is
    permanent (the disk reports no identity) and is used as-is.
    """
    return str(disk.get("id", "")).startswith("dev_") and not disk.get("lastReadAt")


def disk_device_name(disk: dict[str, Any]) -> str:
    """Return ``model (last four serial characters)`` for a disk."""
    model = disk.get("model") or disk.get("name") or disk.get("id") or "Disk"
    serial = disk.get("serial")
    return f"{model} ({str(serial)[-4:]})" if serial else str(model)


# Newer Home Assistant releases replace ``via_device`` with ``via_device_id``.
_USES_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


def disk_device_info(
    hass: HomeAssistant,
    entry: ConfigEntry,
    instance_id: str,
    disk: dict[str, Any],
) -> DeviceInfo:
    """Build the DeviceInfo of one disk, attached to the host device."""
    info = DeviceInfo(
        identifiers={(DOMAIN, f"{instance_id}_{disk['id']}")},
        name=disk_device_name(disk),
        model=disk.get("model"),
        serial_number=disk.get("serial"),
        sw_version=disk.get("firmware"),
    )
    if not _USES_VIA_DEVICE_ID:
        info["via_device"] = (DOMAIN, instance_id)  # type: ignore[typeddict-unknown-key]
        return info
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        if (DOMAIN, instance_id) in device.identifiers:
            info["via_device_id"] = device.id  # type: ignore[typeddict-unknown-key]
            break
    return info


class ChirpEntity(CoordinatorEntity[ChirpCoordinator]):
    """Base class for entities that belong to the monitored host."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChirpCoordinator,
        entry: ConfigEntry,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._instance_id = coordinator.instance_id
        self._attr_unique_id = f"{self._instance_id}_{description.key}"
        self._attr_device_info = host_device_info(entry, coordinator.data)

    @property
    def status(self) -> dict[str, Any]:
        """Return the latest status snapshot."""
        return self.coordinator.data


class ChirpDiskEntity(CoordinatorEntity[ChirpCoordinator]):
    """Base class for entities that belong to one disk."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChirpCoordinator,
        entry: ConfigEntry,
        description: EntityDescription,
        disk: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._instance_id = coordinator.instance_id
        self._disk_id: str = disk["id"]
        self._attr_unique_id = f"{self._instance_id}_{self._disk_id}_{description.key}"
        self._attr_device_info = disk_device_info(
            coordinator.hass, entry, self._instance_id, disk
        )

    @property
    def disk(self) -> dict[str, Any] | None:
        """Return this disk's latest data, or None when it vanished."""
        return self.coordinator.get_disk(self._disk_id)

    @property
    def available(self) -> bool:
        """Disks missing from the latest response become unavailable."""
        return super().available and self.disk is not None
