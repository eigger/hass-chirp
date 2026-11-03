"""Config entries and the external HTTP boundary for the Chirp tests."""

import json
from pathlib import Path

import pytest

# <!-- hass-standards:domain-fixtures:start -->
# Use pytest_homeassistant_custom_component.common.MockConfigEntry for
# mock_config_entry when the integration uses config entries.
# Define mock_client only when an external communication client is present.
# Mock external communication boundaries, never Home Assistant core modules.
# Keep integration-specific fixtures below this managed block.
# <!-- hass-standards:domain-fixtures:end -->
from pytest_homeassistant_custom_component.common import MockConfigEntry

FIXTURES = Path(__file__).parent / "fixtures"
INSTANCE_ID = "8f0c2b7e-3a41-4d6e-9b1f-5c7d2e8a9f10"
HDD_ID = "wwn_5000c500a1b2c3d4"
NVME_ID = "nvme_eui_0025385b21400001"
STATUS_URL = "http://chirp.test/api/v1/status"
REFRESH_URL = "http://chirp.test/api/v1/refresh"


def load_status(name: str = "status.json") -> dict:
    """Load one of the status fixtures."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def status_payload():
    return load_status()


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain="chirp",
        title="pve",
        unique_id=INSTANCE_ID,
        data={
            "host": "chirp.test",
            "port": 80,
            "api_key": "chp_test_key_0123456789abcdef",
            "ssl": False,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def api_response(aioclient_mock, status_payload):
    aioclient_mock.get(STATUS_URL, json=status_payload)
    aioclient_mock.post(REFRESH_URL, status=202, json={"queued": True})
    return aioclient_mock


@pytest.fixture
async def setup_entry(hass, entry, api_response):
    """Load the entry with the baseline fixture."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def entity_id(hass):
    from homeassistant.helpers import entity_registry as er

    def lookup(unique_id, domain="sensor"):
        result = er.async_get(hass).async_get_entity_id(domain, "chirp", unique_id)
        assert result is not None, unique_id
        return result

    return lookup


@pytest.fixture
def registered(hass):
    """Return the entity registry entry for a unique ID, or None."""
    from homeassistant.helpers import entity_registry as er

    def lookup(unique_id, domain="sensor"):
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(domain, "chirp", unique_id)
        return registry.async_get(entity_id) if entity_id else None

    return lookup


@pytest.fixture
def device_for(hass):
    """Return the device of an entry by its (domain, identifier) pair."""
    from homeassistant.helpers import device_registry as dr

    def lookup(entry, identifier):
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        ):
            if ("chirp", identifier) in device.identifiers:
                return device
        return None

    return lookup
