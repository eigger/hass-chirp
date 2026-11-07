"""Sensors: per-protocol creation, values, units, standby and dynamic disks."""

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.helpers import entity_registry as er

from .conftest import HDD_ID, INSTANCE_ID, NVME_ID, STATUS_URL, load_status

HDD = f"{INSTANCE_ID}_{HDD_ID}"
NVME = f"{INSTANCE_ID}_{NVME_ID}"


async def test_host_sensors(hass, setup_entry, entity_id, registered):
    state = hass.states.get(entity_id(f"{INSTANCE_ID}_cpu_temperature"))
    assert state.state == "47.0"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"

    boot = hass.states.get(entity_id(f"{INSTANCE_ID}_boot_time"))
    expected = datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC) - timedelta(seconds=123456)
    assert datetime.fromisoformat(boot.state) == expected
    assert registered(f"{INSTANCE_ID}_boot_time").entity_category.value == "diagnostic"

    errors = hass.states.get(entity_id(f"{INSTANCE_ID}_fetch_errors"))
    assert errors.state == "0"
    assert errors.attributes["icon"] == "mdi:alert-circle-outline"
    assert (
        registered(f"{INSTANCE_ID}_fetch_errors").entity_category.value == "diagnostic"
    )


async def test_disabled_by_default_temperatures(hass, setup_entry, registered):
    for key in (
        "cpu_max_temperature",
        "cpu_core_temperature_core_0",
        "cpu_core_temperature_core_1",
    ):
        reg = registered(f"{INSTANCE_ID}_{key}")
        assert reg is not None, key
        assert reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(reg.entity_id) is None
    assert registered(f"{INSTANCE_ID}_cpu_core_temperature_core_2") is None
    assert registered(f"{INSTANCE_ID}_cpu_core_temperature_core_1").translation_key == (
        "cpu_core_temperature"
    )


async def test_ata_hdd_sensors(hass, setup_entry, entity_id, registered):
    def state(key):
        return hass.states.get(entity_id(f"{HDD}_{key}"))

    temp = state("temperature")
    assert temp.state == "34"
    assert temp.attributes["standby"] is False
    assert temp.attributes["unit_of_measurement"] == "°C"
    hours = state("power_on_hours")
    assert hours.state == "23456"
    assert hours.attributes["unit_of_measurement"] == "h"
    assert hours.attributes["device_class"] == "duration"
    assert hours.attributes["state_class"] == "total_increasing"
    assert state("power_cycle_count").state == "120"
    assert state("power_cycle_count").attributes["icon"] == "mdi:power-cycle"
    health = state("health")
    assert health.state == "warning"
    assert health.attributes["icon"] == "mdi:alert-circle-outline"
    assert health.attributes["reasons"] == [{"code": "reallocated_sectors", "value": 8}]
    assert health.attributes["options"] == ["ok", "warning", "failing"]
    assert state("reallocated_sectors").state == "8"
    assert state("reallocated_sectors").attributes["icon"] == "mdi:database-alert"
    assert state("pending_sectors").state == "0"
    assert state("pending_sectors").attributes["icon"] == "mdi:database-clock"
    assert state("offline_uncorrectable").state == "0"
    assert state("offline_uncorrectable").attributes["icon"] == "mdi:database-alert"
    assert state("udma_crc_errors").state == "0"
    assert state("udma_crc_errors").attributes["icon"] == "mdi:sync-alert"
    # Enabled by default, others diagnostic.
    assert registered(f"{HDD}_reallocated_sectors").entity_category is None
    assert registered(f"{HDD}_pending_sectors").entity_category is None
    for key in ("offline_uncorrectable", "udma_crc_errors", "power_cycle_count"):
        assert registered(f"{HDD}_{key}").entity_category.value == "diagnostic"
    # NVMe/SSD-only sensors are not created for a hard disk.
    for key in ("wear", "available_spare", "data_written", "media_errors"):
        assert registered(f"{HDD}_{key}") is None
    # Temperatures the disk records itself: diagnostic, in °C.
    for key, value in (
        ("temperature_lifetime_min", "18"),
        ("temperature_lifetime_max", "52"),
        ("temperature_power_cycle_min", "29"),
        ("temperature_power_cycle_max", "38"),
        ("temperature_operating_max", "60"),
    ):
        assert state(key).state == value, key
        assert state(key).attributes["unit_of_measurement"] == "°C"
        assert state(key).attributes["device_class"] == "temperature"
        assert registered(f"{HDD}_{key}").entity_category.value == "diagnostic"


async def test_nvme_sensors(hass, setup_entry, entity_id, registered):
    def state(key):
        return hass.states.get(entity_id(f"{NVME}_{key}"))

    assert state("temperature").state == "42"
    assert state("health").state == "ok"
    assert state("health").attributes["icon"] == "mdi:check-circle-outline"
    assert state("health").attributes["reasons"] == []
    assert state("wear").state == "3"
    assert state("wear").attributes["icon"] == "mdi:gauge"
    assert state("wear").attributes["unit_of_measurement"] == "%"
    assert state("available_spare").state == "100"
    assert state("available_spare").attributes["icon"] == "mdi:gauge"
    written = state("data_written")
    assert float(written.state) == pytest.approx(63.209875968)
    assert written.attributes["unit_of_measurement"] == "TB"
    assert written.attributes["device_class"] == "data_size"
    assert state("media_errors").state == "0"
    assert state("media_errors").attributes["icon"] == "mdi:database-alert"
    assert state("unsafe_shutdowns").state == "12"
    assert state("unsafe_shutdowns").attributes["icon"] == "mdi:power-off"
    for key in ("media_errors", "unsafe_shutdowns"):
        assert registered(f"{NVME}_{key}").entity_category.value == "diagnostic"
    for key in ("reallocated_sectors", "pending_sectors", "udma_crc_errors"):
        assert registered(f"{NVME}_{key}") is None
    # NVMe reports only its warning threshold; the other stats are not created.
    assert state("temperature_operating_max").state == "84"
    for key in ("temperature_lifetime_min", "temperature_lifetime_max"):
        assert registered(f"{NVME}_{key}") is None


async def test_data_written_falls_back_to_data_units(
    hass, entry, aioclient_mock, entity_id, status_payload
):
    status_payload["disks"][1]["nvme"]["bytesWritten"] = None
    aioclient_mock.get(STATUS_URL, json=status_payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    written = hass.states.get(entity_id(f"{NVME}_data_written"))
    assert float(written.state) == pytest.approx(123456789 * 512000 / 1e12)


async def test_devices(hass, setup_entry, device_for):
    entry = setup_entry
    host = device_for(entry, INSTANCE_ID)
    assert host.name == "pve"
    assert host.manufacturer == "Chirp (self-hosted)"
    assert host.model == "Intel(R) Core(TM) i5-12500"
    assert host.sw_version == "0.1.0"
    assert host.configuration_url == "http://chirp.test"

    hdd = device_for(entry, HDD)
    assert hdd.name == "ST4000VN008-2DR166 (ABCD)"
    assert hdd.via_device_id == host.id
    assert hdd.serial_number == "ZDH1ABCD"
    assert hdd.sw_version == "SC60"
    assert hdd.model == "ST4000VN008-2DR166"
    nvme = device_for(entry, NVME)
    assert nvme.name == "Samsung SSD 980 PRO 1TB (456A)"
    assert nvme.via_device_id == host.id


async def test_standby_keeps_last_temperature(hass, entry, aioclient_mock, entity_id):
    aioclient_mock.get(STATUS_URL, json=load_status("status_standby.json"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    temp = hass.states.get(entity_id(f"{HDD}_temperature"))
    assert temp.state == "33"
    assert temp.attributes["standby"] is True


async def test_nvme_failing_fixture(hass, entry, aioclient_mock, entity_id):
    aioclient_mock.get(STATUS_URL, json=load_status("status_nvme_failing.json"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    health = hass.states.get(entity_id(f"{NVME}_health"))
    assert health.state == "failing"
    assert health.attributes["icon"] == "mdi:close-circle-outline"
    assert [r["code"] for r in health.attributes["reasons"]] == [
        "smart_failed",
        "nvme_critical_warning",
        "spare_below_threshold",
    ]
    assert hass.states.get(entity_id(f"{NVME}_available_spare")).state == "5"
    assert hass.states.get(entity_id(f"{NVME}_media_errors")).state == "3"
    assert hass.states.get(entity_id(f"{NVME}_wear")).state == "97"


async def test_new_disk_is_added_dynamically(
    hass, setup_entry, api_response, entity_id, registered, device_for
):
    new_id = f"{INSTANCE_ID}_wwn_5002538e00112233"
    assert registered(f"{new_id}_temperature") is None
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=load_status("status_new_disk.json"))
    await setup_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(f"{new_id}_temperature")).state == "31"
    # SATA SSD: wear from ata, but no NVMe-only sensors.
    assert hass.states.get(entity_id(f"{new_id}_wear")).state == "12"
    assert registered(f"{new_id}_available_spare") is None
    # SATA SSD with Device Statistics: data written and SCT temperatures.
    written = hass.states.get(entity_id(f"{new_id}_data_written"))
    assert float(written.state) == pytest.approx(1.49457662208)
    assert (
        hass.states.get(entity_id(f"{new_id}_temperature_lifetime_max")).state == "75"
    )
    assert (
        hass.states.get(entity_id(f"{new_id}_temperature_operating_max")).state == "100"
    )
    assert registered(f"{new_id}_temperature_lifetime_min") is None
    assert hass.states.get(entity_id(f"{new_id}_reallocated_sectors")).state == "0"
    device = device_for(setup_entry, new_id)
    assert device.name == "Samsung SSD 870 EVO 1TB (654Z)"
    assert device.via_device_id is not None


async def test_missing_disk_becomes_unavailable_and_returns(
    hass, setup_entry, api_response, entity_id
):
    coordinator = setup_entry.runtime_data.coordinator
    temp = entity_id(f"{HDD}_temperature")
    health = entity_id(f"{HDD}_health")
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=load_status("status_disk_removed.json"))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(temp).state == "unavailable"
    assert hass.states.get(health).state == "unavailable"
    # The other disk and the host keep working.
    assert hass.states.get(entity_id(f"{NVME}_temperature")).state == "42"
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_cpu_temperature")).state == "47.0"

    api_response.clear_requests()
    api_response.get(STATUS_URL, json=load_status())
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(temp).state == "34"


async def test_boot_time_is_stable_across_jitter(
    hass, setup_entry, api_response, entity_id
):
    boot = entity_id(f"{INSTANCE_ID}_boot_time")
    first = hass.states.get(boot).state
    payload = load_status()
    payload["instance"]["uptimeSeconds"] += 61
    payload["instance"]["collectedAt"] = "2026-11-03T10:01:02Z"  # +62 s, 1 s jitter
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=payload)
    await setup_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(boot).state == first


async def test_sensor_without_cpu_data_skips_cpu_entities(
    hass, entry, aioclient_mock, registered
):
    payload = load_status()
    payload["cpu"].update(packageTemp=None, maxTemp=None, cores=[], source=None)
    payload["instance"]["uptimeSeconds"] = None
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for key in ("cpu_temperature", "cpu_max_temperature", "boot_time"):
        assert registered(f"{INSTANCE_ID}_{key}") is None
    assert registered(f"{INSTANCE_ID}_fetch_errors") is not None


async def test_placeholder_disk_id_waits_for_the_real_id(
    hass, setup_entry, api_response, registered, device_for, status_payload
):
    """``dev_<name>`` before the first read is replaced by the real ID later."""
    entry = setup_entry
    placeholder = {
        **status_payload["disks"][0],
        "id": "dev_sdc",
        "name": "sdc",
        "model": None,
        "serial": None,
        "standby": True,
        "temperature": None,
        "ata": None,
        "lastReadAt": None,
        "health": {"status": "unknown", "reasons": [{"code": "not_read"}]},
    }
    payload = load_status()
    payload["disks"].append(placeholder)
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=payload)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_dev_sdc_temperature") is None
    assert registered(f"{INSTANCE_ID}_dev_sdc_smart_problem", "binary_sensor") is None
    assert device_for(entry, f"{INSTANCE_ID}_dev_sdc") is None

    # Once read, the disk reports its permanent ID and gets its entities.
    real = {
        **placeholder,
        "id": "wwn_5000c500deadbeef",
        "model": "WD40EFRX",
        "serial": "WD-1234",
        "standby": False,
        "temperature": 31,
        "lastReadAt": "2026-11-03T10:00:00.000Z",
    }
    payload["disks"][-1] = real
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=payload)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_wwn_5000c500deadbeef_temperature") is not None
    assert device_for(entry, f"{INSTANCE_ID}_dev_sdc") is None


async def test_permanent_dev_id_is_used_after_a_read(
    hass, entry, aioclient_mock, registered, status_payload
):
    """A disk without WWN, model or serial keeps ``dev_<name>`` once read."""
    status_payload["disks"][0]["id"] = "dev_sda"
    aioclient_mock.get(STATUS_URL, json=status_payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_dev_sda_temperature") is not None


async def test_core_sensors_follow_labels_not_positions(
    hass, entry, aioclient_mock, registered
):
    """Cores are keyed by label, so a reordered list keeps each value in place."""
    payload = load_status()
    payload["cpu"]["cores"] = [
        {"label": "Core 0", "temp": 40.0},
        {"label": "Core 0", "temp": 41.0},  # second socket reuses the label
        {"label": "", "temp": 42.0},
    ]
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    keys = ("core_0", "core_0_2", "index_2")
    for key in keys:
        reg = registered(f"{INSTANCE_ID}_cpu_core_temperature_{key}")
        assert reg is not None, key
        registry.async_update_entity(reg.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    def value(key):
        reg = registered(f"{INSTANCE_ID}_cpu_core_temperature_{key}")
        return hass.states.get(reg.entity_id).state

    assert [value(key) for key in keys] == ["40.0", "41.0", "42.0"]

    reordered = load_status()
    reordered["cpu"]["cores"] = [
        {"label": "", "temp": 50.0},
        {"label": "Core 1", "temp": 52.0},
        {"label": "Core 0", "temp": 51.0},
    ]
    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=reordered)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert value("core_0") == "51.0"
    assert value("core_0_2") == "unknown"
    assert value("index_2") == "unknown"
    assert registered(f"{INSTANCE_ID}_cpu_core_temperature_index_0") is not None
    assert registered(f"{INSTANCE_ID}_cpu_core_temperature_core_1") is not None


async def test_server_unknown_health_is_ha_unknown_state(
    hass, setup_entry, api_response, entity_id
):
    payload = load_status()
    payload["disks"][0]["health"] = {"status": "unknown", "reasons": []}
    payload["disks"][1]["health"] = {"status": "bogus", "reasons": []}
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=payload)
    await setup_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    for disk in (HDD, NVME):
        health = hass.states.get(entity_id(f"{disk}_health"))
        assert health.state == "unknown"
        assert "unknown" not in health.attributes["options"]


@pytest.mark.parametrize(
    ("language", "expected", "healthy"),
    [
        ("en", "High temperature (70 °C)", "No issues"),
        ("ko", "온도 높음 (70 °C)", "문제 없음"),
        ("fr", "High temperature (70 °C)", "No issues"),
    ],
)
async def test_health_reason_state_changes_and_recovers(
    hass, entry, aioclient_mock, entity_id, language, expected, healthy
):
    """Reason changes must change state even while the verdict stays warning."""
    hass.config.language = language
    payload = load_status()
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reason_id = entity_id(f"{HDD}_health_reason")
    before = hass.states.get(reason_id).state

    async def refresh(health):
        payload["disks"][0]["health"] = health
        aioclient_mock.clear_requests()
        aioclient_mock.get(STATUS_URL, json=payload)
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()
        return hass.states.get(reason_id)

    reasons = [{"code": "temperature_high", "value": 70}]
    state = await refresh({"status": "warning", "reasons": reasons})
    assert state.state == expected
    assert state.state != before
    assert state.attributes["reasons"] == reasons
    assert hass.states.get(entity_id(f"{HDD}_health")).state == "warning"
    state = await refresh({"status": "ok", "reasons": []})
    assert state.state == healthy
    assert state.attributes["reasons"] == []
    state = await refresh({"status": "unknown", "reasons": []})
    assert state.state == "unknown"
    state = await refresh({"status": "unknown", "reasons": [{"code": "not_read"}]})
    assert state.state == ("아직 읽지 못함" if language == "ko" else "Not read")


async def test_health_reason_multiple_unknown_codes_and_state_limit(
    hass, setup_entry, api_response, entity_id
):
    payload = load_status()
    reasons = [
        {"code": "smart_failed"},
        {"code": "spare_below_threshold", "value": 0},
        {"code": "wear_high", "value": 97},
        {"code": "future_reason", "value": 12},
    ]

    async def refresh():
        payload["disks"][0]["health"] = {"status": "failing", "reasons": reasons}
        api_response.clear_requests()
        api_response.get(STATUS_URL, json=payload)
        await setup_entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()
        return hass.states.get(entity_id(f"{HDD}_health_reason"))

    state = await refresh()
    assert state.state == (
        "SMART check failed; Available spare below threshold (0 %); "
        "High wear (97 %); future_reason (12)"
    )
    reasons.append({"code": "long_reason_" + "x" * 300})
    state = await refresh()
    assert len(state.state) == 255
    assert state.state.endswith("...")
    assert len(state.attributes["reasons"][-1]["code"]) > 255


@pytest.mark.parametrize("status", ["warning", "failing"])
async def test_health_reason_missing_details_is_not_healthy(
    hass, entry, aioclient_mock, entity_id, status
):
    payload = load_status()
    payload["disks"][0]["health"] = {"status": status, "reasons": []}
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id(f"{HDD}_health_reason"))
    assert state.state == f"{status.capitalize()} (reason not reported)"
