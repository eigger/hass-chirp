"""Constants for the Chirp integration."""

from __future__ import annotations

DOMAIN = "chirp"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_SSL = "ssl"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 80
DEFAULT_SSL = False
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

MANUFACTURER = "Chirp (self-hosted)"

HEALTH_OK = "ok"
HEALTH_WARNING = "warning"
HEALTH_FAILING = "failing"
HEALTH_UNKNOWN = "unknown"
HEALTH_STATES = [HEALTH_OK, HEALTH_WARNING, HEALTH_FAILING, HEALTH_UNKNOWN]
