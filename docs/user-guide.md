# User guide and troubleshooting

[English](user-guide.md) | [한국어](ko/user-guide.md) | [README](../README.md)

## Requirements

- Home Assistant **2025.3.0 or newer**, a reachable [Chirp](https://github.com/eigger/chirp) server and its API key.
- Local HTTP/HTTPS polling; no Bluetooth adapter or proxy is used.
- The integration domain is `chirp` (display name **Chirp**).

## Installation

### 1. Install the Chirp server

Chirp runs on the machine whose disks and CPU you want to watch. On Proxmox VE, run the one-click script on the node. It creates a container and installs Chirp:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/eigger/chirp/master/proxmox/ct/chirp.sh)"
```

Chirp listens on port **80** by default (`CHIRP_PORT`). Its dashboard is at `http://<host>/`.

### 2. Find the API key

1. Open the chirp dashboard (`http://<chirp host>/`). On a fresh install, create the admin account first: whoever opens the dashboard first becomes the admin, so do this right after installing chirp.
2. Sign in and go to **Settings → API key**.
3. Click **Copy** (or **Show** to read it), then paste the key into the chirp integration in Home Assistant together with the chirp host and port.

**Regenerate** in the same place creates a new key. The old key stops working immediately, so update the integration afterwards (Home Assistant will ask you to re-authenticate). If the key is set with `CHIRP_API_KEY` on the server, it is shown read-only and must be changed there. On the server you can also print it with `node apps/server/dist/cli.js key show` (Proxmox: `pct exec <CTID> -- node /opt/chirp/current/apps/server/dist/cli.js key show`; Docker: `docker exec chirp node apps/server/dist/cli.js key show`).

### 3. Install and add the integration

1. On Home Assistant 2025.3.0 or newer, add `eigger/hass-chirp` as a custom **Integration** repository in HACS.
2. Install **Chirp** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Chirp**.
4. Enter the **host** (IP address or host name, without `http://` or a path), the **port** (default `80`) and the **API key**. Enable **Use HTTPS** only if Chirp is served over HTTPS, for example behind a reverse proxy. **Verify SSL certificate** is on by default; turn it off only when that proxy uses a self-signed certificate and you trust the server.

Each Chirp instance has a unique ID. Adding the same instance again (for example after its IP address changed) updates the stored host, port, HTTPS settings and API key instead of creating a duplicate. The new key is stored only after it authenticated against that same instance, so this is also a quick way to replace a rotated key. To change the address or HTTPS settings later, use **Reconfigure** on the integration entry; it only accepts the same instance. If a different Chirp instance starts answering at the stored address (for example after a DHCP change or a server reinstall), updates fail with `ChirpInstanceMismatchError` in the fetch error sensor and no entities are created for it; use **Reconfigure** to point the entry at the right server. The polling interval (default 60 seconds, 30–3600) is an integration option.

For manual installation, copy `custom_components/chirp` into the same path under your HA configuration directory and restart. To remove, delete the integration entry, uninstall through HACS or remove that directory, then restart.

## Supported features and entities

The integration creates only the entities the server actually reports. Disabled-by-default entities can be enabled from the entity settings.

**Host device** (named after the Chirp host name; model is the CPU model):

| Entity | Notes |
|---|---|
| CPU temperature | Package temperature, °C |
| CPU maximum temperature | Disabled by default |
| `<core>` temperature | One per CPU core, disabled by default. Identified by the core label (`Core 0` → `..._cpu_core_temperature_core_0`), so a server that lists cores in another order keeps each value on its entity; a repeated label gets `_2`, `_3`, … and a core without a label uses its position (`index_<n>`) |
| Boot time | Diagnostic; collection time minus uptime |
| Consecutive fetch errors | Diagnostic; stays available while Chirp is down; attributes `last_error`, `last_error_at`, `last_success_at` |

**Disk devices** (one per disk, named `model (last four serial characters)`, attached to the host):

| Entity | Notes |
|---|---|
| Temperature | Keeps the last value while the disk is in standby; attribute `standby` |
| Lifetime minimum/maximum temperature, Minimum/maximum temperature since power-on, Maximum operating temperature | °C, diagnostic; only when the disk records them (SATA SCT Status / Device Statistics; NVMe reports only the maximum operating temperature, its warning threshold). The since-power-on pair is disabled by default because many drives only mirror the current temperature there. Needs Chirp 0.3.2 or newer |
| Power-on hours | Total increasing |
| Refresh SMART data | Button; asks Chirp to re-read SMART now, then follows the read with a few polls. Chirp reads every disk in one pass, so any disk's button refreshes all disks (sleeping disks are still not woken) |
| Power cycle count | Diagnostic |
| Health | `ok`, `warning` or `failing`; Home Assistant's *unknown* when Chirp reports no verdict; attribute `reasons` |
| Health reason | Actual reasons as state (e.g. `High temperature (70 °C)`); full raw details in `reasons` |
| SMART problem | Problem sensor; on for `warning` or `failing`; attributes `reasons`, `smart_passed` |
| Reallocated sectors, Pending sectors | SATA disks, enabled by default |
| Offline uncorrectable sectors, UDMA CRC errors | SATA disks, diagnostic |
| Wear | SSD and NVMe, percentage of life used (SATA: Device Statistics endurance indicator when the disk has one) |
| Available spare | NVMe, percent |
| Data written | NVMe, and SATA disks (SSD or HDD) that report Device Statistics; TB |
| Media errors, Unsafe shutdowns | NVMe, diagnostic |

**Host metrics** (on the host device; only from Chirp servers that report them, see below):

| Entity | Key (unique ID suffix) | Unit / class | Default |
|---|---|---|---|
| Memory used | `memory_used_percent` | %, measurement | Enabled |
| Memory used size | `memory_used` | data size (shown in GiB), measurement | Disabled |
| Memory total | `memory_total` | data size (GiB) | Diagnostic, disabled |
| Swap used | `swap_used_percent` | %, measurement; only when the host has swap | Enabled |
| CPU usage | `cpu_usage_percent` | %, measurement; *unknown* until Chirp has two samples | Enabled |
| Load (1 min) | `load_1m` | measurement | Enabled |
| Load (5 min), Load (15 min) | `load_5m`, `load_15m` | measurement | Disabled |
| CPU package power | `package_power` | power, W, measurement; when Chirp has a RAPL or hwmon CPU power source (*unknown* on its first sample) | Enabled |
| `<label>` power | `power_source_<id>` | power, W, measurement; one per RAPL zone / hwmon power reading | Disabled |
| `<label>` speed | `fan_<id>` | rpm, measurement | Enabled when the fan was spinning when first seen, otherwise disabled (see below) |
| `<label>` voltage | `voltage_<id>` | voltage, V, measurement | Disabled |
| Metrics scope | `data_scope` | `host`, `container` or `mixed`; attributes `memory_scope`, `load_scope`, `network_scope` | Diagnostic, enabled |

The load sensors and CPU usage have a `cpu_count` attribute (logical CPUs in that scope). Fan, voltage and power source names are the label from the monitoring chip followed by "speed", "voltage" or "power" (`CPU Fan speed`, `+3.3V voltage`, `psys power`); a label that already says it (`power1`, `Vcore Voltage`) is used as is, and if two readings share a label the chip name is added.

**Fans that were stopped when first seen stay disabled.** Monitoring chips list every fan header, and headers with nothing connected report 0 rpm. Whether a fan sensor is enabled by default is decided once, when Home Assistant first registers it: a fan that was stopped (for example a zero-RPM GPU or case fan at idle) or reported no reading at that moment stays disabled even after it spins up. Enable it in the entity settings if you want it.

**Network interface devices** (one per interface Chirp lists, named `<host name> <interface>`, model `Physical interface`, `Bond`, `Bridge`, `VLAN` or `Virtual interface`, attached to the host). Unique IDs are `<instance id>_net_<interface id>_<key>`:

| Entity | Key | Unit / class | Default |
|---|---|---|---|
| Receive rate, Transmit rate | `rx_rate`, `tx_rate` | data rate, B/s from Chirp shown in Mbit/s, measurement; *unknown* on Chirp's first sample and after a counter reset | Enabled |
| Data received, Data sent | `rx_total`, `tx_total` | data size (shown in GB), total increasing (cumulative kernel counters since the interface was created) | Diagnostic, enabled |
| Link | `link` | connectivity binary sensor, on when Chirp reports the link as up (operstate `up`, or `unknown` with carrier); attributes `oper_state`, `kind` | Enabled |
| Link speed | `speed` | data rate, Mbit/s; *unknown* when the driver reports none (bridges, VLANs) and while the link is down | Diagnostic, enabled |
| Receive errors, Transmit errors, Receive drops, Transmit drops | `rx_errors`, `tx_errors`, `rx_dropped`, `tx_dropped` | total increasing | Diagnostic, disabled |

Chirp lists physical NICs, bonds, bridges and VLANs by default and hides `veth*`, `tap*`, Docker and other virtual devices; `CHIRP_NET_INCLUDE` / `CHIRP_NET_EXCLUDE` on the server change that. Each interface adds 6 entities enabled by default (rates, totals, link, link speed) and 4 disabled ones, so exclude interfaces you do not need on the server.

New disks are added automatically on the next poll. A disk that Chirp has not read yet (standby or unreadable since the server started) only has a temporary `dev_<name>` ID; its entities are created after the first read, when Chirp reports the permanent ID. A disk that disappears from Chirp's response becomes unavailable; delete its device from the device page if it is gone for good. The host device cannot be deleted.

### Host metrics: availability and scope

Host metrics need a Chirp server that reports them. An older server simply does not send them, and the integration then creates none of these entities (no errors). A section the server could not read at all (for example no RAPL or hwmon power source) is not created either. Every entity appears automatically once its data shows up, for example after a server update. A single value Chirp could not read is shown as *unknown*. If a whole section, an interface, a fan, a voltage or a power source disappears later, its entities become unavailable; a vanished interface or disk device can be deleted from its device page (if it comes back later, its entities are created again), and orphaned fan, voltage or power entities can be removed after a reload.

**Scope (host or container).** Chirp often runs in a container (Proxmox LXC, Docker). Memory, load and network values then come either from the **host** (Chirp reads the host's `/proc` and `/sys` mounted into the container, or it is not in a container) or from the **container**'s own view: in an LXC that can be the container's limits (for example 512 MB of RAM, one CPU) and its own `eth0`. Each memory, load and network entity has a `scope` attribute (`host` or `container`), and the diagnostic **Metrics scope** sensor summarises them (`mixed` when sections differ). Entity names do not change with the scope. If it says `container` but you want host values, give Chirp the host mounts described in Chirp's deployment guide ([host metrics](https://github.com/eigger/chirp/blob/master/docs/deploy.md#host-metrics-memory-load-network)). Container-scope entities keep the same defaults as host ones, so a later switch to host scope does not leave them disabled. Power, fan and voltage readings come from the host's hardware sensors in both cases and always have `scope: host`.

### Health reasons

Each disk's **Health reason** sensor (`..._health_reason`) exposes the reason and value as its state, for example `High temperature (70 °C)` or `Reallocated sectors (8)`. Multiple reasons are separated by `; `. Recovery shows `No issues`. A change of reason changes this sensor's state even if health remains `warning`, so **History** can show the actual past problem. Recorder must record this sensor; retention and exclusion settings apply. Reasons from before this sensor was added cannot be recovered retroactively.

Labels come from translation files using Home Assistant's configured language, with English fallback. Reload the integration after changing that language. Untranslated API codes are shown as received, and `reasons` retains all original codes and values. States longer than Home Assistant's 255-character limit are shortened with an ellipsis. A missing verdict with no reasons shows *unknown*; warning or failing without reasons explicitly shows `Warning (reason not reported)` or `Failing (reason not reported)`.

The `reasons` attribute lists objects with a `code` and an optional `value`. Codes come from the Chirp API: `smart_failed`, `nvme_critical_warning`, `spare_below_threshold`, `reallocated_sectors`, `pending_sectors`, `offline_uncorrectable`, `media_errors`, `wear_high`, `temperature_high` and `not_read`. When Chirp's verdict is `unknown` (it could not read the disk, for example `not_read`), the health sensor shows Home Assistant's own *unknown* state rather than a separate option, the `reasons` attribute still explains why, and the SMART problem sensor is *unknown* too, so it is not reported as a problem.

## Usage

```yaml
action: button.press
target:
  entity_id: button.wdc_wd40efrx_c3d4_refresh_smart_data
```

Select the actual entity created by your installation. Chirp queues the read (HTTP 202) and runs it in the background, so the integration polls the status every 5 seconds, at most 6 times, and stops as soon as the disks' read times have changed and settled. Pressing again restarts that follow-up instead of adding another one. Chirp rate-limits refreshes (HTTP 429); the integration treats that as success and refreshes its data once.

Example automation that notifies about a failing disk (list each disk's **SMART problem** sensor):

```yaml
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.wdc_wd40efrx_c3d4_smart_problem
      - binary_sensor.samsung_ssd_970_evo_plus_9a1b_smart_problem
    to: "on"
actions:
  - action: notify.notify
    data:
      message: "{{ trigger.to_state.name }} reported a SMART problem."
```

## Limitations and troubleshooting

- The integration is read-only except for the SMART refresh request. Change thresholds and settings in Chirp.
- Home Assistant polls only `GET /api/v1/status`. SMART values change on Chirp's own schedule, so a short polling interval does not give fresher SMART data.
- When Chirp cannot be reached, entities keep their last values for up to 2 failed polls; the third failure in a row makes them unavailable until the next success. The consecutive fetch error counter stays available throughout and returns to zero after the next success. A rejected API key makes the entities unavailable at once and starts Home Assistant's re-authentication flow.
- **Cannot connect**: check host, port and the HTTPS switch (with a self-signed certificate, turn off **Verify SSL certificate**); open `http://<host>:<port>/health` in a browser. The address field takes a host name, IPv4 or IPv6 address only, not a URL; IPv6 zone IDs (`%eth0`) are not supported.
- **Invalid authentication**: copy the key again from **Settings → API key** in the Chirp dashboard (it changes when someone regenerates it). A key from a different Chirp instance is rejected during re-authentication.
- API versions: this release supports Chirp API version 1. If Chirp reports a newer version, a single warning is logged and the known fields are still used.
- **Memory or network values look too small** (for example 512 MB of RAM or only `eth0`): check the `scope` attribute or the **Metrics scope** sensor. `container` means Chirp sees only its container; see [Host metrics: availability and scope](#host-metrics-availability-and-scope).
- Remove API keys, host names, IP addresses and disk serial numbers from issue reports. Diagnostics redact them automatically, as well as MAC addresses embedded in interface names (`enx…`, `wlx…`).
- Tests use real Home Assistant with mocked HTTP responses and do not certify a live Chirp server.

## Choosing sensor groups

During setup, use the CPU, RAM and swap, Disks and SMART, Network, Hardware, and Filesystems and ZFS checkboxes to select the Home Assistant entities to add. Change these later under **Settings → Devices & services → Chirp → Configure**, alongside the polling interval, or use **Reconfigure** to change groups together with the server address. Existing installations enable all groups by default.

Deselecting a group stops adding its entities and disables its existing entities. Selecting it again restores the entities enabled before the group was turned off, preserving entity IDs, custom names and individual user disables. Entities disabled by default stay disabled. Boot time, fetch errors and metrics scope remain available for diagnosis. Group selection affects Home Assistant entities; Chirp continues its own collection schedule.

### Additional sensors

| Sensor | Default / availability |
|---|---|
| Available memory | Enabled; existing API `memory.availableBytes`; GiB, scope attribute |
| Swap used / total | Disabled; only when swap is configured; GiB |
| I/O wait | Enabled when the server reports `load.ioWaitPercent`; %, scope and CPU count |
| Hardware temperatures | Disabled; one per `sensors[].id`. Older servers without stable IDs do not create these entities |
| SMART collection problem | Enabled diagnostic problem binary sensor; errors turn it on, never-read disks remain unknown. Attribute `last_read_at`: time of the last successful SMART read, retained during standby and failed reads (an attribute, so it does not fill the logbook) |
| SMART read error | Disabled diagnostic enum: none, open failed, timeout, parse error |
| Standby | Disabled diagnostic binary sensor; sleeping does not count as a collection failure |
| Filesystem usage / available bytes | Enabled per configured path; used and total bytes disabled |
| ZFS pool health / usage | Enabled per pool GUID; used, total and free bytes disabled |

I/O wait, stable temperature IDs and storage fields require the Chirp API extension in [server PR #7](https://github.com/eigger/chirp/pull/7). Existing memory and SMART diagnostics also work with older servers. Missing optional arrays create no entities; previously discovered items become unavailable when absent and recover under the same ID when they return. An unreadable individual value is unknown. ZFS health preserves the server's raw status (for example `ONLINE` or `DEGRADED`).

Filesystem/ZFS collection is opt-in on the server. Set `CHIRP_FILESYSTEM_PATHS=/,/data` and/or `CHIRP_ZFS_ENABLED=true` in Chirp, then restart it. Host paths inside a container additionally need an explicit read-only root mount and `CHIRP_HOST_ROOT`; otherwise filesystem scope is container. See the [server API contract](https://github.com/eigger/chirp/blob/master/docs/api.md#additional-host-and-storage-metrics). Pool free bytes are raw ZFS pool space, not dataset available space. Hardware temperature discovery can include disk temperatures already covered by SMART; enable only the readings you want.
