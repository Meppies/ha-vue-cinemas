"""Calendar of the showings in a Vue Cinemas watchlist."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_CINEMA_NAME, MAX_DAYS_AHEAD, SUBENTRY_WATCHLIST
from .coordinator import VueCinemasConfigEntry
from .entity import VueWatchlistEntity
from .watchlist import Showing, select_showings

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VueCinemasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a calendar for every watchlist."""
    coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_WATCHLIST:
            continue
        async_add_entities(
            [VueWatchlistCalendar(coordinator, subentry, "calendar")],
            config_subentry_id=subentry.subentry_id,
        )


class VueWatchlistCalendar(VueWatchlistEntity, CalendarEntity):
    """Showings as calendar events."""

    def _event(self, showing: Showing) -> CalendarEvent:
        session = showing.session
        extras = ", ".join(a.short_name or a.name for a in session.attributes)
        description = "\n".join(
            line
            for line in (
                showing.film.synopsis,
                extras,
                session.price,
                session.booking_url,
            )
            if line
        )
        return CalendarEvent(
            start=session.start,
            end=session.end,
            summary=f"{showing.film.title} ({session.screen})"
            if session.screen
            else showing.film.title,
            location=f"Vue {self.coordinator.config_entry.data[CONF_CINEMA_NAME]}",
            description=description,
            uid=f"{self.coordinator.cinema_id}-{session.session_id}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next showing."""
        showings = self.showings()
        return self._event(showings[0]) if showings else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return showings in a range; the day window is widened to the range."""
        watchlist = replace(self.watchlist, days_ahead=MAX_DAYS_AHEAD)
        now = dt_util.now()
        return [
            self._event(showing)
            for showing in select_showings(self.coordinator.data, watchlist, now)
            if showing.session.end > start_date and showing.session.start < end_date
        ]
