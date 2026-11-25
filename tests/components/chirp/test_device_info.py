"""DeviceInfo is built with keyword arguments (TypedDict and dataclass)."""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.chirp import entity as chirp_entity
from custom_components.chirp.const import MANUFACTURER
from custom_components.chirp.entity import (
    dashboard_url,
    disk_device_info,
    host_device_fields,
    host_device_info,
    interface_device_info,
)

from .conftest import HDD_ID, INSTANCE_ID, load_status

PACKAGE = Path(__file__).parents[3] / "custom_components" / "chirp"

# Deprecated since HA 2026.12 (removed 2027.12).
DEPRECATED_CONSTANTS = {
    "ATTR_CONFIGURATION_URL",
    "ATTR_CONNECTIONS",
    "ATTR_DEFAULT_NAME",
    "ATTR_HW_VERSION",
    "ATTR_IDENTIFIERS",
    "ATTR_MANUFACTURER",
    "ATTR_MODEL",
    "ATTR_MODEL_ID",
    "ATTR_SERIAL_NUMBER",
    "ATTR_SUGGESTED_AREA",
    "ATTR_SW_VERSION",
    "ATTR_VIA_DEVICE",
}

DISK = {"id": HDD_ID, "model": "ST4000", "serial": "ZDH1ABCD", "firmware": "SC60"}
INTERFACE = {"id": "eno1", "name": "eno1", "kind": "physical"}


def _field(info, name):
    """Read a field the same way on the TypedDict and the dataclass."""
    return info.get(name) if isinstance(info, dict) else getattr(info, name)


def _fields(info) -> dict:
    """Return the set fields of a DeviceInfo as a dict on both implementations."""
    if isinstance(info, dict):
        return dict(info)
    return {k: v for k, v in info.as_dict().items() if v is not None}


def test_host_device_fields_are_exact(entry):
    status = load_status()
    fields = host_device_fields(entry, status)
    assert fields == {
        "identifiers": {("chirp", INSTANCE_ID)},
        "name": status["instance"]["hostname"],
        "manufacturer": MANUFACTURER,
        "model": status["cpu"]["model"],
        "sw_version": status["instance"]["version"],
        "configuration_url": dashboard_url(entry),
    }
    assert _fields(host_device_info(entry, status)) == fields


def test_host_device_fields_keep_none_model(entry):
    status = load_status()
    status["cpu"] = None
    fields = host_device_fields(entry, status)
    assert "model" in fields
    assert fields["model"] is None


@pytest.mark.parametrize("uses_id", [False, True])
def test_via_field_selection(hass, entry, uses_id):
    entry.add_to_hass(hass)
    host = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **host_device_fields(entry, load_status()),
    )
    with patch.object(chirp_entity, "_USES_VIA_DEVICE_ID", uses_id):
        if not uses_id and "via_device_id" in DeviceInfo.__annotations__:
            pytest.skip("via_device is not a DeviceInfo field on this release")
        if uses_id and "via_device_id" not in DeviceInfo.__annotations__:
            pytest.skip("via_device_id is not a DeviceInfo field on this release")
        for info in (
            disk_device_info(hass, entry, INSTANCE_ID, DISK),
            interface_device_info(hass, entry, load_status(), INTERFACE),
        ):
            fields = _fields(info)
            if uses_id:
                assert fields["via_device_id"] == host.id
                assert "via_device" not in fields
            else:
                assert fields["via_device"] == ("chirp", INSTANCE_ID)
                assert "via_device_id" not in fields


def test_no_host_device_means_no_via_field(hass, entry):
    entry.add_to_hass(hass)
    with patch.object(chirp_entity, "_USES_VIA_DEVICE_ID", True):
        assert chirp_entity._via_host(hass, entry, INSTANCE_ID) == {}
        if "via_device_id" in DeviceInfo.__annotations__:
            fields = _fields(disk_device_info(hass, entry, INSTANCE_ID, DISK))
            assert "via_device_id" not in fields
            assert "via_device" not in fields


def test_via_host_kwargs_for_each_mode(hass, entry):
    entry.add_to_hass(hass)
    host = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **host_device_fields(entry, load_status()),
    )
    with patch.object(chirp_entity, "_USES_VIA_DEVICE_ID", True):
        assert chirp_entity._via_host(hass, entry, INSTANCE_ID) == {
            "via_device_id": host.id
        }
    with patch.object(chirp_entity, "_USES_VIA_DEVICE_ID", False):
        assert chirp_entity._via_host(hass, entry, INSTANCE_ID) == {
            "via_device": ("chirp", INSTANCE_ID)
        }


async def test_setup_registers_host_with_keyword_arguments(hass, entry, api_response):
    original = dr.DeviceRegistry.async_get_or_create
    with patch.object(
        dr.DeviceRegistry, "async_get_or_create", autospec=True, side_effect=original
    ) as create:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    host_calls = [
        c
        for c in create.call_args_list
        if c.kwargs.get("identifiers") == {("chirp", INSTANCE_ID)}
    ]
    assert host_calls
    assert host_calls[0].kwargs == {
        "config_entry_id": entry.entry_id,
        **host_device_fields(entry, load_status()),
    }


async def test_setup_registers_host_device(hass, setup_entry, device_for):
    host = device_for(setup_entry, INSTANCE_ID)
    assert host.name == load_status()["instance"]["hostname"]
    assert host.manufacturer == MANUFACTURER
    assert host.model == "Intel(R) Core(TM) i5-12500"
    assert host.sw_version == "0.1.0"
    assert host.configuration_url == dashboard_url(setup_entry)


def test_no_deprecated_device_info_use():
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "homeassistant.const"
            ):
                names = {alias.name for alias in node.names}
                assert not names & DEPRECATED_CONSTANTS, path
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    assert not (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id in {"info", "device_info"}
                    ), f"{path}:{node.lineno} item assignment"
