"""Base entity for Vue Cinemas watchlists."""

from __future__ import annotations

from datetime import datetime

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import BASE_URL, CONF_CINEMA_NAME, DOMAIN
from .coordinator import VueCinemasCoordinator
from .watchlist import Showing, Watchlist, select_showings


class VueWatchlistEntity(CoordinatorEntity[VueCinemasCoordinator]):
    """An entity that belongs to one watchlist subentry."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VueCinemasCoordinator,
        subentry: ConfigSubentry,
        key: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.subentry_id = subentry.subentry_id
        self.watchlist = Watchlist.from_data(subentry.data)
        self._attr_unique_id = f"{subentry.subentry_id}_{key}"
        self._attr_translation_key = key
        cinema = coordinator.config_entry.data[CONF_CINEMA_NAME]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=f"Vue {cinema} · {subentry.title}",
            manufacturer="Vue Cinemas",
            model=f"Watchlist {cinema}",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"{BASE_URL}/cinema",
        )

    def showings(self, now: datetime | None = None) -> list[Showing]:
        """Return this watchlist's showings."""
        return select_showings(
            self.coordinator.data, self.watchlist, now or dt_util.now()
        )
