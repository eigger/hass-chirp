"""Host metrics: memory, load, power, fans, voltages and network interfaces."""

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.chirp import async_remove_config_entry_device

from .conftest import HDD_ID, INSTANCE_ID, STATUS_URL, load_status

NET = f"{INSTANCE_ID}_net"
NET_DEVICE = f"{INSTANCE_ID}:net:"
SAMPLE_INTERFACES = ("bond0", "eno1", "enp3s0", "vmbr0", "vmbr0_100")
INTERFACE_SENSOR_KEYS = (
    "rx_rate",
    "tx_rate",
    "rx_total",
    "tx_total",
    "speed",
    "rx_errors",
    "tx_errors",
    "rx_dropped",
    "tx_dropped",
)
METRIC_KEYS = (
    "data_scope",
    "memory_available",
    "swap_used",
    "swap_total",
    "io_wait_percent",
    "memory_used_percent",
    "memory_used",
    "memory_total",
    "swap_used_percent",
    "cpu_usage_percent",
    "load_1m",
    "load_5m",
    "load_15m",
    "package_power",
)
SAMPLE_LIST_KEYS = (
    "hardware_temperature_temp_0011223344556677",
    "power_source_rapl_package_0",
    "power_source_rapl_package_0_core",
    "power_source_rapl_package_0_uncore",
    "power_source_rapl_psys",
    "fan_nct6798_cpu_fan",
    "fan_nct6798_fan2",
    "voltage_nct6798_in0",
    "voltage_nct6798_3_3v",
)
DISABLED_BY_DEFAULT = (
    "memory_used",
    "memory_total",
    "swap_used",
    "swap_total",
    "load_5m",
    "load_15m",
    "power_source_rapl_package_0",
    "power_source_rapl_package_0_core",
    "power_source_rapl_package_0_uncore",
    "power_source_rapl_psys",
    "fan_nct6798_fan2",
    "voltage_nct6798_in0",
    "voltage_nct6798_3_3v",
)


async def _setup(hass, entry, aioclient_mock, fixture):
    aioclient_mock.get(STATUS_URL, json=load_status(fixture))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _refresh(hass, entry, aioclient_mock, payload):
    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, json=payload)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


def _metric_unique_ids(hass, entry):
    """Return the unique IDs of every host metric and interface entity."""
    prefixes = (
        *(f"{INSTANCE_ID}_{key}" for key in METRIC_KEYS),
        f"{INSTANCE_ID}_hardware_temperature_",
        f"{INSTANCE_ID}_power_source_",
        f"{INSTANCE_ID}_fan_",
        f"{INSTANCE_ID}_voltage_",
        f"{NET}_",
    )
    return {
        reg.unique_id
        for reg in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if reg.unique_id.startswith(prefixes)
    }


def _enable_all(hass, entry):
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.disabled_by is not None:
            registry.async_update_entity(reg.entity_id, disabled_by=None)


async def _setup_all_enabled(hass, entry, aioclient_mock, fixture):
    await _setup(hass, entry, aioclient_mock, fixture)
    _enable_all(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_sample_creates_every_metric_entity(hass, entry, aioclient_mock):
    await _setup(hass, entry, aioclient_mock, "status.json")
    expected = {
        *(f"{INSTANCE_ID}_{key}" for key in (*METRIC_KEYS, *SAMPLE_LIST_KEYS)),
        *(
            f"{NET}_{iface}_{key}"
            for iface in SAMPLE_INTERFACES
            for key in (*INTERFACE_SENSOR_KEYS, "link")
        ),
    }
    assert _metric_unique_ids(hass, entry) == expected


async def test_sample_defaults_and_categories(hass, entry, aioclient_mock, registered):
    await _setup(hass, entry, aioclient_mock, "status.json")
    for key in DISABLED_BY_DEFAULT:
        reg = registered(f"{INSTANCE_ID}_{key}")
        assert reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
    for key in (
        "data_scope",
        "memory_used_percent",
        "swap_used_percent",
        "cpu_usage_percent",
        "load_1m",
        "package_power",
        "fan_nct6798_cpu_fan",
    ):
        assert registered(f"{INSTANCE_ID}_{key}").disabled_by is None, key
    for key in ("data_scope", "memory_total"):
        assert registered(f"{INSTANCE_ID}_{key}").entity_category.value == (
            "diagnostic"
        )
    for key in ("memory_used_percent", "cpu_usage_percent", "package_power"):
        assert registered(f"{INSTANCE_ID}_{key}").entity_category is None
    for key in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped"):
        reg = registered(f"{NET}_eno1_{key}")
        assert reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
        assert reg.entity_category.value == "diagnostic"
    for key in ("rx_total", "tx_total", "speed"):
        reg = registered(f"{NET}_eno1_{key}")
        assert reg.disabled_by is None, key
        assert reg.entity_category.value == "diagnostic"
    for key in ("rx_rate", "tx_rate"):
        assert registered(f"{NET}_eno1_{key}").entity_category is None
    assert registered(f"{NET}_eno1_link", "binary_sensor").disabled_by is None
    assert registered(f"{INSTANCE_ID}_fan_nct6798_cpu_fan").translation_key == "fan"
    assert registered(f"{NET}_eno1_speed").translation_key == "link_speed"


async def test_sample_memory_and_load_values(hass, entry, aioclient_mock, entity_id):
    await _setup_all_enabled(hass, entry, aioclient_mock, "status.json")

    def state(key):
        return hass.states.get(entity_id(f"{INSTANCE_ID}_{key}"))

    used = state("memory_used_percent")
    assert used.state == "37.6"
    assert used.attributes["unit_of_measurement"] == "%"
    assert used.attributes["state_class"] == "measurement"
    assert used.attributes["scope"] == "host"
    assert "device_class" not in used.attributes

    size = state("memory_used")
    assert size.attributes["device_class"] == "data_size"
    assert size.attributes["unit_of_measurement"] == "GiB"
    assert size.attributes["state_class"] == "measurement"
    assert float(size.state) == pytest.approx(25232932864 / 2**30)
    total = state("memory_total")
    assert float(total.state) == pytest.approx(67108864000 / 2**30)
    assert "state_class" not in total.attributes
    assert total.attributes["scope"] == "host"

    swap = state("swap_used_percent")
    assert swap.state == "3.1"
    assert swap.attributes["unit_of_measurement"] == "%"

    cpu = state("cpu_usage_percent")
    assert cpu.state == "6.4"
    assert cpu.attributes["unit_of_measurement"] == "%"
    assert cpu.attributes["scope"] == "host"
    assert cpu.attributes["cpu_count"] == 12
    for key, value in (("load_1m", "0.84"), ("load_5m", "0.71"), ("load_15m", "0.65")):
        load = state(key)
        assert load.state == value, key
        assert load.attributes["state_class"] == "measurement"
        assert "unit_of_measurement" not in load.attributes
        assert load.attributes["cpu_count"] == 12

    scope = state("data_scope")
    assert scope.state == "host"
    assert scope.attributes["device_class"] == "enum"
    assert scope.attributes["options"] == ["host", "container", "mixed"]
    assert scope.attributes["memory_scope"] == "host"
    assert scope.attributes["load_scope"] == "host"
    assert scope.attributes["network_scope"] == "host"


async def test_sample_power_fan_voltage_values(hass, entry, aioclient_mock, entity_id):
    await _setup_all_enabled(hass, entry, aioclient_mock, "status.json")

    def state(key):
        return hass.states.get(entity_id(f"{INSTANCE_ID}_{key}"))

    package = state("package_power")
    assert package.state == "18.4"
    assert package.attributes["device_class"] == "power"
    assert package.attributes["unit_of_measurement"] == "W"
    assert package.attributes["state_class"] == "measurement"
    assert package.attributes["source"] == "rapl"
    assert package.attributes["scope"] == "host"

    psys = state("power_source_rapl_psys")
    assert psys.state == "24.9"
    assert psys.attributes["device_class"] == "power"
    assert psys.attributes["unit_of_measurement"] == "W"
    assert psys.attributes["friendly_name"] == "pve psys power"
    assert state("power_source_rapl_package_0_core").state == "11.2"

    fan = state("fan_nct6798_cpu_fan")
    assert fan.state == "1180"
    assert fan.attributes["unit_of_measurement"] == "rpm"
    assert fan.attributes["state_class"] == "measurement"
    assert fan.attributes["chip"] == "nct6798"
    assert fan.attributes["friendly_name"] == "pve CPU Fan speed"
    assert "device_class" not in fan.attributes
    assert state("fan_nct6798_fan2").state == "0"

    volt = state("voltage_nct6798_3_3v")
    assert volt.state == "3.344"
    assert volt.attributes["device_class"] == "voltage"
    assert volt.attributes["unit_of_measurement"] == "V"
    assert volt.attributes["state_class"] == "measurement"
    assert volt.attributes["friendly_name"] == "pve +3.3V voltage"
    assert state("voltage_nct6798_in0").state == "1.032"


async def test_sample_interface_values(hass, entry, aioclient_mock, entity_id):
    await _setup_all_enabled(hass, entry, aioclient_mock, "status.json")

    def state(iface, key, domain="sensor"):
        return hass.states.get(entity_id(f"{NET}_{iface}_{key}", domain))

    rx = state("bond0", "rx_rate")
    assert rx.attributes["device_class"] == "data_rate"
    assert rx.attributes["unit_of_measurement"] == "Mbit/s"
    assert rx.attributes["state_class"] == "measurement"
    assert rx.attributes["scope"] == "host"
    assert rx.attributes["friendly_name"] == "pve bond0 Receive rate"
    assert float(rx.state) == pytest.approx(152340.5 * 8 / 1e6)
    assert float(state("bond0", "tx_rate").state) == pytest.approx(40210.2 * 8 / 1e6)

    total = state("vmbr0", "rx_total")
    assert total.attributes["device_class"] == "data_size"
    assert total.attributes["unit_of_measurement"] == "GB"
    assert total.attributes["state_class"] == "total_increasing"
    assert float(total.state) == pytest.approx(790123456789 / 1e9)

    speed = state("eno1", "speed")
    assert speed.state == "1000"
    assert speed.attributes["device_class"] == "data_rate"
    assert speed.attributes["unit_of_measurement"] == "Mbit/s"
    assert "state_class" not in speed.attributes
    assert state("vmbr0", "speed").state == "unknown"

    dropped = state("eno1", "rx_dropped")
    assert dropped.state == "12"
    assert dropped.attributes["state_class"] == "total_increasing"
    assert state("eno1", "tx_errors").state == "0"

    up = state("eno1", "link", "binary_sensor")
    assert up.state == "on"
    assert up.attributes["device_class"] == "connectivity"
    assert up.attributes["oper_state"] == "up"
    assert up.attributes["kind"] == "physical"
    assert up.attributes["scope"] == "host"
    down = state("enp3s0", "link", "binary_sensor")
    assert down.state == "off"
    assert down.attributes["oper_state"] == "down"
    assert state("vmbr0_100", "link", "binary_sensor").attributes["kind"] == "vlan"


async def test_interface_devices_hang_off_the_host(
    hass, entry, aioclient_mock, device_for
):
    await _setup(hass, entry, aioclient_mock, "status.json")
    host = device_for(entry, INSTANCE_ID)
    vlan = device_for(entry, f"{NET_DEVICE}vmbr0_100")
    assert vlan.name == "pve vmbr0.100"
    assert vlan.model == "VLAN"
    assert vlan.via_device_id == host.id
    assert device_for(entry, f"{NET_DEVICE}bond0").model == "Bond"
    assert device_for(entry, f"{NET_DEVICE}eno1").model == "Physical interface"
    assert device_for(entry, f"{NET_DEVICE}vmbr0").model == "Bridge"
    # Memory, load, power, fan and voltage sensors belong to the host device.
    registry = er.async_get(hass)
    for key in ("memory_used_percent", "package_power", "fan_nct6798_cpu_fan"):
        entity = registry.async_get(
            registry.async_get_entity_id("sensor", "chirp", f"{INSTANCE_ID}_{key}")
        )
        assert entity.device_id == host.id, key


async def test_container_scope_fixture(
    hass, entry, aioclient_mock, entity_id, registered
):
    await _setup_all_enabled(hass, entry, aioclient_mock, "status_container_scope.json")
    expected = {
        *(f"{INSTANCE_ID}_{key}" for key in METRIC_KEYS if key != "io_wait_percent"),
        f"{INSTANCE_ID}_power_source_rapl_package_0",
        *(f"{NET}_eth0_{key}" for key in (*INTERFACE_SENSOR_KEYS, "link")),
    }
    assert _metric_unique_ids(hass, entry) == expected

    def state(key):
        return hass.states.get(entity_id(f"{INSTANCE_ID}_{key}"))

    scope = state("data_scope")
    assert scope.state == "container"
    assert scope.attributes["memory_scope"] == "container"
    memory = state("memory_used_percent")
    assert memory.state == "25.0"
    assert memory.attributes["scope"] == "container"
    assert float(state("memory_total").state) == pytest.approx(0.5)
    # Swap is configured (0 % used), so the sensor exists and reads 0.
    assert state("swap_used_percent").state == "0.0"
    cpu = state("cpu_usage_percent")
    assert cpu.state == "unknown"
    assert cpu.attributes["scope"] == "container"
    assert cpu.attributes["cpu_count"] == 1
    # A RAPL source exists but has no reading yet (first sample).
    package = state("package_power")
    assert package.state == "unknown"
    assert package.attributes["source"] == "rapl"
    assert state("power_source_rapl_package_0").state == "unknown"

    rx = hass.states.get(entity_id(f"{NET}_eth0_rx_rate"))
    assert rx.state == "unknown"
    assert rx.attributes["scope"] == "container"
    assert hass.states.get(entity_id(f"{NET}_eth0_speed")).state == "10000"
    link = hass.states.get(entity_id(f"{NET}_eth0_link", "binary_sensor"))
    assert link.state == "on"
    assert link.attributes["scope"] == "container"
    # Container-scope entities keep the same defaults as host-scope ones.
    assert registered(f"{INSTANCE_ID}_memory_used_percent").disabled_by is None


@pytest.mark.parametrize("fixture", ["status_null_sections.json", "status_legacy.json"])
async def test_null_and_legacy_create_no_metric_entities(
    hass, entry, aioclient_mock, fixture, entity_id, caplog
):
    await _setup(hass, entry, aioclient_mock, fixture)
    assert _metric_unique_ids(hass, entry) == set()
    # The existing entities are unaffected.
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_cpu_temperature")).state == "47.0"
    assert "Traceback" not in caplog.text
    assert "Error" not in caplog.text


async def test_mixed_scope(hass, entry, aioclient_mock, entity_id):
    payload = load_status()
    payload["network"]["scope"] = "container"
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    scope = hass.states.get(entity_id(f"{INSTANCE_ID}_data_scope"))
    assert scope.state == "mixed"
    assert scope.attributes["memory_scope"] == "host"
    assert scope.attributes["network_scope"] == "container"


@pytest.mark.parametrize("fixture", ["status_null_sections.json", "status_legacy.json"])
async def test_sections_that_disappear_become_unavailable(
    hass, entry, aioclient_mock, entity_id, fixture
):
    await _setup(hass, entry, aioclient_mock, "status.json")
    keys = (
        "data_scope",
        "memory_used_percent",
        "swap_used_percent",
        "cpu_usage_percent",
        "load_1m",
        "package_power",
        "fan_nct6798_cpu_fan",
    )
    for key in keys:
        assert hass.states.get(entity_id(f"{INSTANCE_ID}_{key}")).state != (
            "unavailable"
        )
    await _refresh(hass, entry, aioclient_mock, load_status(fixture))
    for key in keys:
        state = hass.states.get(entity_id(f"{INSTANCE_ID}_{key}"))
        assert state.state == "unavailable", key
    for iface in SAMPLE_INTERFACES:
        assert hass.states.get(entity_id(f"{NET}_{iface}_rx_rate")).state == (
            "unavailable"
        )
        link = hass.states.get(entity_id(f"{NET}_{iface}_link", "binary_sensor"))
        assert link.state == "unavailable"
    # Disks and CPU temperatures keep working.
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_cpu_temperature")).state == "47.0"

    await _refresh(hass, entry, aioclient_mock, load_status())
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_memory_used_percent")).state == (
        "37.6"
    )
    assert hass.states.get(entity_id(f"{NET}_eno1_link", "binary_sensor")).state == (
        "on"
    )


async def test_sections_that_appear_later_are_added(
    hass, entry, aioclient_mock, registered, entity_id
):
    await _setup(hass, entry, aioclient_mock, "status_legacy.json")
    assert registered(f"{INSTANCE_ID}_memory_used_percent") is None
    await _refresh(hass, entry, aioclient_mock, load_status())
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_memory_used_percent")).state == (
        "37.6"
    )
    assert hass.states.get(entity_id(f"{NET}_bond0_link", "binary_sensor")).state == (
        "on"
    )


async def test_null_values_are_unknown(hass, entry, aioclient_mock, entity_id):
    await _setup(hass, entry, aioclient_mock, "status.json")
    payload = load_status()
    payload["memory"]["usedPercent"] = None
    payload["load"]["load1"] = None
    payload["power"]["packageWatts"] = None
    payload["fans"][0]["rpm"] = None
    payload["network"]["interfaces"][0]["rxBytesPerSec"] = None
    payload["network"]["interfaces"][0]["up"] = None
    await _refresh(hass, entry, aioclient_mock, payload)
    for unique_id, domain in (
        (f"{INSTANCE_ID}_memory_used_percent", "sensor"),
        (f"{INSTANCE_ID}_load_1m", "sensor"),
        (f"{INSTANCE_ID}_package_power", "sensor"),
        (f"{INSTANCE_ID}_fan_nct6798_cpu_fan", "sensor"),
        (f"{NET}_bond0_rx_rate", "sensor"),
        (f"{NET}_bond0_link", "binary_sensor"),
    ):
        assert hass.states.get(entity_id(unique_id, domain)).state == "unknown"


async def test_swap_sensor_needs_swap(hass, entry, aioclient_mock, registered):
    payload = load_status()
    payload["memory"].update(swapTotalBytes=0, swapUsedBytes=0, swapUsedPercent=None)
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_swap_used_percent") is None
    assert registered(f"{INSTANCE_ID}_memory_used_percent") is not None


async def test_package_power_needs_a_source(hass, entry, aioclient_mock, registered):
    payload = load_status()
    payload["power"].update(packageWatts=None, packageSource=None)
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registered(f"{INSTANCE_ID}_package_power") is None
    assert registered(f"{INSTANCE_ID}_power_source_rapl_psys") is not None


async def test_repeated_labels_get_the_chip_name(
    hass, entry, aioclient_mock, entity_id
):
    payload = load_status()
    payload["fans"] = [
        {"id": "nct6798_fan1", "chip": "nct6798", "label": "fan1", "rpm": 900},
        {"id": "amdgpu_fan1", "chip": "amdgpu", "label": "fan1", "rpm": 1500},
    ]
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    names = {
        hass.states.get(entity_id(f"{INSTANCE_ID}_fan_{fan}")).attributes[
            "friendly_name"
        ]
        for fan in ("nct6798_fan1", "amdgpu_fan1")
    }
    assert names == {"pve nct6798 fan1 speed", "pve amdgpu fan1 speed"}


async def test_interfaces_and_fans_added_and_removed(
    hass, entry, aioclient_mock, entity_id, registered, device_for
):
    await _setup(hass, entry, aioclient_mock, "status.json")
    host = device_for(entry, INSTANCE_ID)
    enp = device_for(entry, f"{NET_DEVICE}enp3s0")
    assert not await async_remove_config_entry_device(hass, entry, enp)
    assert not await async_remove_config_entry_device(hass, entry, host)

    payload = load_status()
    payload["network"]["interfaces"] = [
        iface for iface in payload["network"]["interfaces"] if iface["id"] != "enp3s0"
    ]
    payload["network"]["interfaces"].append(
        {
            **payload["network"]["interfaces"][1],
            "id": "eno2",
            "name": "eno2",
            "rxBytesPerSec": 1000,
        }
    )
    payload["fans"] = payload["fans"][1:]
    await _refresh(hass, entry, aioclient_mock, payload)

    assert hass.states.get(entity_id(f"{NET}_enp3s0_rx_rate")).state == "unavailable"
    assert (
        hass.states.get(entity_id(f"{NET}_enp3s0_link", "binary_sensor")).state
        == "unavailable"
    )
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_fan_nct6798_cpu_fan")).state == (
        "unavailable"
    )
    assert float(
        hass.states.get(entity_id(f"{NET}_eno2_rx_rate")).state
    ) == pytest.approx(0.008)
    assert device_for(entry, f"{NET_DEVICE}eno2").via_device_id == host.id
    # Only the vanished interface device can be removed.
    assert await async_remove_config_entry_device(hass, entry, enp)
    assert not await async_remove_config_entry_device(
        hass, entry, device_for(entry, f"{NET_DEVICE}eno2")
    )
    dr.async_get(hass).async_remove_device(enp.id)
    await hass.async_block_till_done()
    assert registered(f"{NET}_enp3s0_rx_rate") is None
    assert registered(f"{NET}_enp3s0_link", "binary_sensor") is None
    assert device_for(entry, f"{NET_DEVICE}enp3s0") is None

    # The interface comes back in the same session: it gets new entities.
    await _refresh(hass, entry, aioclient_mock, load_status())
    assert hass.states.get(entity_id(f"{NET}_enp3s0_rx_rate")).state == "0.0"
    assert (
        hass.states.get(entity_id(f"{NET}_enp3s0_link", "binary_sensor")).state == "off"
    )
    assert registered(f"{NET}_enp3s0_rx_errors").disabled_by is (
        er.RegistryEntryDisabler.INTEGRATION
    )
    assert device_for(entry, f"{NET_DEVICE}enp3s0").via_device_id == host.id


async def test_server_outage_keeps_metrics_then_unavailable(
    hass, entry, aioclient_mock, entity_id
):
    await _setup(hass, entry, aioclient_mock, "status.json")
    memory = entity_id(f"{INSTANCE_ID}_memory_used_percent")
    link = entity_id(f"{NET}_eno1_link", "binary_sensor")
    coordinator = entry.runtime_data.coordinator
    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, status=500)
    for _ in range(2):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(memory).state == "37.6"
        assert hass.states.get(link).state == "on"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(memory).state == "unavailable"
    assert hass.states.get(link).state == "unavailable"


async def test_removed_disk_device_is_recreated_when_the_disk_returns(
    hass, entry, aioclient_mock, entity_id, registered, device_for
):
    await _setup(hass, entry, aioclient_mock, "status.json")
    disk = f"{INSTANCE_ID}_{HDD_ID}"
    await _refresh(hass, entry, aioclient_mock, load_status("status_disk_removed.json"))
    device = device_for(entry, disk)
    assert await async_remove_config_entry_device(hass, entry, device)
    dr.async_get(hass).async_remove_device(device.id)
    await hass.async_block_till_done()
    assert registered(f"{disk}_temperature") is None

    await _refresh(hass, entry, aioclient_mock, load_status())
    assert hass.states.get(entity_id(f"{disk}_temperature")).state == "34"
    assert (
        hass.states.get(entity_id(f"{disk}_smart_problem", "binary_sensor")).state
        == "on"
    )


async def test_disk_and_interface_ids_cannot_share_a_device(
    hass, entry, aioclient_mock, device_for, registered
):
    """A disk ID ``net_eno1`` and the interface ``eno1`` stay separate."""
    payload = load_status()
    payload["disks"][0]["id"] = "net_eno1"
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    disk = device_for(entry, f"{INSTANCE_ID}_net_eno1")
    interface = device_for(entry, f"{NET_DEVICE}eno1")
    assert disk is not None and interface is not None
    assert disk.id != interface.id
    assert disk.name == "ST4000VN008-2DR166 (ABCD)"
    assert interface.name == "pve eno1"
    registry = er.async_get(hass)
    assert (
        registry.async_get(
            registered(f"{INSTANCE_ID}_net_eno1_temperature").entity_id
        ).device_id
        == disk.id
    )
    assert registered(f"{NET}_eno1_rx_rate").device_id == interface.id
    # Both are present, so neither can be removed.
    assert not await async_remove_config_entry_device(hass, entry, disk)
    assert not await async_remove_config_entry_device(hass, entry, interface)

    # Only the disk vanishes: its device is removable, the interface's is not.
    payload = load_status()
    payload["disks"] = payload["disks"][1:]
    await _refresh(hass, entry, aioclient_mock, payload)
    assert await async_remove_config_entry_device(hass, entry, disk)
    assert not await async_remove_config_entry_device(hass, entry, interface)

    # Only the interface vanishes: the reverse.
    payload = load_status()
    payload["disks"][0]["id"] = "net_eno1"
    payload["network"]["interfaces"] = [
        iface for iface in payload["network"]["interfaces"] if iface["id"] != "eno1"
    ]
    await _refresh(hass, entry, aioclient_mock, payload)
    assert not await async_remove_config_entry_device(hass, entry, disk)
    assert await async_remove_config_entry_device(hass, entry, interface)


async def test_labels_that_name_the_reading_are_not_repeated(
    hass, entry, aioclient_mock, entity_id, registered
):
    payload = load_status()
    payload["power"]["sources"] = [
        {"id": "zenpower_power1", "label": "power1", "watts": 30.5},
        {"id": "zenpower_ppt", "label": "PPT", "watts": 45.0},
    ]
    payload["voltages"] = [
        {
            "id": "it8686_vcore",
            "chip": "it8686",
            "label": "Vcore Voltage",
            "volts": 1.2,
        },
    ]
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    _enable_all(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    def name(key):
        return hass.states.get(entity_id(f"{INSTANCE_ID}_{key}")).attributes[
            "friendly_name"
        ]

    assert name("power_source_zenpower_power1") == "pve power1"
    assert name("power_source_zenpower_ppt") == "pve PPT power"
    assert name("voltage_it8686_vcore") == "pve Vcore Voltage"
    assert registered(
        f"{INSTANCE_ID}_power_source_zenpower_power1"
    ).translation_key == ("labeled_reading")
    assert registered(f"{INSTANCE_ID}_power_source_zenpower_ppt").translation_key == (
        "power_source"
    )


async def test_unknown_scope_value(hass, entry, aioclient_mock, entity_id):
    """A scope this release does not know: summary unknown, raw value shown."""
    payload = load_status()
    payload["memory"]["scope"] = "vm"
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(f"{INSTANCE_ID}_data_scope")).state == "unknown"
    memory = hass.states.get(entity_id(f"{INSTANCE_ID}_memory_used_percent"))
    assert memory.attributes["scope"] == "vm"
    assert memory.state == "37.6"


async def test_repeated_item_ids_use_the_first_item(
    hass, entry, aioclient_mock, entity_id
):
    payload = load_status()
    payload["fans"].append({**payload["fans"][0], "rpm": 9999})
    aioclient_mock.get(STATUS_URL, json=payload)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    fan = hass.states.get(entity_id(f"{INSTANCE_ID}_fan_nct6798_cpu_fan"))
    assert fan.state == "1180"
    # A repeated ID is not a second reading with the same label: no chip prefix.
    assert fan.attributes["friendly_name"] == "pve CPU Fan speed"


async def test_allowed_but_not_performed_removal_keeps_entities(
    hass, entry, aioclient_mock, entity_id, registered, device_for, caplog
):
    """Removal allowed (True) but the device stays: no duplicate entities."""
    await _setup(hass, entry, aioclient_mock, "status.json")
    payload = load_status()
    payload["network"]["interfaces"] = [
        iface for iface in payload["network"]["interfaces"] if iface["id"] != "enp3s0"
    ]
    await _refresh(hass, entry, aioclient_mock, payload)
    enp = device_for(entry, f"{NET_DEVICE}enp3s0")
    assert await async_remove_config_entry_device(hass, entry, enp)
    # Home Assistant does not remove the device after all; the interface returns.
    await _refresh(hass, entry, aioclient_mock, load_status())
    assert "does not generate unique IDs" not in caplog.text
    assert hass.states.get(entity_id(f"{NET}_enp3s0_rx_rate")).state == "0.0"
    assert (
        hass.states.get(entity_id(f"{NET}_enp3s0_link", "binary_sensor")).state == "off"
    )
    assert registered(f"{NET}_enp3s0_rx_rate").device_id == enp.id

    # Removing it later for real still brings the entities back on return.
    await _refresh(hass, entry, aioclient_mock, payload)
    assert await async_remove_config_entry_device(hass, entry, enp)
    dr.async_get(hass).async_remove_device(enp.id)
    await hass.async_block_till_done()
    assert registered(f"{NET}_enp3s0_rx_rate") is None
    await _refresh(hass, entry, aioclient_mock, load_status())
    assert hass.states.get(entity_id(f"{NET}_enp3s0_rx_rate")).state == "0.0"
    assert "does not generate unique IDs" not in caplog.text
