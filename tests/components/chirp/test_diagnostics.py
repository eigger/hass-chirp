"""Diagnostics must never leak the key, address or disk identity (HA-12)."""

import json

from homeassistant.components.diagnostics import REDACTED

from custom_components.chirp.diagnostics import async_get_config_entry_diagnostics

from .conftest import HDD_ID, STATUS_URL, load_status


async def test_diagnostics_redaction(hass, setup_entry):
    result = await async_get_config_entry_diagnostics(hass, setup_entry)
    assert result["entry"]["data"]["api_key"] == REDACTED
    assert result["entry"]["data"]["host"] == REDACTED
    assert result["entry"]["data"]["port"] == 80
    status = result["status"]
    assert status["instance"]["id"] == REDACTED
    assert status["instance"]["hostname"] == REDACTED
    for disk in status["disks"]:
        assert disk["serial"] == REDACTED
        assert disk["devicePath"] == REDACTED
        assert disk["id"] == REDACTED
    # Useful, non-identifying data remains.
    assert status["cpu"]["packageTemp"] == 47.0
    assert status["disks"][0]["health"]["status"] == "warning"
    assert result["coordinator"]["consecutive_errors"] == 0

    dump = json.dumps(result)
    for secret in (
        "chp_test_key",
        "chirp.test",
        "ZDH1ABCD",
        "S5GXNF0R123456A",
        HDD_ID,
        "5000c500a1b2c3d4",
        "/dev/disk/by-id",
        "8f0c2b7e",
        '"pve"',
    ):
        assert secret not in dump, secret


async def test_diagnostics_redacts_wwn_and_serial_number_keys(
    hass, entry, aioclient_mock
):
    payload = load_status()
    payload["disks"][0]["wwn"] = "0x5000c500a1b2c3d4"
    payload["disks"][0]["serial_number"] = "ZDH1ABCD"
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await async_get_config_entry_diagnostics(hass, entry)
    disk = result["status"]["disks"][0]
    assert disk["wwn"] == REDACTED
    assert disk["serial_number"] == REDACTED
