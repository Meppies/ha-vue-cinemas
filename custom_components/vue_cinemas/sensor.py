"""Sensors for Vue Cinemas watchlists."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import SUBENTRY_WATCHLIST
from .coordinator import VueCinemasConfigEntry
from .entity import VueWatchlistEntity
from .watchlist import Showing

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VueCinemasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for every watchlist."""
    coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_WATCHLIST:
            continue
        async_add_entities(
            [
                VueNextShowingSensor(coordinator, subentry, "next_showing"),
                VueShowingCountSensor(coordinator, subentry, "showings"),
            ],
            config_subentry_id=subentry.subentry_id,
        )


class _TimedWatchlistSensor(VueWatchlistEntity, SensorEntity):
    """A watchlist sensor that re-evaluates when the next showing starts."""

    _unsub_timer: CALLBACK_TYPE | None = None

    def _upcoming(self, now: datetime) -> list[Showing]:
        return [s for s in self.showings(now) if s.session.start > now]

    @callback
    def _schedule(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        if not self.coordinator.data:
            return
        now = dt_util.now()
        upcoming = self._upcoming(now)
        if upcoming:
            self._unsub_timer = async_track_point_in_utc_time(
                self.hass, self._handle_timer, upcoming[0].session.start
            )

    @callback
    def _handle_timer(self, _now: datetime) -> None:
        self._unsub_timer = None
        self.async_write_ha_state()
        self._schedule()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Start the timer once added."""
        await super().async_added_to_hass()
        self._schedule()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the timer."""
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        await super().async_will_remove_from_hass()


class VueNextShowingSensor(_TimedWatchlistSensor):
    """Start time of the next matching showing."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _unrecorded_attributes = frozenset(
        {"poster", "booking_url", "film_id", "session_id"}
    )

    def _next(self) -> Showing | None:
        upcoming = self._upcoming(dt_util.now())
        return upcoming[0] if upcoming else None

    @property
    def native_value(self) -> datetime | None:
        """Return the start of the next showing."""
        showing = self._next()
        return showing.session.start if showing else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Describe the next showing."""
        showing = self._next()
        if showing is None:
            return None
        return {
            "film": showing.film.title,
            "screen": showing.session.screen,
            "end": showing.session.end.isoformat(),
            "attributes": [a.short_name or a.name for a in showing.session.attributes],
            "film_id": showing.film.film_id,
            "session_id": showing.session.session_id,
            "poster": showing.film.poster_url,
            "booking_url": showing.session.booking_url,
        }


class VueShowingCountSensor(_TimedWatchlistSensor):
    """Number of matching showings in the watchlist window."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        """Return the number of upcoming showings."""
        return len(self._upcoming(dt_util.now()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the number of distinct films."""
        return {"films": len({s.film.film_id for s in self._upcoming(dt_util.now())})}
