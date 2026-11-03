"""The refresh button queues a SMART read and refreshes the coordinator."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from .conftest import INSTANCE_ID, REFRESH_URL, STATUS_URL


async def _press(hass, entity_id):
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


def _posts(aioclient_mock):
    return [call for call in aioclient_mock.mock_calls if call[0] == "post"]


def _gets(aioclient_mock):
    return [call for call in aioclient_mock.mock_calls if call[0] == "get"]


async def test_press_posts_refresh_and_updates(
    hass, setup_entry, api_response, entity_id
):
    button = entity_id(f"{INSTANCE_ID}_refresh_smart", "button")
    gets_before = len(_gets(api_response))
    await _press(hass, button)
    await hass.async_block_till_done()
    posts = _posts(api_response)
    assert len(posts) == 1
    assert str(posts[0][1]) == REFRESH_URL
    assert posts[0][3]["Authorization"].startswith("Bearer chp_test_key")
    assert len(_gets(api_response)) == gets_before + 1


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
