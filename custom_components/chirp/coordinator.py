"""Poll the Chirp server for host and disk status."""

from __future__ import annotations

import asyncio
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
    REFRESH_POLL_INTERVAL,
    REFRESH_POLL_MAX_ATTEMPTS,
    UNAVAILABLE_AFTER_FAILURES,
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
    """Fetch ``/api/v1/status``; ride out brief outages with the last snapshot.

    Up to ``UNAVAILABLE_AFTER_FAILURES - 1`` failed polls in a row return the
    cached snapshot so entities keep their values. The next failure raises
    ``UpdateFailed``: ``last_update_success`` turns false and every
    ``CoordinatorEntity`` becomes unavailable until a poll succeeds again.
    """

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
        self._follow_task: asyncio.Task[None] | None = None
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

    def disk_read_marks(self) -> dict[str, Any]:
        """Return each disk's ``lastReadAt`` to detect a finished SMART read."""
        return {
            disk.get("id"): disk.get("lastReadAt")
            for disk in (self.data or {}).get("disks", [])
        }

    async def async_follow_smart_refresh(self) -> None:
        """Re-poll after a queued SMART read until its results have landed.

        Chirp answers ``POST /refresh`` with 202 and reads the disks in the
        background, so one immediate poll still shows the previous values. Poll
        a few times with a short delay and stop once the ``lastReadAt`` values
        have changed and stayed the same for one more poll (all disks done), or
        when the attempt limit is reached.
        """
        before = previous = self.disk_read_marks()
        for _ in range(REFRESH_POLL_MAX_ATTEMPTS):
            await asyncio.sleep(REFRESH_POLL_INTERVAL)
            await self.async_refresh()
            if not self.last_update_success:
                return
            current = self.disk_read_marks()
            if current != before and current == previous:
                return
            previous = current

    def async_start_smart_refresh_follow(self) -> None:
        """Start (or restart) the background poll after a queued SMART read."""
        if self._follow_task is not None and not self._follow_task.done():
            self._follow_task.cancel()
        self._follow_task = self._entry.async_create_background_task(
            self.hass,
            self.async_follow_smart_refresh(),
            f"{DOMAIN} follow SMART refresh",
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.api.async_get_status()
            expected = self._entry.unique_id
            if expected and str(status["instance"]["id"]) != expected:
                # Another Chirp server now answers at this address (DHCP change or
                # reinstall). Its data must not be filed under this entry's IDs.
                raise ChirpInstanceMismatchError(
                    "A different Chirp instance answered at the configured address"
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
            if isinstance(err, ChirpAuthError):
                # A rejected key does not heal by itself: Home Assistant starts
                # the reauth flow and marks the entities unavailable.
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="invalid_auth"
                ) from err
            if (
                self.data is not None
                and self.consecutive_errors < UNAVAILABLE_AFTER_FAILURES
            ):
                # Ride out brief outages with the last good snapshot.
                return self.data
            if isinstance(err, ChirpInstanceMismatchError):
                raise UpdateFailed(
                    translation_domain=DOMAIN, translation_key="wrong_instance"
                ) from err
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": self.last_error},
            ) from err

        if self.consecutive_errors:
            _LOGGER.info("Chirp updates recovered")
        self.consecutive_errors = 0
        self.last_success_at = dt_util.utcnow().isoformat()
        return status
