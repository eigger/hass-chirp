"""Exercise actual config entry setup, reload, cleanup and retry."""

from homeassistant.config_entries import ConfigEntryState

from custom_components.chirp import async_remove_config_entry_device

from .conftest import HDD_ID, INSTANCE_ID, NVME_ID, STATUS_URL, load_status


async def test_setup_reload_and_unload(hass, setup_entry, entity_id):
    entry = setup_entry
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data.coordinator
    temp = entity_id(f"{INSTANCE_ID}_cpu_temperature")
    assert hass.states.get(temp).state == "47.0"
    assert coordinator._listeners
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator is not coordinator
    assert not coordinator._listeners
    current = entry.runtime_data.coordinator
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not current._listeners
    assert current._unsub_refresh is None
    assert hass.states.get(temp).state == "unavailable"


async def test_connection_failure_then_retry(
    hass, entry, aioclient_mock, status_payload
):
    aioclient_mock.get(STATUS_URL, status=500)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=status_payload)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_initial_auth_failure_starts_reauth(hass, entry, aioclient_mock):
    aioclient_mock.get(STATUS_URL, status=401)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"].get("source") == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_remove_config_entry_device(hass, setup_entry, api_response, device_for):
    entry = setup_entry
    host = device_for(entry, INSTANCE_ID)
    hdd = device_for(entry, f"{INSTANCE_ID}_{HDD_ID}")
    assert host is not None and hdd is not None
    # Present disks and the host cannot be removed.
    assert not await async_remove_config_entry_device(hass, entry, host)
    assert not await async_remove_config_entry_device(hass, entry, hdd)

    api_response.clear_requests()
    api_response.get(STATUS_URL, json=load_status("status_disk_removed.json"))
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert await async_remove_config_entry_device(hass, entry, hdd)
    nvme = device_for(entry, f"{INSTANCE_ID}_{NVME_ID}")
    assert not await async_remove_config_entry_device(hass, entry, nvme)
