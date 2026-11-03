"""Sensors for the monitored host and its disks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import ChirpConfigEntry
from .const import HEALTH_STATES
from .coordinator import ChirpCoordinator
from .entity import ChirpDiskEntity, ChirpEntity, is_provisional_disk

PARALLEL_UPDATES = 0

# Uptime and collection timestamps jitter by a second or two between polls.
_BOOT_TIME_TOLERANCE = timedelta(seconds=10)
_NVME_DATA_UNIT_BYTES = 512_000


def _number(value: Any) -> float | int | None:
    """Return numbers unchanged and everything else (None, bool, str) as None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


@dataclass(frozen=True, kw_only=True)
class ChirpSensorDescription(SensorEntityDescription):
    """Describe a host-level sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _status: True
    placeholders: dict[str, str] | None = None


@dataclass(frozen=True, kw_only=True)
class ChirpDiskSensorDescription(SensorEntityDescription):
    """Describe a per-disk sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _disk: True
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _cpu(status: dict[str, Any]) -> dict[str, Any]:
    cpu = status.get("cpu")
    return cpu if isinstance(cpu, dict) else {}


def _boot_time(status: dict[str, Any]) -> datetime | None:
    instance = status.get("instance") or {}
    uptime = _number(instance.get("uptimeSeconds"))
    collected = dt_util.parse_datetime(str(instance.get("collectedAt") or ""))
    if uptime is None or collected is None:
        return None
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=dt_util.UTC)
    return collected - timedelta(seconds=uptime)


HOST_SENSORS: tuple[ChirpSensorDescription, ...] = (
    ChirpSensorDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda status: _number(_cpu(status).get("packageTemp")),
        exists_fn=lambda status: _number(_cpu(status).get("packageTemp")) is not None,
    ),
    ChirpSensorDescription(
        key="cpu_max_temperature",
        translation_key="cpu_max_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda status: _number(_cpu(status).get("maxTemp")),
        exists_fn=lambda status: _number(_cpu(status).get("maxTemp")) is not None,
    ),
    ChirpSensorDescription(
        key="boot_time",
        translation_key="boot_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_boot_time,
        exists_fn=lambda status: _boot_time(status) is not None,
    ),
)


def _core_keys(status: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(stable key, core)`` for every CPU core in a snapshot.

    The key comes from the core's label (``"Core 0"`` -> ``core_0``) so that a
    server that lists the cores in another order still maps each value to the
    same entity. A core without a usable label falls back to its position, and
    a repeated label (for example ``Core 0`` on each socket) gets a ``_2``,
    ``_3`` ... suffix in the order the server reports it.
    """
    cores = _cpu(status).get("cores")
    result: list[tuple[str, dict[str, Any]]] = []
    seen: dict[str, int] = {}
    for index, core in enumerate(cores if isinstance(cores, list) else []):
        if not isinstance(core, dict):
            continue
        base = slugify(str(core.get("label") or "")) or f"index_{index}"
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base}_{seen[base]}"
        result.append((key, core))
    return result


def _core(status: dict[str, Any], key: str) -> dict[str, Any] | None:
    return next((core for k, core in _core_keys(status) if k == key), None)


def _core_descriptions(status: dict[str, Any]) -> list[ChirpSensorDescription]:
    """Build one disabled-by-default sensor per CPU core reported by the server."""
    descriptions: list[ChirpSensorDescription] = []
    for index, (core_key, core) in enumerate(_core_keys(status)):

        def value_fn(data: dict[str, Any], key: str = core_key) -> float | int | None:
            found = _core(data, key)
            return None if found is None else _number(found.get("temp"))

        descriptions.append(
            ChirpSensorDescription(
                key=f"cpu_core_temperature_{core_key}",
                translation_key="cpu_core_temperature",
                device_class=SensorDeviceClass.TEMPERATURE,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=1,
                entity_registry_enabled_default=False,
                placeholders={"core": str(core.get("label") or f"Core {index}")},
                value_fn=value_fn,
                exists_fn=lambda data, key=core_key: _core(data, key) is not None,
            )
        )
    return descriptions


def _ata(disk: dict[str, Any], field: str) -> float | int | None:
    ata = disk.get("ata")
    return _number(ata.get(field)) if isinstance(ata, dict) else None


def _nvme(disk: dict[str, Any], field: str) -> float | int | None:
    nvme = disk.get("nvme")
    return _number(nvme.get(field)) if isinstance(nvme, dict) else None


def _has_ata(disk: dict[str, Any]) -> bool:
    return isinstance(disk.get("ata"), dict)


def _has_nvme(disk: dict[str, Any]) -> bool:
    return isinstance(disk.get("nvme"), dict)


def _has_wear(disk: dict[str, Any]) -> bool:
    if _has_nvme(disk):
        return True
    return _has_ata(disk) and disk.get("kind") == "ssd"


def _wear(disk: dict[str, Any]) -> float | int | None:
    if _has_nvme(disk):
        return _nvme(disk, "percentageUsed")
    return _ata(disk, "wearLevelPercentUsed")


def _data_written_tb(disk: dict[str, Any]) -> float | None:
    written = _nvme(disk, "bytesWritten")
    if written is None:
        units = _nvme(disk, "dataUnitsWritten")
        if units is None:
            return None
        written = units * _NVME_DATA_UNIT_BYTES
    return written / 1e12


def _health_status(disk: dict[str, Any]) -> str | None:
    """Return the server's health verdict, or None (HA "unknown") otherwise.

    Chirp's own ``unknown`` verdict (disk not read yet, standby since start or
    unreadable) is reported as Home Assistant's unknown state instead of an
    ENUM option of the same name, matching the SMART problem binary sensor.
    """
    health = disk.get("health")
    status = health.get("status") if isinstance(health, dict) else None
    return status if status in HEALTH_STATES else None


def _health_reasons(disk: dict[str, Any]) -> list[dict[str, Any]]:
    health = disk.get("health")
    reasons = health.get("reasons") if isinstance(health, dict) else None
    return [
        {"code": reason.get("code"), "value": reason.get("value")}
        for reason in (reasons if isinstance(reasons, list) else [])
        if isinstance(reason, dict)
    ]


def _count_description(
    key: str,
    field: str,
    getter: Callable[[dict[str, Any], str], float | int | None],
    exists: Callable[[dict[str, Any]], bool],
    *,
    diagnostic: bool,
) -> ChirpDiskSensorDescription:
    return ChirpDiskSensorDescription(
        key=key,
        translation_key=key,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        value_fn=lambda disk: getter(disk, field),
        exists_fn=exists,
    )


DISK_SENSORS: tuple[ChirpDiskSensorDescription, ...] = (
    ChirpDiskSensorDescription(
        key="temperature",
        translation_key="disk_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda disk: _number(disk.get("temperature")),
        attrs_fn=lambda disk: {"standby": bool(disk.get("standby"))},
    ),
    ChirpDiskSensorDescription(
        key="power_on_hours",
        translation_key="power_on_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda disk: _number(disk.get("powerOnHours")),
    ),
    ChirpDiskSensorDescription(
        key="power_cycle_count",
        translation_key="power_cycle_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda disk: _number(disk.get("powerCycleCount")),
    ),
    ChirpDiskSensorDescription(
        key="health",
        translation_key="health",
        device_class=SensorDeviceClass.ENUM,
        options=HEALTH_STATES,
        value_fn=_health_status,
        attrs_fn=lambda disk: {"reasons": _health_reasons(disk)},
    ),
    _count_description(
        "reallocated_sectors", "reallocatedSectors", _ata, _has_ata, diagnostic=False
    ),
    _count_description(
        "pending_sectors", "pendingSectors", _ata, _has_ata, diagnostic=False
    ),
    _count_description(
        "offline_uncorrectable",
        "offlineUncorrectable",
        _ata,
        _has_ata,
        diagnostic=True,
    ),
    _count_description(
        "udma_crc_errors", "udmaCrcErrors", _ata, _has_ata, diagnostic=True
    ),
    ChirpDiskSensorDescription(
        key="wear",
        translation_key="wear",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wear,
        exists_fn=_has_wear,
    ),
    ChirpDiskSensorDescription(
        key="available_spare",
        translation_key="available_spare",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda disk: _nvme(disk, "availableSpare"),
        exists_fn=_has_nvme,
    ),
    ChirpDiskSensorDescription(
        key="data_written",
        translation_key="data_written",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.TERABYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=_data_written_tb,
        exists_fn=_has_nvme,
    ),
    _count_description(
        "media_errors", "mediaErrors", _nvme, _has_nvme, diagnostic=True
    ),
    _count_description(
        "unsafe_shutdowns", "unsafeShutdowns", _nvme, _has_nvme, diagnostic=True
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChirpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors now and whenever new disks or cores show up."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        status = coordinator.data
        instance_id = coordinator.instance_id
        new: list[SensorEntity] = []
        for host_description in (*HOST_SENSORS, *_core_descriptions(status)):
            unique_id = f"{instance_id}_{host_description.key}"
            if unique_id not in known and host_description.exists_fn(status):
                known.add(unique_id)
                new.append(ChirpHostSensor(coordinator, entry, host_description))
        for disk in status["disks"]:
            if is_provisional_disk(disk):
                continue
            for disk_description in DISK_SENSORS:
                unique_id = f"{instance_id}_{disk['id']}_{disk_description.key}"
                if unique_id not in known and disk_description.exists_fn(disk):
                    known.add(unique_id)
                    new.append(
                        ChirpDiskSensor(coordinator, entry, disk_description, disk)
                    )
        if new:
            async_add_entities(new)

    # Fetch errors are always present, independent of what the server reports.
    async_add_entities([ChirpFetchErrorSensor(coordinator, entry)])
    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class ChirpHostSensor(ChirpEntity, SensorEntity):
    """A sensor describing the monitored host."""

    entity_description: ChirpSensorDescription

    def __init__(
        self,
        coordinator: ChirpCoordinator,
        entry: ChirpConfigEntry,
        description: ChirpSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description)
        if description.placeholders:
            self._attr_translation_placeholders = description.placeholders
        self._last_datetime: datetime | None = None

    @property
    def native_value(self) -> Any:
        """Return the sensor value from the latest snapshot."""
        value = self.entity_description.value_fn(self.status)
        if isinstance(value, datetime):
            last = self._last_datetime
            if last is not None and abs(value - last) <= _BOOT_TIME_TOLERANCE:
                return last
            self._last_datetime = value
        return value


class ChirpFetchErrorSensor(ChirpEntity, SensorEntity):
    """Number of consecutive failed polls; attributes describe the last error."""

    def __init__(self, coordinator: ChirpCoordinator, entry: ChirpConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            SensorEntityDescription(
                key="fetch_errors",
                translation_key="fetch_errors",
                entity_category=EntityCategory.DIAGNOSTIC,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )

    @property
    def available(self) -> bool:
        """Stay available while the server is down; that is what it reports."""
        return True

    @property
    def native_value(self) -> int:
        """Return the consecutive error count."""
        return self.coordinator.consecutive_errors

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the latest failure and success."""
        return {
            "last_error": self.coordinator.last_error,
            "last_error_at": self.coordinator.last_error_at,
            "last_success_at": self.coordinator.last_success_at,
        }


class ChirpDiskSensor(ChirpDiskEntity, SensorEntity):
    """A sensor describing one disk."""

    entity_description: ChirpDiskSensorDescription

    @property
    def native_value(self) -> Any:
        """Return the sensor value from the latest snapshot."""
        disk = self.disk
        return None if disk is None else self.entity_description.value_fn(disk)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes for this sensor."""
        disk = self.disk
        attrs_fn = self.entity_description.attrs_fn
        if disk is None or attrs_fn is None:
            return None
        return attrs_fn(disk)
