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
    anyp = hass.states.get(
        entity_id(f"{INSTANCE_ID}_any_disk_problem", "binary_sensor")
    )
    assert anyp.state == "on"
    assert anyp.attributes["device_class"] == "problem"


async def test_failing_nvme(hass, entry, aioclient_mock, entity_id):
    aioclient_mock.get(STATUS_URL, json=load_status("status_nvme_failing.json"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    problem = hass.states.get(entity_id(f"{NVME}_smart_problem", "binary_sensor"))
    assert problem.state == "on"
    assert problem.attributes["smart_passed"] is False
    assert len(problem.attributes["reasons"]) == 3


async def test_any_problem_clears_when_all_disks_ok(
    hass, setup_entry, api_response, entity_id
):
    payload = load_status()
    payload["disks"][0]["health"] = {"status": "ok", "reasons": []}
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=payload)
    await setup_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    anyp = entity_id(f"{INSTANCE_ID}_any_disk_problem", "binary_sensor")
    assert hass.states.get(anyp).state == "off"
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
    anyp = entity_id(f"{INSTANCE_ID}_any_disk_problem", "binary_sensor")
    assert hass.states.get(anyp).state == "off"


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
