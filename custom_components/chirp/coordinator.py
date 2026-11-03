"""Poll the Chirp server for host and disk status."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import ChirpApi, ChirpAuthError, ChirpError, ChirpInstanceMismatchError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def scan_interval_from_options(options: dict[str, Any]) -> timedelta:
    """Return the validated polling interval stored in the entry options."""
    try:
        seconds = int(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    except (TypeError, ValueError):
        seconds = DEFAULT_SCAN_INTERVAL
    return timedelta(seconds=max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, seconds)))


class ChirpCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch ``/api/v1/status`` and keep the last good snapshot on failure."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: ChirpApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} status",
            update_interval=scan_interval_from_options(entry.options),
        )
        self.api = api
        self._entry = entry
        self._reauth_started = False
        self.consecutive_errors = 0
        self.last_error: str | None = None
        self.last_error_at: str | None = None
        self.last_success_at: str | None = None

    @property
    def instance_id(self) -> str:
        """Return the Chirp instance ID that owns every device and unique ID."""
        return str(self.data["instance"]["id"])

    def get_disk(self, disk_id: str) -> dict[str, Any] | None:
        """Return a disk from the latest snapshot, or None if it disappeared."""
        for disk in (self.data or {}).get("disks", []):
            if disk.get("id") == disk_id:
                return disk
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.api.async_get_status()
            expected = self._entry.unique_id
            if expected and str(status["instance"]["id"]) != expected:
                # Another Chirp server now answers at this address (DHCP change or
                # reinstall). Its data must not be filed under this entry's IDs.
                raise ChirpInstanceMismatchError(
                    "A different Chirp instance answered at the configured address; "
                    "reconfigure the entry to point at the right server"
                )
        except ChirpError as err:
            self.consecutive_errors += 1
            self.last_error = (
                f"{type(err).__name__}: {err}" if str(err) else type(err).__name__
            )
            self.last_error_at = dt_util.utcnow().isoformat()
            log = _LOGGER.warning if self.consecutive_errors == 1 else _LOGGER.debug
            log(
                "Chirp update failed (%s consecutive failures): %s",
                self.consecutive_errors,
                self.last_error,
            )
            if self.data is not None:
                if isinstance(err, ChirpAuthError) and not self._reauth_started:
                    self._entry.async_start_reauth(self.hass)
                    self._reauth_started = True
                # Returning cached data keeps entities showing the last good values.
                return self.data

            # No cached state during the first refresh.
            if isinstance(err, ChirpAuthError):
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err

        if self.consecutive_errors:
            _LOGGER.info("Chirp updates recovered")
        self.consecutive_errors = 0
        self._reauth_started = False
        self.last_success_at = dt_util.utcnow().isoformat()
        return status
