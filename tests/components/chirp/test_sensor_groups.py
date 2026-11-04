"""Group selection in setup/options/reconfigure and registry preservation."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.chirp.groups import GROUPS, entity_group

from .conftest import INSTANCE_ID, STATUS_URL, load_status


async def test_initial_checkboxes_only_add_selected_groups(hass, aioclient_mock):
    aioclient_mock.get(STATUS_URL, json=load_status())
    result = await hass.config_entries.flow.async_init(
        "chirp", context={"source": config_entries.SOURCE_USER}
    )
    choices = {f"monitor_{group}": group == "ram" for group in GROUPS}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "chirp.test",
            "api_key": "chp_test_key_0123456789abcdef",
            **choices,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert dict(entry.options) == choices
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert entities
    assert {entity_group(entity.unique_id, INSTANCE_ID) for entity in entities} == {
        None,
        "ram",
    }


async def test_options_disable_restore_preserves_names_and_user_disables(
    hass, setup_entry, registered
):
    entry = setup_entry
    registry = er.async_get(hass)
    cpu = registered(f"{INSTANCE_ID}_cpu_temperature")
    core = registered(f"{INSTANCE_ID}_cpu_max_temperature")
    registry.async_update_entity(cpu.entity_id, name="My CPU")
    registry.async_update_entity(
        core.entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    for enabled in (False, True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "scan_interval": 90,
                **{f"monitor_{group}": enabled for group in GROUPS},
            },
        )
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY
        saved = registry.async_get(cpu.entity_id)
        assert saved.name == "My CPU"
        assert saved.disabled_by is (
            None if enabled else er.RegistryEntryDisabler.INTEGRATION
        )
        assert (
            registry.async_get(core.entity_id).disabled_by
            is er.RegistryEntryDisabler.USER
        )
        assert (
            registered(f"{INSTANCE_ID}_fan_nct6798_fan2").disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert registered(f"{INSTANCE_ID}_fetch_errors").disabled_by is None
        state = hass.states.get(cpu.entity_id)
        if enabled:
            assert state.state == "47.0"
        else:
            assert state is None or state.state == "unavailable"


async def test_reconfigure_can_change_groups_without_changing_connection(
    hass, setup_entry
):
    entry = setup_entry
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "chirp.test",
            "port": 80,
            "ssl": False,
            "monitor_network": False,
        },
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.options["monitor_network"] is False
    assert entry.options["monitor_cpu"] is True
    network = [
        entity
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity_group(entity.unique_id, INSTANCE_ID) == "network"
    ]
    assert network
    assert all(entity.disabled_by is not None for entity in network)


async def test_options_new_group_discovers_later_items(
    hass, entry, aioclient_mock, registered
):
    hass.config_entries.async_update_entry(entry, options={"monitor_smart": False})
    payload = load_status()
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_{payload['disks'][0]['id']}_health") is None
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 60, "monitor_smart": True}
    )
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_{payload['disks'][0]['id']}_health") is not None
