"""Sensors for the monitored host and its disks."""

from __future__ import annotations

import dataclasses
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
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfElectricPotential,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import ChirpConfigEntry
from .const import (
    DATA_SCOPES,
    HEALTH_FAILING,
    HEALTH_OK,
    HEALTH_STATES,
    HEALTH_WARNING,
    SCOPE_CONTAINER,
    SCOPE_HOST,
    SCOPE_MIXED,
    SCOPED_SECTIONS,
)
from .coordinator import COLLECTIONS, ChirpCoordinator, network_interfaces
from .entity import (
    ChirpDiskEntity,
    ChirpEntity,
    ChirpInterfaceEntity,
    disk_unique_id,
    interface_unique_id,
    is_provisional_disk,
    register_forget_device,
)

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
    # None: always available while the server answers. Host metric sensors
    # become unavailable when their section (or list item) is gone.
    available_fn: Callable[[dict[str, Any]], bool] | None = None
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
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
    # CPU package temperature
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
    # CPU maximum temperature
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
    # Host boot time
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


# Host metrics (memory, load, power, fans, voltages). Every section is
# optional: an older server does not send it and a newer one sends null when it
# could not be read. Sensors are created only once their section shows up, a
# null value inside a section is reported as unknown, and a sensor whose
# section (or list item) later disappears becomes unavailable.


def _section(status: dict[str, Any], name: str) -> dict[str, Any] | None:
    value = status.get(name)
    return value if isinstance(value, dict) else None


def _has_section(name: str) -> Callable[[dict[str, Any]], bool]:
    return lambda status: _section(status, name) is not None


def _section_value(name: str, field: str) -> Callable[[dict[str, Any]], Any]:
    def value_fn(status: dict[str, Any]) -> float | int | None:
        section = _section(status, name)
        return None if section is None else _number(section.get(field))

    return value_fn


def _scope_attrs(name: str) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    def attrs_fn(status: dict[str, Any]) -> dict[str, Any] | None:
        section = _section(status, name)
        return None if section is None else {"scope": section.get("scope")}

    return attrs_fn


def _load_attrs(status: dict[str, Any]) -> dict[str, Any] | None:
    load = _section(status, "load")
    if load is None:
        return None
    return {"scope": load.get("scope"), "cpu_count": _number(load.get("cpuCount"))}


def _has_swap(status: dict[str, Any]) -> bool:
    memory = _section(status, "memory")
    total = None if memory is None else _number(memory.get("swapTotalBytes"))
    return total is not None and total > 0


def _has_package_power(status: dict[str, Any]) -> bool:
    """Return True when the server has a CPU package power source.

    ``packageWatts`` is null on the first RAPL sample, so the source decides
    whether the sensor exists and a null reading shows as unknown.
    """
    power = _section(status, "power")
    return power is not None and (
        power.get("packageSource") is not None
        or _number(power.get("packageWatts")) is not None
    )


def _data_scope(status: dict[str, Any]) -> str | None:
    """Summarise the scopes of the memory, load and network sections.

    A scope this integration does not know (a future server value) makes the
    summary unknown instead of guessing; each entity's ``scope`` attribute
    still shows the raw value so nothing is hidden.
    """
    scopes = {
        section.get("scope")
        for name in SCOPED_SECTIONS
        if (section := _section(status, name)) is not None
    }
    if scopes == {SCOPE_HOST}:
        return SCOPE_HOST
    if scopes == {SCOPE_CONTAINER}:
        return SCOPE_CONTAINER
    return SCOPE_MIXED if {SCOPE_HOST, SCOPE_CONTAINER} <= scopes else None


def _data_scope_attrs(status: dict[str, Any]) -> dict[str, Any]:
    return {
        f"{name}_scope": section.get("scope")
        if (section := _section(status, name)) is not None
        else None
        for name in SCOPED_SECTIONS
    }


def _any_scoped_section(status: dict[str, Any]) -> bool:
    return any(_section(status, name) is not None for name in SCOPED_SECTIONS)


_HOST_SCOPE = {"scope": SCOPE_HOST}

METRIC_SENSORS: tuple[ChirpSensorDescription, ...] = (
    # Where memory/load/network values come from
    ChirpSensorDescription(
        key="data_scope",
        translation_key="data_scope",
        device_class=SensorDeviceClass.ENUM,
        options=DATA_SCOPES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_data_scope,
        exists_fn=_any_scoped_section,
        available_fn=_any_scoped_section,
        attrs_fn=_data_scope_attrs,
    ),
    # Memory used
    ChirpSensorDescription(
        key="memory_used_percent",
        translation_key="memory_used_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_section_value("memory", "usedPercent"),
        exists_fn=_has_section("memory"),
        available_fn=_has_section("memory"),
        attrs_fn=_scope_attrs("memory"),
    ),
    ChirpSensorDescription(
        key="memory_used",
        translation_key="memory_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=_section_value("memory", "usedBytes"),
        exists_fn=_has_section("memory"),
        available_fn=_has_section("memory"),
        attrs_fn=_scope_attrs("memory"),
    ),
    ChirpSensorDescription(
        key="memory_total",
        translation_key="memory_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_section_value("memory", "totalBytes"),
        exists_fn=_has_section("memory"),
        available_fn=_has_section("memory"),
        attrs_fn=_scope_attrs("memory"),
    ),
    ChirpSensorDescription(
        key="swap_used_percent",
        translation_key="swap_used_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_section_value("memory", "swapUsedPercent"),
        exists_fn=_has_swap,
        available_fn=_has_section("memory"),
        attrs_fn=_scope_attrs("memory"),
    ),
    # CPU usage and load averages
    ChirpSensorDescription(
        key="cpu_usage_percent",
        translation_key="cpu_usage_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_section_value("load", "cpuUsagePercent"),
        exists_fn=_has_section("load"),
        available_fn=_has_section("load"),
        attrs_fn=_load_attrs,
    ),
    ChirpSensorDescription(
        key="load_1m",
        translation_key="load_1m",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_section_value("load", "load1"),
        exists_fn=_has_section("load"),
        available_fn=_has_section("load"),
        attrs_fn=_load_attrs,
    ),
    ChirpSensorDescription(
        key="load_5m",
        translation_key="load_5m",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=_section_value("load", "load5"),
        exists_fn=_has_section("load"),
        available_fn=_has_section("load"),
        attrs_fn=_load_attrs,
    ),
    ChirpSensorDescription(
        key="load_15m",
        translation_key="load_15m",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=_section_value("load", "load15"),
        exists_fn=_has_section("load"),
        available_fn=_has_section("load"),
        attrs_fn=_load_attrs,
    ),
    # CPU package power
    ChirpSensorDescription(
        key="package_power",
        translation_key="package_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_section_value("power", "packageWatts"),
        exists_fn=_has_package_power,
        available_fn=_has_section("power"),
        attrs_fn=lambda status: {
            **_HOST_SCOPE,
            "source": (_section(status, "power") or {}).get("packageSource"),
        },
    ),
)


def _labels(items: list[dict[str, Any]]) -> dict[str, str]:
    """Return a display label per item ID; repeated labels get the chip name."""
    counts: dict[str, int] = {}
    for item in items:
        label = str(item.get("label") or item["id"])
        counts[label] = counts.get(label, 0) + 1
    result: dict[str, str] = {}
    for item in items:
        label = str(item.get("label") or item["id"])
        chip = item.get("chip")
        result[item["id"]] = f"{chip} {label}" if counts[label] > 1 and chip else label
    return result


@dataclass(frozen=True, kw_only=True)
class ChirpItemSensorDescription(SensorEntityDescription):
    """Describe a sensor for one item of a list (power source, fan, voltage)."""

    collection: str
    field: str
    item_id: str = ""
    # Labels that already contain one of these words use the bare label as the
    # name ("PPT power" is fine, "power1 power" is not).
    label_words: tuple[str, ...] = ()
    placeholders: dict[str, str] | None = None


def _fan_spinning(fan: dict[str, Any]) -> bool:
    """Enable a fan sensor by default only for a fan that was spinning.

    Monitoring chips list every fan header, so most boards report several
    ``0`` rpm headers with nothing connected to them. The decision is made
    when the entity is first registered; enabling it later is up to the user.
    """
    rpm = _number(fan.get("rpm"))
    return rpm is not None and rpm > 0


ITEM_SENSORS: tuple[
    tuple[ChirpItemSensorDescription, Callable[[dict[str, Any]], bool] | None], ...
] = (
    # Each power source (RAPL zone, hwmon power reading)
    (
        ChirpItemSensorDescription(
            key="power_source",
            translation_key="power_source",
            collection="power_sources",
            field="watts",
            label_words=("power", "watt"),
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            entity_registry_enabled_default=False,
        ),
        None,
    ),
    # Fan speed ("CPU Fan speed", "fan2 speed")
    (
        ChirpItemSensorDescription(
            key="fan",
            translation_key="fan",
            collection="fans",
            field="rpm",
            label_words=("speed",),
            native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        _fan_spinning,
    ),
    # Voltage rail
    (
        ChirpItemSensorDescription(
            key="voltage",
            translation_key="voltage",
            collection="voltages",
            field="volts",
            label_words=("volt",),
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=3,
            entity_registry_enabled_default=False,
        ),
        None,
    ),
)


def _item_descriptions(status: dict[str, Any]) -> list[ChirpItemSensorDescription]:
    """Build one sensor description per power source, fan and voltage."""
    descriptions: list[ChirpItemSensorDescription] = []
    for template, enabled_fn in ITEM_SENSORS:
        items = COLLECTIONS[template.collection](status)
        labels = _labels(items)
        for item in items:
            label = labels[item["id"]]
            plain = any(word in label.lower() for word in template.label_words)
            enabled = template.entity_registry_enabled_default
            if enabled_fn is not None:
                enabled = enabled_fn(item)
            descriptions.append(
                dataclasses.replace(
                    template,
                    key=f"{template.key}_{item['id']}",
                    translation_key="labeled_reading"
                    if plain
                    else template.translation_key,
                    item_id=item["id"],
                    entity_registry_enabled_default=enabled,
                    placeholders={"label": label},
                )
            )
    return descriptions


@dataclass(frozen=True, kw_only=True)
class ChirpInterfaceSensorDescription(SensorEntityDescription):
    """Describe a per-network-interface sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


def _interface_value(field: str) -> Callable[[dict[str, Any]], Any]:
    return lambda interface: _number(interface.get(field))


def _interface_counter(key: str, field: str) -> ChirpInterfaceSensorDescription:
    return ChirpInterfaceSensorDescription(
        key=key,
        translation_key=key,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_interface_value(field),
    )


def _interface_rate(key: str, field: str) -> ChirpInterfaceSensorDescription:
    # Shown in Mbit/s, the unit of the link speed, so both compare directly.
    return ChirpInterfaceSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_interface_value(field),
    )


def _interface_total(key: str, field: str) -> ChirpInterfaceSensorDescription:
    return ChirpInterfaceSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_interface_value(field),
    )


INTERFACE_SENSORS: tuple[ChirpInterfaceSensorDescription, ...] = (
    # Receive / transmit rate
    _interface_rate("rx_rate", "rxBytesPerSec"),
    _interface_rate("tx_rate", "txBytesPerSec"),
    # Bytes received / sent since the interface was created (kernel counters)
    _interface_total("rx_total", "rxBytes"),
    _interface_total("tx_total", "txBytes"),
    # Negotiated link speed
    ChirpInterfaceSensorDescription(
        key="speed",
        translation_key="link_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_interface_value("speedMbps"),
    ),
    # Error and drop counters
    _interface_counter("rx_errors", "rxErrors"),
    _interface_counter("tx_errors", "txErrors"),
    _interface_counter("rx_dropped", "rxDropped"),
    _interface_counter("tx_dropped", "txDropped"),
)


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
    icon: str | None = None,
) -> ChirpDiskSensorDescription:
    return ChirpDiskSensorDescription(
        key=key,
        translation_key=key,
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        value_fn=lambda disk: getter(disk, field),
        exists_fn=exists,
    )


DISK_SENSORS: tuple[ChirpDiskSensorDescription, ...] = (
    # Disk temperature
    ChirpDiskSensorDescription(
        key="temperature",
        translation_key="disk_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda disk: _number(disk.get("temperature")),
        attrs_fn=lambda disk: {"standby": bool(disk.get("standby"))},
    ),
    # Power-on hours
    ChirpDiskSensorDescription(
        key="power_on_hours",
        translation_key="power_on_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda disk: _number(disk.get("powerOnHours")),
    ),
    # Power cycle count
    ChirpDiskSensorDescription(
        key="power_cycle_count",
        translation_key="power_cycle_count",
        icon="mdi:power-cycle",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda disk: _number(disk.get("powerCycleCount")),
    ),
    # SMART health verdict
    ChirpDiskSensorDescription(
        key="health",
        translation_key="health",
        icon="mdi:heart-pulse",
        device_class=SensorDeviceClass.ENUM,
        options=HEALTH_STATES,
        value_fn=_health_status,
        attrs_fn=lambda disk: {"reasons": _health_reasons(disk)},
    ),
    # Reallocated sectors count
    _count_description(
        "reallocated_sectors",
        "reallocatedSectors",
        _ata,
        _has_ata,
        diagnostic=False,
        icon="mdi:database-alert",
    ),
    # Current pending sectors count
    _count_description(
        "pending_sectors",
        "pendingSectors",
        _ata,
        _has_ata,
        diagnostic=False,
        icon="mdi:database-clock",
    ),
    # Offline uncorrectable sectors count
    _count_description(
        "offline_uncorrectable",
        "offlineUncorrectable",
        _ata,
        _has_ata,
        diagnostic=True,
        icon="mdi:database-alert",
    ),
    # UDMA CRC error count
    _count_description(
        "udma_crc_errors",
        "udmaCrcErrors",
        _ata,
        _has_ata,
        diagnostic=True,
        icon="mdi:sync-alert",
    ),
    # SSD wear level percentage
    ChirpDiskSensorDescription(
        key="wear",
        translation_key="wear",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wear,
        exists_fn=_has_wear,
    ),
    # NVMe available spare capacity
    ChirpDiskSensorDescription(
        key="available_spare",
        translation_key="available_spare",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda disk: _nvme(disk, "availableSpare"),
        exists_fn=_has_nvme,
    ),
    # Total data written in TB
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
    # Media and integrity errors count
    _count_description(
        "media_errors",
        "mediaErrors",
        _nvme,
        _has_nvme,
        diagnostic=True,
        icon="mdi:database-alert",
    ),
    # Unsafe shutdowns count
    _count_description(
        "unsafe_shutdowns",
        "unsafeShutdowns",
        _nvme,
        _has_nvme,
        diagnostic=True,
        icon="mdi:power-off",
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
        for host_description in (
            *HOST_SENSORS,
            *_core_descriptions(status),
            *METRIC_SENSORS,
        ):
            unique_id = f"{instance_id}_{host_description.key}"
            if unique_id not in known and host_description.exists_fn(status):
                known.add(unique_id)
                new.append(ChirpHostSensor(coordinator, entry, host_description))
        for item_description in _item_descriptions(status):
            unique_id = f"{instance_id}_{item_description.key}"
            if unique_id not in known:
                known.add(unique_id)
                new.append(ChirpItemSensor(coordinator, entry, item_description))
        for disk in status["disks"]:
            if is_provisional_disk(disk):
                continue
            for disk_description in DISK_SENSORS:
                unique_id = disk_unique_id(
                    instance_id, disk["id"], disk_description.key
                )
                if unique_id not in known and disk_description.exists_fn(disk):
                    known.add(unique_id)
                    new.append(
                        ChirpDiskSensor(coordinator, entry, disk_description, disk)
                    )
        for interface in network_interfaces(status):
            for interface_description in INTERFACE_SENSORS:
                unique_id = interface_unique_id(
                    instance_id, interface["id"], interface_description.key
                )
                if unique_id not in known:
                    known.add(unique_id)
                    new.append(
                        ChirpInterfaceSensor(
                            coordinator, entry, interface_description, interface
                        )
                    )
        if new:
            async_add_entities(new)

    # Fetch errors are always present, independent of what the server reports.
    async_add_entities([ChirpFetchErrorSensor(coordinator, entry)])
    register_forget_device(
        entry,
        known,
        (description.key for description in DISK_SENSORS),
        (description.key for description in INTERFACE_SENSORS),
    )
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
    def available(self) -> bool:
        """Host metric sensors whose section is gone become unavailable."""
        available_fn = self.entity_description.available_fn
        return super().available and (available_fn is None or available_fn(self.status))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, such as the scope of host metrics."""
        attrs_fn = self.entity_description.attrs_fn
        return None if attrs_fn is None else attrs_fn(self.status)

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


# Consecutive failed polls count
class ChirpFetchErrorSensor(ChirpEntity, SensorEntity):
    """Number of consecutive failed polls; attributes describe the last error."""

    def __init__(self, coordinator: ChirpCoordinator, entry: ChirpConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            SensorEntityDescription(
                key="fetch_errors",
                translation_key="fetch_errors",
                icon="mdi:alert-circle-outline",
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
    def icon(self) -> str | None:
        """Return dynamic icon for disk health based on state."""
        if self.entity_description.key == "health":
            status = self.native_value
            if status == HEALTH_OK:
                return "mdi:check-circle-outline"
            if status == HEALTH_WARNING:
                return "mdi:alert-circle-outline"
            if status == HEALTH_FAILING:
                return "mdi:close-circle-outline"
            return "mdi:heart-pulse"
        return super().icon

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


class ChirpInterfaceSensor(ChirpInterfaceEntity, SensorEntity):
    """A sensor describing one network interface."""

    entity_description: ChirpInterfaceSensorDescription

    @property
    def native_value(self) -> Any:
        """Return the sensor value from the latest snapshot."""
        interface = self.interface
        return (
            None if interface is None else self.entity_description.value_fn(interface)
        )


class ChirpItemSensor(ChirpEntity, SensorEntity):
    """A host sensor for one power source, fan or voltage reading."""

    entity_description: ChirpItemSensorDescription

    def __init__(
        self,
        coordinator: ChirpCoordinator,
        entry: ChirpConfigEntry,
        description: ChirpItemSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description)
        self._attr_translation_placeholders = description.placeholders or {}

    @property
    def item(self) -> dict[str, Any] | None:
        """Return this reading's latest data, or None when it vanished."""
        description = self.entity_description
        return self.coordinator.get_item(description.collection, description.item_id)

    @property
    def available(self) -> bool:
        """Readings missing from the latest response become unavailable."""
        return super().available and self.item is not None

    @property
    def native_value(self) -> float | int | None:
        """Return the reading from the latest snapshot."""
        item = self.item
        return (
            None if item is None else _number(item.get(self.entity_description.field))
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the scope (always the host's sensors) and the chip."""
        item = self.item
        if item is None:
            return None
        chip = {"chip": item["chip"]} if item.get("chip") else {}
        return {**_HOST_SCOPE, **chip}
