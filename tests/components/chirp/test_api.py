"""Exercise the HTTP client against the mocked Chirp boundary."""

import logging

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.chirp.api import (
    ChirpApi,
    ChirpAuthError,
    ChirpConnectionError,
    build_base_url,
    normalize_host,
)

from .conftest import REFRESH_URL, STATUS_URL

KEY = "chp_secret_key_value_0123456789"


def make_api(hass, **kwargs):
    params = {"host": "chirp.test", "port": 80, "api_key": f" {KEY} ", "use_ssl": False}
    params.update(kwargs)
    return ChirpApi(async_get_clientsession(hass), **params)


async def test_get_status_sends_bearer_key(hass, aioclient_mock, status_payload):
    aioclient_mock.get(STATUS_URL, json=status_payload)
    status = await make_api(hass).async_get_status()
    assert status["instance"]["id"] == status_payload["instance"]["id"]
    assert len(status["disks"]) == 2
    method, url, _data, headers = aioclient_mock.mock_calls[0]
    assert (method, str(url)) == ("get", STATUS_URL)
    assert headers["Authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("code", [401, 403])
async def test_auth_errors(hass, aioclient_mock, code):
    aioclient_mock.get(STATUS_URL, status=code)
    with pytest.raises(ChirpAuthError):
        await make_api(hass).async_get_status()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 500},
        {"status": 429},
        {"exc": TimeoutError},
        {"exc": aiohttp.ClientConnectionError},
        {"text": "not json"},
        {"json": []},
        {"json": {"apiVersion": 1, "instance": {"id": "x"}}},
        {"json": {"apiVersion": 1, "instance": {}, "disks": []}},
        {"json": {"apiVersion": "1", "instance": {"id": "x"}, "disks": []}},
        {"json": {"apiVersion": 1, "instance": {"id": "x"}, "disks": {}}},
    ],
)
async def test_connection_and_format_errors_hide_secrets(hass, aioclient_mock, kwargs):
    aioclient_mock.get(STATUS_URL, **kwargs)
    with pytest.raises(ChirpConnectionError) as err:
        await make_api(hass).async_get_status()
    message = str(err.value)
    assert "chirp.test" not in message
    assert KEY not in message
    assert "http" not in message


async def test_newer_api_version_warns_once(
    hass, aioclient_mock, status_payload, caplog
):
    status_payload["apiVersion"] = 2
    aioclient_mock.get(STATUS_URL, json=status_payload)
    api = make_api(hass)
    with caplog.at_level(logging.WARNING):
        await api.async_get_status()
        await api.async_get_status()
    assert sum("API version 2" in r.message for r in caplog.records) == 1


async def test_non_dict_disks_are_dropped(hass, aioclient_mock, status_payload):
    status_payload["disks"].append("garbage")
    aioclient_mock.get(STATUS_URL, json=status_payload)
    assert len((await make_api(hass).async_get_status())["disks"]) == 2


async def test_refresh_queued_cooldown_and_errors(hass, aioclient_mock):
    api = make_api(hass)
    aioclient_mock.post(REFRESH_URL, status=202)
    assert await api.async_refresh() is True
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {KEY}"
    aioclient_mock.clear_requests()
    aioclient_mock.post(REFRESH_URL, status=429, json={"error": "cooldown"})
    assert await api.async_refresh() is False
    aioclient_mock.clear_requests()
    aioclient_mock.post(REFRESH_URL, status=401)
    with pytest.raises(ChirpAuthError):
        await api.async_refresh()
    aioclient_mock.clear_requests()
    aioclient_mock.post(REFRESH_URL, status=500)
    with pytest.raises(ChirpConnectionError):
        await api.async_refresh()


async def test_port_and_ssl_in_url(hass, aioclient_mock, status_payload):
    aioclient_mock.get("https://chirp.test:8443/api/v1/status", json=status_payload)
    api = make_api(hass, port=8443, use_ssl=True)
    assert api.base_url == "https://chirp.test:8443"
    await api.async_get_status()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" chirp.test ", "chirp.test"),
        ("192.168.1.10", "192.168.1.10"),
        ("fe80::1", "[fe80::1]"),
        ("[fe80::1]", "[fe80::1]"),
        ("FE80:0:0::0001", "[fe80::1]"),
        ("chirp_host", "chirp_host"),
    ],
)
def test_normalize_host(value, expected):
    assert normalize_host(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "  ",
        "http://chirp.test",
        "chirp.test/path",
        "chirp.test:80",
        "a b",
        "u@h",
        "[:::::]",
        "[chirp.test]",
        "fe80::1%eth0",
        "gg::1",
        "chirp%2etest",
        "chirp<test>",
        "-chirp",
        "chirp..test",
        "[::1]:8080",
    ],
)
def test_normalize_host_rejects(value):
    with pytest.raises(ValueError):
        normalize_host(value)


def test_build_base_url_hides_default_ports():
    assert build_base_url("h", 80, False) == "http://h"
    assert build_base_url("h", 443, True) == "https://h"
    assert build_base_url("h", 443, False) == "http://h:443"
    assert build_base_url("h", 8080, True) == "https://h:8080"


async def test_disks_without_usable_id_are_dropped(
    hass, aioclient_mock, status_payload
):
    status_payload["disks"].append({"name": "sdz"})
    status_payload["disks"].append({"id": "", "name": "sdy"})
    status_payload["disks"].append({"id": 5, "name": "sdx"})
    aioclient_mock.get(STATUS_URL, json=status_payload)
    disks = (await make_api(hass).async_get_status())["disks"]
    assert [disk["id"] for disk in disks] == [
        status_payload["disks"][0]["id"],
        status_payload["disks"][1]["id"],
    ]
