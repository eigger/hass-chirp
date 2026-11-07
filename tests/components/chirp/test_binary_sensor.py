"""Problem binary sensors derived from the server's health verdicts."""

from .conftest import HDD_ID, INSTANCE_ID, NVME_ID, STATUS_URL, load_status

HDD = f"{INSTANCE_ID}_{HDD_ID}"
NVME = f"{INSTANCE_ID}_{NVME_ID}"


async def test_baseline_problem_sensors(hass, setup_entry, entity_id):
    warn = hass.states.get(entity_id(f"{HDD}_smart_problem", "binary_sensor"))
    assert warn.state == "on"
    assert warn.attributes["device_class"] == "problem"
    assert warn.attributes["reasons"] == [{"code": "reallocated_sectors", "value": 8}]
    assert warn.attributes["smart_passed"] is True
    ok = hass.states.get(entity_id(f"{NVME}_smart_problem", "binary_sensor"))
    assert ok.state == "off"
    assert ok.attributes["reasons"] == []


async def test_host_has_no_aggregate_disk_problem_sensor(
    hass, entry, aioclient_mock, entity_id
):
    """The host's old "Any disk problem" duplicated each disk's SMART problem."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "binary_sensor",
        "chirp",
        f"{INSTANCE_ID}_any_disk_problem",
        config_entry=entry,
    )
    aioclient_mock.get(STATUS_URL, json=load_status())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(stale.entity_id) is None
    assert hass.states.get(stale.entity_id) is None


async def test_last_read_timestamp_sensor_is_retired(hass, entry, aioclient_mock):
    """The per-disk timestamp sensor logged every SMART cycle; it is an attribute now."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "sensor", "chirp", f"{HDD}_last_read_at", config_entry=entry
    )
    kept = registry.async_get_or_create(
        "sensor", "chirp", f"{HDD}_temperature", config_entry=entry
    )
    aioclient_mock.get(STATUS_URL, json=load_status())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(stale.entity_id) is None
    assert registry.async_get(kept.entity_id) is not None


async def test_failing_nvme(hass, entry, aioclient_mock, entity_id):
    aioclient_mock.get(STATUS_URL, json=load_status("status_nvme_failing.json"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    problem = hass.states.get(entity_id(f"{NVME}_smart_problem", "binary_sensor"))
    assert problem.state == "on"
    assert problem.attributes["smart_passed"] is False
    assert len(problem.attributes["reasons"]) == 3


async def test_problem_clears_when_disk_ok(hass, setup_entry, api_response, entity_id):
    payload = load_status()
    payload["disks"][0]["health"] = {"status": "ok", "reasons": []}
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=payload)
    await setup_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(f"{HDD}_smart_problem", "binary_sensor")).state
        == "off"
    )


async def test_unknown_health_is_not_reported_as_problem(
    hass, setup_entry, api_response, entity_id
):
    payload = load_status()
    payload["disks"][0]["health"] = {
        "status": "unknown",
        "reasons": [{"code": "not_read"}],
    }
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=payload)
    await setup_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    smart = hass.states.get(entity_id(f"{HDD}_smart_problem", "binary_sensor"))
    assert smart.state == "unknown"
    health = hass.states.get(entity_id(f"{HDD}_health"))
    assert health.state == "unknown"
    assert health.attributes["reasons"] == [{"code": "not_read", "value": None}]


async def test_new_disk_gets_problem_sensor_and_missing_is_unavailable(
    hass, setup_entry, api_response, entity_id
):
    new_id = f"{INSTANCE_ID}_wwn_5002538e00112233_smart_problem"
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=load_status("status_new_disk.json"))
    coordinator = setup_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(new_id, "binary_sensor")).state == "off"

    api_response.clear_requests()
    api_response.get(STATUS_URL, json=load_status("status_disk_removed.json"))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(new_id, "binary_sensor")).state == "unavailable"
    assert (
        hass.states.get(entity_id(f"{HDD}_smart_problem", "binary_sensor")).state
        == "unavailable"
    )
