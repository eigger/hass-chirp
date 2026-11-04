"""Exercise config, reauth, reconfigure and options flows through HA."""

from unittest.mock import patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.chirp.const import DOMAIN

from .conftest import INSTANCE_ID, REFRESH_URL, STATUS_URL, load_status

KEY = "chp_new_key_0123456789abcdef"
USER_INPUT = {"host": "chirp.test", "port": 80, "api_key": KEY, "ssl": False}


async def _start_user(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_creates_entry(hass, aioclient_mock, status_payload):
    aioclient_mock.get(STATUS_URL, json=status_payload)
    aioclient_mock.post(REFRESH_URL, status=202)
    result = await _start_user(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "host": " chirp.test ", "api_key": f" {KEY} "}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "pve"
    assert result["data"] == {**USER_INPUT, "verify_ssl": True}
    assert result["result"].unique_id == INSTANCE_ID
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {KEY}"


async def test_user_flow_defaults_port_80(hass, aioclient_mock, status_payload):
    aioclient_mock.get(STATUS_URL, json=status_payload)
    aioclient_mock.post(REFRESH_URL, status=202)
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "chirp.test", "api_key": KEY}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["port"] == 80
    assert result["data"]["ssl"] is False


async def test_user_flow_https_custom_port(hass, aioclient_mock, status_payload):
    aioclient_mock.get("https://chirp.test:8443/api/v1/status", json=status_payload)
    aioclient_mock.post("https://chirp.test:8443/api/v1/refresh", status=202)
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "chirp.test", "port": 8443, "api_key": KEY, "ssl": True},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["port"] == 8443
    assert result["data"]["ssl"] is True


@pytest.mark.parametrize(
    ("mock_kwargs", "host", "expected"),
    [
        ({"status": 401}, "chirp.test", "invalid_auth"),
        ({"status": 403}, "chirp.test", "invalid_auth"),
        ({"status": 500}, "chirp.test", "cannot_connect"),
        ({"exc": aiohttp.ClientConnectionError}, "chirp.test", "cannot_connect"),
        ({"exc": TimeoutError}, "chirp.test", "cannot_connect"),
        ({"text": "<html>"}, "chirp.test", "cannot_connect"),
        ({"status": 200}, "http://chirp.test", "invalid_host"),
        ({"status": 200}, "chirp.test/api", "invalid_host"),
    ],
)
async def test_user_flow_errors_then_recovery(
    hass, aioclient_mock, status_payload, mock_kwargs, host, expected
):
    aioclient_mock.get(STATUS_URL, **mock_kwargs)
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "host": host}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=status_payload)
    aioclient_mock.post(REFRESH_URL, status=202)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_instance_updates_address_and_key(hass, entry, aioclient_mock):
    aioclient_mock.get("https://chirp-new.test:8443/api/v1/status", json=load_status())
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "chirp-new.test", "port": 8443, "api_key": KEY, "ssl": True},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "chirp-new.test"
    assert entry.data["port"] == 8443
    assert entry.data["ssl"] is True
    assert entry.data["verify_ssl"] is True
    # The entered key authenticated against this instance, so it is stored too.
    assert entry.data["api_key"] == KEY


async def test_reauth_flow_success_and_errors(hass, setup_entry, aioclient_mock):
    entry = setup_entry
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, status=401)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "chp_bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, status=500)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "chp_bad"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    other = load_status()
    other["instance"]["id"] = "00000000-0000-4000-8000-000000000000"
    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=other)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": KEY}
    )
    assert result["errors"] == {"base": "wrong_instance"}
    assert entry.data["api_key"] != KEY

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=load_status())
    aioclient_mock.post(REFRESH_URL, status=202)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": f" {KEY} "}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_key"] == KEY
    assert entry.state is ConfigEntryState.LOADED


async def test_reconfigure_flow(hass, setup_entry, aioclient_mock):
    entry = setup_entry
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    aioclient_mock.clear_requests()
    aioclient_mock.get("http://other.test:8080/api/v1/status", status=500)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "other.test", "port": 8080, "ssl": False}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    other = load_status()
    other["instance"]["id"] = "00000000-0000-4000-8000-000000000000"
    aioclient_mock.clear_requests()
    aioclient_mock.get("http://other.test:8080/api/v1/status", json=other)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "other.test", "port": 8080, "ssl": False}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_instance"
    assert entry.data["host"] == "chirp.test"

    result = await entry.start_reconfigure_flow(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get("http://other.test:8080/api/v1/status", json=load_status())
    aioclient_mock.post("http://other.test:8080/api/v1/refresh", status=202)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "other.test", "port": 8080, "ssl": False}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "other.test"
    assert entry.data["port"] == 8080
    assert entry.data["api_key"].startswith("chp_test_key")  # key reused
    assert entry.state is ConfigEntryState.LOADED


async def test_reconfigure_invalid_host(hass, setup_entry):
    result = await setup_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "http://x", "port": 80, "ssl": False}
    )
    assert result["errors"] == {"base": "invalid_host"}


async def test_options_flow_changes_scan_interval(hass, setup_entry):
    entry = setup_entry
    first = entry.runtime_data.coordinator
    assert first.update_interval.total_seconds() == 60
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 120}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "scan_interval": 120,
        **{
            f"monitor_{group}": True
            for group in ("cpu", "ram", "smart", "network", "hardware", "storage")
        },
    }
    assert entry.runtime_data.coordinator is not first
    assert entry.runtime_data.coordinator.update_interval.total_seconds() == 120


@pytest.mark.parametrize("value", [10, 5000])
async def test_options_flow_rejects_out_of_range(hass, setup_entry, value):
    from voluptuous import Invalid

    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    with pytest.raises(Exception) as err:
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": value}
        )
    assert isinstance(err.value, Invalid) or "scan_interval" in str(err.value)


async def test_user_flow_self_signed_https_skips_verification(
    hass, aioclient_mock, status_payload
):
    """verify_ssl reaches HA's shared session helper for the flow and setup."""
    from homeassistant.helpers import aiohttp_client

    import custom_components.chirp as chirp_init
    from custom_components.chirp import config_flow

    calls = []

    def recording(hass, verify_ssl=True, **kwargs):
        calls.append(verify_ssl)
        return aiohttp_client.async_get_clientsession(hass, verify_ssl, **kwargs)

    aioclient_mock.get("https://chirp.test/api/v1/status", json=status_payload)
    with (
        patch.object(config_flow, "async_get_clientsession", recording),
        patch.object(chirp_init, "async_get_clientsession", recording),
    ):
        result = await _start_user(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {**USER_INPUT, "port": 443, "ssl": True, "verify_ssl": False},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["verify_ssl"] is False
    assert calls == [False, False]


async def test_reconfigure_changes_verify_ssl(hass, setup_entry, aioclient_mock):
    entry = setup_entry
    assert "verify_ssl" not in entry.data  # entries from before the option
    result = await entry.start_reconfigure_flow(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get("https://chirp.test/api/v1/status", json=load_status())
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "chirp.test", "port": 443, "ssl": True, "verify_ssl": False},
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["ssl"] is True
    assert entry.data["verify_ssl"] is False
    assert entry.state is ConfigEntryState.LOADED


async def test_duplicate_with_rejected_key_keeps_entry(hass, entry, aioclient_mock):
    aioclient_mock.get(STATUS_URL, status=401)
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["api_key"] != KEY


async def test_duplicate_reloads_loaded_entry_with_new_key(
    hass, setup_entry, aioclient_mock
):
    first = setup_entry.runtime_data.coordinator
    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=load_status())
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()
    assert result["reason"] == "already_configured"
    assert setup_entry.data["api_key"] == KEY
    assert setup_entry.state is ConfigEntryState.LOADED
    assert setup_entry.runtime_data.coordinator is not first
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == f"Bearer {KEY}"
