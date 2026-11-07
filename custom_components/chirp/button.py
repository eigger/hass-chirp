"""Per-disk button that asks Chirp to re-read SMART data now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ChirpConfigEntry
from .api import ChirpAuthError, ChirpError
from .const import DOMAIN
from .entity import (
    ChirpDiskEntity,
    disk_unique_id,
    is_provisional_disk,
    register_forget_device,
)
from .groups import selected_entities

PARALLEL_UPDATES = 1

REFRESH_DESCRIPTION = ButtonEntityDescription(
    key="refresh_smart",
    translation_key="refresh_smart",
    icon="mdi:database-refresh",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChirpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a refresh button on every disk, now and for disks that appear later."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        instance_id = coordinator.instance_id
        new: list[ButtonEntity] = []
        for disk in coordinator.data["disks"]:
            if is_provisional_disk(disk):
                continue
            unique_id = disk_unique_id(instance_id, disk["id"], REFRESH_DESCRIPTION.key)
            if unique_id not in known:
                known.add(unique_id)
                new.append(
                    ChirpRefreshButton(coordinator, entry, REFRESH_DESCRIPTION, disk)
                )
        if new:
            async_add_entities(selected_entities(entry, new))

    register_forget_device(entry, known, (REFRESH_DESCRIPTION.key,), ())
    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class ChirpRefreshButton(ChirpDiskEntity, ButtonEntity):
    """Queue a SMART re-read on the server, then follow it with polls.

    Chirp re-reads every disk in one pass (there is no per-disk refresh), so
    pressing the button on any disk refreshes all of them. Disks in standby
    are still not woken.
    """

    async def async_press(self) -> None:
        """Request a SMART refresh; the server's cooldown (429) is not an error.

        A queued read (202) finishes in the background on the server, so the
        coordinator follows it with a few delayed polls instead of reading the
        previous values right away. During the cooldown a read is already
        running or just finished, so one refresh is enough.
        """
        try:
            queued = await self.coordinator.api.async_refresh()
        except ChirpAuthError:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="refresh_auth_failed"
            ) from None
        except ChirpError:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="refresh_failed"
            ) from None
        if queued:
            self.coordinator.async_start_smart_refresh_follow()
        else:
            await self.coordinator.async_request_refresh()
