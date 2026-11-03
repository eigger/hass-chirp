"""Keep the last good snapshot on failure and recover through real HA updates."""

import logging

from homeassistant.config_entries import ConfigEntryState

from custom_components.chirp.coordinator import scan_interval_from_options

from .conftest import INSTANCE_ID, STATUS_URL, load_status

OTHER_INSTANCE = "00000000-0000-4000-8000-000000000000"


async def test_failures_preserve_state_and_recover(
    hass, setup_entry, api_response, entity_id, status_payload, caplog
):
    coordinator = setup_entry.runtime_data.coordinator
    last_good = coordinator.data
    temp = entity_id(f"{INSTANCE_ID}_cpu_temperature")
    assert hass.states.get(temp).state == "47.0"
    for failures in (1, 2):
        api_response.clear_requests()
        api_response.get(STATUS_URL, status=500)
        with caplog.at_level(logging.WARNING):
            await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.data is last_good
        assert coordinator.consecutive_errors == failures
        assert coordinator.last_error.startswith("ChirpConnectionError:")
        assert coordinator.last_error_at is not None
        assert hass.states.get(temp).state == "47.0"
        errors = hass.states.get(entity_id(f"{INSTANCE_ID}_fetch_errors"))
        assert errors.state == str(failures)
        assert errors.attributes["last_error"].startswith("ChirpConnectionError")
        assert "chirp.test" not in errors.attributes["last_error"]
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=status_payload)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.consecutive_errors == 0
    assert coordinator.last_success_at is not None
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_fetch_errors")).state == "0"
    assert (
        sum(
            r.levelname == "WARNING" and "Chirp update failed" in r.message
            for r in caplog.records
        )
        == 1
    )


async def test_runtime_auth_failure_starts_only_one_reauth(
    hass, setup_entry, api_response
):
    coordinator = setup_entry.runtime_data.coordinator
    last_good = coordinator.data
    api_response.clear_requests()
    api_response.get(STATUS_URL, status=401)
    for _ in range(2):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert coordinator.data is last_good
    assert coordinator.consecutive_errors == 2
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert setup_entry.state is ConfigEntryState.LOADED


async def test_reauth_can_start_again_after_recovery(
    hass, setup_entry, api_response, status_payload
):
    coordinator = setup_entry.runtime_data.coordinator
    api_response.clear_requests()
    api_response.get(STATUS_URL, status=401)
    await coordinator.async_refresh()
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=status_payload)
    await coordinator.async_refresh()
    assert coordinator._reauth_started is False


def test_scan_interval_defaults_and_clamps():
    assert scan_interval_from_options({}).total_seconds() == 60
    assert scan_interval_from_options({"scan_interval": 45}).total_seconds() == 45
    assert scan_interval_from_options({"scan_interval": 1}).total_seconds() == 30
    assert scan_interval_from_options({"scan_interval": 99999}).total_seconds() == 3600
    assert scan_interval_from_options({"scan_interval": "x"}).total_seconds() == 60


async def test_options_scan_interval_used(hass, entry, api_response):
    hass.config_entries.async_update_entry(entry, options={"scan_interval": 300})
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.coordinator.update_interval.total_seconds() == 300


async def test_different_instance_is_rejected_and_keeps_entities(
    hass, setup_entry, api_response, entity_id, registered, status_payload
):
    """A new server at the same address must not create entities in this entry."""
    coordinator = setup_entry.runtime_data.coordinator
    last_good = coordinator.data
    other = load_status()
    other["instance"]["id"] = OTHER_INSTANCE
    api_response.clear_requests()
    api_response.get(STATUS_URL, json=other)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data is last_good
    assert coordinator.consecutive_errors == 1
    assert coordinator.last_error.startswith("ChirpInstanceMismatchError:")
    assert registered(f"{OTHER_INSTANCE}_cpu_temperature") is None
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_cpu_temperature")).state == "47.0"
    assert not hass.config_entries.flow.async_progress()

    api_response.clear_requests()
    api_response.get(STATUS_URL, json=status_payload)
    await coordinator.async_refresh()
    assert coordinator.consecutive_errors == 0


async def test_different_instance_at_setup_retries(hass, entry, aioclient_mock):
    other = load_status()
    other["instance"]["id"] = OTHER_INSTANCE
    aioclient_mock.get(STATUS_URL, json=other)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
