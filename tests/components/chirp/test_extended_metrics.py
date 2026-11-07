"""Optional API fields, storage lifecycle and SMART diagnostic semantics."""

from homeassistant.helpers import entity_registry as er

from .conftest import HDD_ID, INSTANCE_ID, STATUS_URL, load_status


async def _refresh(hass, entry, aioclient_mock, payload):
    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=payload)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_existing_api_memory_and_smart_values(
    hass, setup_entry, entity_id, aioclient_mock
):
    entry = setup_entry
    memory = hass.states.get(entity_id(f"{INSTANCE_ID}_memory_available"))
    assert float(memory.state) == 41875931136 / 1024**3
    assert memory.attributes["scope"] == "host"
    problem_id = entity_id(f"{INSTANCE_ID}_{HDD_ID}_read_problem", "binary_sensor")

    def last_read():
        return hass.states.get(problem_id).attributes["last_read_at"]

    assert last_read() == "2026-11-03T09:58:00Z"
    assert hass.states.get(problem_id).state == "off"
    payload = load_status()
    payload["disks"][0]["standby"] = True
    await _refresh(hass, entry, aioclient_mock, payload)
    assert hass.states.get(problem_id).state == "off"
    payload["disks"][0]["error"] = "timeout"
    await _refresh(hass, entry, aioclient_mock, payload)
    assert hass.states.get(problem_id).state == "on"
    # A failed attempt must not masquerade as a successful read.
    assert last_read() == "2026-11-03T09:58:00Z"
    payload["disks"][0]["error"] = None
    payload["disks"][0]["lastReadAt"] = None
    await _refresh(hass, entry, aioclient_mock, payload)
    assert hass.states.get(problem_id).state == "unknown"
    assert last_read() is None


async def test_optional_storage_appears_disappears_and_recovers(
    hass, entry, aioclient_mock, registered
):
    aioclient_mock.get(STATUS_URL, json=load_status("status_legacy.json"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_filesystem_fs_root_used_percent") is None
    payload = load_status()
    await _refresh(hass, entry, aioclient_mock, payload)
    fs = registered(f"{INSTANCE_ID}_filesystem_fs_root_used_percent")
    zfs = registered(f"{INSTANCE_ID}_zfs_pool_1234567890123456789_health")
    wait = registered(f"{INSTANCE_ID}_io_wait_percent")
    assert hass.states.get(fs.entity_id).state == "60"
    assert hass.states.get(zfs.entity_id).state == "ONLINE"
    assert hass.states.get(wait.entity_id).state == "1.2"
    payload["filesystems"][0]["usedPercent"] = None
    payload["zfsPools"][0]["name"] = "renamed"
    payload["zfsPools"][0]["health"] = "DEGRADED"
    await _refresh(hass, entry, aioclient_mock, payload)
    assert hass.states.get(fs.entity_id).state == "unknown"
    assert hass.states.get(zfs.entity_id).state == "DEGRADED"
    assert hass.states.get(zfs.entity_id).attributes["name"] == "renamed"
    payload["filesystems"] = None
    payload["zfsPools"] = []
    del payload["load"]["ioWaitPercent"]
    await _refresh(hass, entry, aioclient_mock, payload)
    assert all(
        hass.states.get(reg.entity_id).state == "unavailable" for reg in (fs, zfs, wait)
    )
    await _refresh(hass, entry, aioclient_mock, load_status())
    assert hass.states.get(fs.entity_id).state == "60"
    assert registered(zfs.unique_id).entity_id == zfs.entity_id


async def test_temperature_uses_server_id_not_position(
    hass, setup_entry, aioclient_mock, registered
):
    entry = setup_entry
    registry = er.async_get(hass)
    reg = registered(f"{INSTANCE_ID}_hardware_temperature_temp_0011223344556677")
    assert reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    registry.async_update_entity(reg.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    payload = load_status()
    payload["sensors"].insert(
        0, {"id": "another", "chip": "jc42", "label": "DIMM", "temp": 55}
    )
    payload["sensors"][1]["temp"] = 45
    await _refresh(hass, entry, aioclient_mock, payload)
    assert hass.states.get(reg.entity_id).state == "45"
    payload["sensors"] = []
    await _refresh(hass, entry, aioclient_mock, payload)
    assert hass.states.get(reg.entity_id).state == "unavailable"
