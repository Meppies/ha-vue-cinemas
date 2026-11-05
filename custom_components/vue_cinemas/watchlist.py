"""Watchlist filtering: turn a cinema programme into the showings one list wants."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .const import (
    CERTIFICATE_ANY,
    CERTIFICATES,
    CONF_ATTRIBUTES,
    CONF_DAYS_AHEAD,
    CONF_GENRES,
    CONF_HIDE_SOLD_OUT,
    CONF_INCLUDE_COMING_SOON,
    CONF_MAX_CERTIFICATE,
    CONF_MODE,
    CONF_SCREENS,
    DEFAULT_DAYS_AHEAD,
    MAX_DAYS_AHEAD,
    MODE_NOW_SHOWING,
)
from .coordinator import CinemaData
from .models import Attribute, Certificate, Film, FilmDetails, Session


@dataclass(frozen=True, slots=True)
class Watchlist:
    """The filter settings of one watchlist subentry."""

    mode: str
    days_ahead: int
    screens: frozenset[str]
    genres: frozenset[str]
    attributes: frozenset[str]
    max_certificate: str
    hide_sold_out: bool
    include_coming_soon: bool

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> Watchlist:
        """Build from subentry data, tolerating missing keys."""
        return cls(
            mode=str(data.get(CONF_MODE, MODE_NOW_SHOWING)),
            days_ahead=int(data.get(CONF_DAYS_AHEAD, DEFAULT_DAYS_AHEAD)),
            screens=frozenset(data.get(CONF_SCREENS) or ()),
            genres=frozenset(data.get(CONF_GENRES) or ()),
            attributes=frozenset(data.get(CONF_ATTRIBUTES) or ()),
            max_certificate=str(data.get(CONF_MAX_CERTIFICATE, CERTIFICATE_ANY)),
            hide_sold_out=bool(data.get(CONF_HIDE_SOLD_OUT, False)),
            include_coming_soon=bool(data.get(CONF_INCLUDE_COMING_SOON, False)),
        )


@dataclass(frozen=True, slots=True)
class Showing:
    """One session of one film, as selected by a watchlist."""

    film: Film
    session: Session
    details: FilmDetails | None


def certificate_allowed(certificate: Certificate | None, maximum: str) -> bool:
    """True when the film's Kijkwijzer age is at or below the maximum.

    Films without a known classification ("tbc") are allowed: hiding them
    would hide most premières.
    """
    if maximum == CERTIFICATE_ANY or maximum not in CERTIFICATES:
        return True
    name = certificate.name.casefold() if certificate else ""
    if name not in CERTIFICATES:
        return True
    return CERTIFICATES.index(name) <= CERTIFICATES.index(maximum)


def _film_matches(
    film: Film, details: FilmDetails | None, watchlist: Watchlist, today: datetime
) -> bool:
    if watchlist.mode == MODE_NOW_SHOWING and (
        film.release_date is None or film.release_date > today.date()
    ):
        return False
    if not certificate_allowed(film.certificate, watchlist.max_certificate):
        return False
    if watchlist.genres:
        genres = set(details.genres) if details else set()
        if not genres & watchlist.genres:
            return False
    return True


def _session_matches(
    session: Session,
    film_attributes: tuple[Attribute, ...],
    watchlist: Watchlist,
    now: datetime,
    until: datetime,
) -> bool:
    if session.end <= now or session.start >= until:
        return False
    if watchlist.hide_sold_out and session.sold_out:
        return False
    if watchlist.screens and session.screen not in watchlist.screens:
        return False
    if watchlist.attributes:
        names = {a.name for a in session.attributes} | {a.name for a in film_attributes}
        if not names & watchlist.attributes:
            return False
    return True


def select_showings(
    data: CinemaData, watchlist: Watchlist, now: datetime
) -> list[Showing]:
    """Return the matching showings, earliest first.

    A showing that has started but not ended is kept, so the card can show
    what is on right now. The window ends at midnight `days_ahead` days out.
    """
    local_now = now
    until = (local_now + timedelta(days=watchlist.days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    showings: list[Showing] = []
    for film in data.films:
        details = data.details.get(film.film_id)
        if not film.sessions or not _film_matches(film, details, watchlist, local_now):
            continue
        showings.extend(
            Showing(film, session, details)
            for session in film.sessions
            if _session_matches(session, film.film_attributes, watchlist, now, until)
        )
    return sorted(showings, key=lambda s: (s.session.start, s.film.title.casefold()))


def select_coming_soon(
    data: CinemaData, watchlist: Watchlist, now: datetime
) -> list[Film]:
    """Return announced films without sessions, by release date.

    Only films with a known release date within the next 90 days are listed;
    Vue announces films up to a year ahead.
    """
    if not watchlist.include_coming_soon:
        return []
    horizon = now.date() + timedelta(days=MAX_DAYS_AHEAD)
    films = [
        f
        for f in data.films
        if f.is_coming_soon
        and f.release_date is not None
        and f.release_date <= horizon
        and certificate_allowed(f.certificate, watchlist.max_certificate)
        and (
            not watchlist.genres
            or set((d.genres if (d := data.details.get(f.film_id)) else []))
            & watchlist.genres
        )
    ]
    return sorted(
        films,
        key=lambda f: (f.release_date or horizon, f.title.casefold()),
    )
