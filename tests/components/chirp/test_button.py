"""The refresh button queues a SMART read and follows it with delayed polls."""

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.chirp import coordinator as coordinator_module

from .conftest import HDD_ID, INSTANCE_ID, REFRESH_URL, STATUS_URL, load_status


@pytest.fixture(autouse=True)
def fast_follow(monkeypatch):
    """Follow a queued refresh without the real delay between polls."""
    monkeypatch.setattr(coordinator_module, "REFRESH_POLL_INTERVAL", 0)


def _read_at(stamp):
    payload = load_status()
    for disk in payload["disks"]:
        disk["lastReadAt"] = stamp
    return payload


def _sequence(*payloads):
    """Answer successive status polls with the given payloads (last repeats)."""
    remaining = list(payloads)

    async def respond(method, url, data):
        payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return AiohttpClientMockResponse(method, url, json=payload)

    return respond


async def _press(hass, entity_id):
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


def _posts(aioclient_mock):
    return [call for call in aioclient_mock.mock_calls if call[0] == "post"]


def _gets(aioclient_mock):
    return [call for call in aioclient_mock.mock_calls if call[0] == "get"]


async def test_press_posts_refresh_and_follows_until_read_settles(
    hass, setup_entry, api_response, entity_id
):
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    assert hass.states.get(button).attributes["icon"] == "mdi:database-refresh"
    coordinator = setup_entry.runtime_data.coordinator
    stale = load_status()
    fresh = _read_at("2026-11-03T10:05:00Z")
    fresh["disks"][0]["ata"]["reallocatedSectors"] = 9
    api_response.clear_requests()
    api_response.post(REFRESH_URL, status=202, json={"queued": True})
    # The first poll still sees the old read, the second the new one, and the
    # third confirms nothing else changed, which ends the follow-up.
    api_response.get(STATUS_URL, side_effect=_sequence(stale, fresh))
    await _press(hass, button)
    posts = _posts(api_response)
    assert len(posts) == 1
    assert str(posts[0][1]) == REFRESH_URL
    assert posts[0][3]["Authorization"].startswith("Bearer chp_test_key")
    await coordinator._follow_task
    await hass.async_block_till_done()
    assert len(_gets(api_response)) == 3
    sectors = hass.states.get(entity_id(f"{INSTANCE_ID}_{HDD_ID}_reallocated_sectors"))
    assert sectors.state == "9"


async def test_follow_stops_at_the_attempt_limit(
    hass, setup_entry, api_response, entity_id
):
    """A read that never lands (all disks in standby) polls a bounded number."""
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    assert hass.states.get(button).attributes["icon"] == "mdi:database-refresh"
    coordinator = setup_entry.runtime_data.coordinator
    api_response.clear_requests()
    api_response.post(REFRESH_URL, status=202, json={"queued": True})
    api_response.get(STATUS_URL, json=load_status())
    await _press(hass, button)
    await coordinator._follow_task
    assert len(_gets(api_response)) == coordinator_module.REFRESH_POLL_MAX_ATTEMPTS


async def test_follow_stops_when_the_server_goes_away(
    hass, setup_entry, api_response, entity_id, monkeypatch
):
    monkeypatch.setattr(coordinator_module, "UNAVAILABLE_AFTER_FAILURES", 1)
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    assert hass.states.get(button).attributes["icon"] == "mdi:database-refresh"
    coordinator = setup_entry.runtime_data.coordinator
    api_response.clear_requests()
    api_response.post(REFRESH_URL, status=202, json={"queued": True})
    api_response.get(STATUS_URL, status=500)
    await _press(hass, button)
    await coordinator._follow_task
    assert len(_gets(api_response)) == 1


async def test_second_press_restarts_the_follow(
    hass, setup_entry, api_response, entity_id, monkeypatch
):
    """Only one follow-up runs at a time, so presses cannot pile up polls."""
    monkeypatch.setattr(coordinator_module, "REFRESH_POLL_INTERVAL", 3600)
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    assert hass.states.get(button).attributes["icon"] == "mdi:database-refresh"
    coordinator = setup_entry.runtime_data.coordinator
    await _press(hass, button)
    first = coordinator._follow_task
    await _press(hass, button)
    await hass.async_block_till_done()
    assert first.cancelled()
    assert not coordinator._follow_task.done()
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert coordinator._follow_task.done()


async def test_cooldown_is_ignored(hass, setup_entry, api_response, entity_id):
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    api_response.clear_requests()
    api_response.post(
        REFRESH_URL, status=429, json={"error": "cooldown", "retryAfter": 20}
    )
    api_response.get(STATUS_URL, json=setup_entry.runtime_data.coordinator.data)
    await _press(hass, button)  # must not raise
    await hass.async_block_till_done()
    assert len(_posts(api_response)) == 1


async def test_connection_error_raises(hass, setup_entry, api_response, entity_id):
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    api_response.clear_requests()
    api_response.post(REFRESH_URL, status=500)
    with pytest.raises(HomeAssistantError):
        await _press(hass, button)


async def test_auth_error_raises_and_starts_reauth(
    hass, setup_entry, api_response, entity_id
):
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    api_response.clear_requests()
    api_response.post(REFRESH_URL, status=401)
    with pytest.raises(HomeAssistantError):
        await _press(hass, button)
    await hass.async_block_till_done()
    assert any(
        flow["context"].get("source") == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )
