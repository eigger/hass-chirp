"""Button that asks Chirp to re-read SMART data now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ChirpConfigEntry
from .api import ChirpAuthError, ChirpError
from .const import DOMAIN
from .coordinator import ChirpCoordinator
from .entity import ChirpEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChirpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the refresh button."""
    async_add_entities([ChirpRefreshButton(entry.runtime_data.coordinator, entry)])


class ChirpRefreshButton(ChirpEntity, ButtonEntity):
    """Queue a SMART re-read on the server, then refresh the coordinator."""

    def __init__(self, coordinator: ChirpCoordinator, entry: ChirpConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            ButtonEntityDescription(
                key="refresh_smart", translation_key="refresh_smart"
            ),
        )

    async def async_press(self) -> None:
        """Request a SMART refresh; the server's cooldown (429) is not an error."""
        try:
            await self.coordinator.api.async_refresh()
        except ChirpAuthError:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="refresh_auth_failed"
            ) from None
        except ChirpError:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="refresh_failed"
            ) from None
        await self.coordinator.async_request_refresh()
