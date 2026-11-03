"""Constants for the Chirp integration."""

from __future__ import annotations

DOMAIN = "chirp"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_SSL = "ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 80
DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = True
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

MANUFACTURER = "Chirp (self-hosted)"

HEALTH_OK = "ok"
HEALTH_WARNING = "warning"
HEALTH_FAILING = "failing"
# The server's "unknown" verdict maps to Home Assistant's own unknown state
# (None), so it is not an ENUM option.
HEALTH_STATES = [HEALTH_OK, HEALTH_WARNING, HEALTH_FAILING]

# Entities stay available with the last good snapshot through brief outages and
# become unavailable once this many polls in a row have failed.
UNAVAILABLE_AFTER_FAILURES = 3

# After a queued SMART refresh (202), re-poll the status this often until the
# disks' lastReadAt values settle, at most this many times.
REFRESH_POLL_INTERVAL = 5.0
REFRESH_POLL_MAX_ATTEMPTS = 6
