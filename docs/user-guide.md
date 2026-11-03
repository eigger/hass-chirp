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

The key starts with `chp_` and is stored on the Chirp host:

```sh
cat /var/lib/chirp/api-key
# or
node /opt/chirp/current/apps/server/dist/cli.js key show
```

For a Proxmox container, prefix the command with `pct exec <ctid> --`, for example `pct exec 105 -- cat /var/lib/chirp/api-key`. `... cli.js key rotate` creates a new key; update Home Assistant afterwards through the re-authentication form. If `CHIRP_API_KEY` is set on the server, it takes precedence over the key file.

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
| Any disk problem | Problem sensor; on when any disk is in `warning` or `failing` state |
| Refresh SMART data | Button; asks Chirp to re-read SMART now, then follows the read with a few polls |

**Disk devices** (one per disk, named `model (last four serial characters)`, attached to the host):

| Entity | Notes |
|---|---|
| Temperature | Keeps the last value while the disk is in standby; attribute `standby` |
| Power-on hours | Total increasing |
| Power cycle count | Diagnostic |
| Health | `ok`, `warning` or `failing`; Home Assistant's *unknown* when Chirp reports no verdict; attribute `reasons` |
| SMART problem | Problem sensor; on for `warning` or `failing`; attributes `reasons`, `smart_passed` |
| Reallocated sectors, Pending sectors | SATA disks, enabled by default |
| Offline uncorrectable sectors, UDMA CRC errors | SATA disks, diagnostic |
| Wear | SSD and NVMe, percentage of life used |
| Available spare | NVMe, percent |
| Data written | NVMe, TB |
| Media errors, Unsafe shutdowns | NVMe, diagnostic |

New disks are added automatically on the next poll. A disk that Chirp has not read yet (standby or unreadable since the server started) only has a temporary `dev_<name>` ID; its entities are created after the first read, when Chirp reports the permanent ID. A disk that disappears from Chirp's response becomes unavailable; delete its device from the device page if it is gone for good. The host device cannot be deleted.

### Health reasons

The `reasons` attribute lists objects with a `code` and an optional `value`. Codes come from the Chirp API: `smart_failed`, `nvme_critical_warning`, `spare_below_threshold`, `reallocated_sectors`, `pending_sectors`, `offline_uncorrectable`, `media_errors`, `wear_high`, `temperature_high` and `not_read`. When Chirp's verdict is `unknown` (it could not read the disk, for example `not_read`), the health sensor shows Home Assistant's own *unknown* state rather than a separate option, the `reasons` attribute still explains why, and the SMART problem sensor is *unknown* too, so it is not reported as a problem.

## Usage

```yaml
action: button.press
target:
  entity_id: button.pve_refresh_smart_data
```

Select the actual entity created by your installation. Chirp queues the read (HTTP 202) and runs it in the background, so the integration polls the status every 5 seconds, at most 6 times, and stops as soon as the disks' read times have changed and settled. Pressing again restarts that follow-up instead of adding another one. Chirp rate-limits refreshes (HTTP 429); the integration treats that as success and refreshes its data once.

Example automation that notifies about a failing disk:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.pve_any_disk_problem
    to: "on"
actions:
  - action: notify.notify
    data:
      message: A disk reported a SMART problem.
```

## Limitations and troubleshooting

- The integration is read-only except for the SMART refresh request. Change thresholds and settings in Chirp.
- Home Assistant polls only `GET /api/v1/status`. SMART values change on Chirp's own schedule, so a short polling interval does not give fresher SMART data.
- When Chirp cannot be reached, entities keep their last values for up to 2 failed polls; the third failure in a row makes them unavailable until the next success. The consecutive fetch error counter stays available throughout and returns to zero after the next success. A rejected API key makes the entities unavailable at once and starts Home Assistant's re-authentication flow.
- **Cannot connect**: check host, port and the HTTPS switch (with a self-signed certificate, turn off **Verify SSL certificate**); open `http://<host>:<port>/health` in a browser. The address field takes a host name, IPv4 or IPv6 address only, not a URL; IPv6 zone IDs (`%eth0`) are not supported.
- **Invalid authentication**: copy the key again from `/var/lib/chirp/api-key`. A key from a different Chirp instance is rejected during re-authentication.
- API versions: this release supports Chirp API version 1. If Chirp reports a newer version, a single warning is logged and the known fields are still used.
- Remove API keys, host names, IP addresses and disk serial numbers from issue reports. Diagnostics redact them automatically.
- Tests use real Home Assistant with mocked HTTP responses and do not certify a live Chirp server.
