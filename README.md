<!-- hass-standards:header:start -->
# Chirp Home Assistant Integration (hass-chirp)

A read-only Home Assistant custom integration that shows Chirp disk SMART health, disk temperatures and CPU temperature.

**English** | [한국어](README.ko.md)

<!-- hass-standards:badges:start -->
[![Release](https://img.shields.io/github/v/release/eigger/hass-chirp?style=flat)](https://github.com/eigger/hass-chirp/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat)](#installation)
[![Home Assistant minimum](https://img.shields.io/badge/HA-%E2%89%A5%202025.3.0-41BDF5?style=flat)](hacs.json)
[![Tests](https://img.shields.io/github/actions/workflow/status/eigger/hass-chirp/tests.yml?branch=master&style=flat&label=Tests)](https://github.com/eigger/hass-chirp/actions/workflows/tests.yml)
[![Validate](https://img.shields.io/github/actions/workflow/status/eigger/hass-chirp/validate.yml?branch=master&style=flat&label=Validate)](https://github.com/eigger/hass-chirp/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/eigger/hass-chirp?style=flat)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/eigger/hass-chirp/latest/total?style=flat&color=41BDF5&label=Downloads)](https://github.com/eigger/hass-chirp/releases)
<!-- hass-standards:badges:end -->
<!-- hass-standards:header:end -->

![Chirp](custom_components/chirp/brand/logo.png)

A **read-only** Home Assistant custom integration for [Chirp](https://github.com/eigger/chirp), a self-hosted monitor for disk SMART health and temperatures. It polls Chirp's `/api/v1/status` endpoint (every 60 seconds by default) and exposes the host's CPU temperature and every disk's temperature, health and SMART counters as entities.

## Features

- One device for the monitored host (CPU temperature, boot time, "any disk problem" and a SMART refresh button) plus one device per disk
- Per-disk temperature (kept while the disk is in standby), power-on hours, health (`ok` / `warning` / `failing` with reasons; Home Assistant's *unknown* until Chirp has read the disk) and a SMART problem binary sensor
- Protocol-specific counters: reallocated and pending sectors for SATA, wear, available spare, data written and media errors for SSD/NVMe
- Disks that appear later are added automatically; disks that vanish become unavailable
- Last known values ride out brief outages; after 3 failed polls in a row the entities become unavailable until Chirp answers again. A consecutive error counter stays available for diagnosis

## Requirements

Home Assistant **2025.3.0 or newer**, a reachable [Chirp](https://github.com/eigger/chirp) server and its API key. Uses local HTTP/HTTPS polling; no Bluetooth is needed.

## Installation

<!-- hass-standards:installation:start -->
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eigger&repository=hass-chirp&category=integration)
<!-- hass-standards:installation:end -->

1. Install Chirp on the machine you want to monitor. On Proxmox VE, the one-click script creates a container for you:

   ```sh
   bash -c "$(curl -fsSL https://raw.githubusercontent.com/eigger/chirp/master/proxmox/ct/chirp.sh)"
   ```

2. Add `eigger/hass-chirp` as a custom **Integration** repository in HACS, install **Chirp** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Chirp**.
4. Enter the Chirp **host** (IP address or name), **port** (default `80`) and **API key**. Tick *Use HTTPS* only if Chirp is served over HTTPS; untick *Verify SSL certificate* only for a self-signed certificate on a server you trust.

The API key starts with `chp_`. On the Chirp host, show it with `cat /var/lib/chirp/api-key` (inside a Proxmox container: `pct exec <ctid> -- cat /var/lib/chirp/api-key`). [More details](docs/user-guide.md#installation)

## Usage

```yaml
action: button.press
target:
  entity_id: button.pve_refresh_smart_data
```

Use the actual entity ID created by your installation. The button asks Chirp to re-read SMART data now and then polls a few more times (every 5 seconds, up to 30 seconds) until the new readings arrive; Chirp applies its own cooldown and the integration ignores it. Integration options let you change the polling interval (30–3600 seconds). [Troubleshooting](docs/user-guide.md#limitations-and-troubleshooting)

## Documentation

| Guide | Contents |
|---|---|
| [User guide](docs/user-guide.md) | Setup and API key, entities and attributes, health reasons, troubleshooting |
| [Development and tests](docs/development.md) | Real-HA tests, minimum/current environments, dependencies and commands |
| [Adopted standards](STANDARDS.md) · [Checklist](ADOPTION_CHECKLIST.md) | Common rules and verification records |

<!-- hass-standards:support:start -->
## Support

- [Issues](https://github.com/eigger/hass-chirp/issues): Report bugs or request features.
- [Discussions](https://github.com/eigger/hass-chirp/discussions): Ask questions and share your experience.
<!-- hass-standards:support:end -->

<!-- hass-standards:related-projects:start -->
## Related Projects

- [Chirp](https://github.com/eigger/chirp): The self-hosted disk and CPU monitor this integration connects to.
<!-- hass-standards:related-projects:end -->

<!-- hass-standards:license:start -->
## License

Released under the [MIT License](LICENSE).
<!-- hass-standards:license:end -->
