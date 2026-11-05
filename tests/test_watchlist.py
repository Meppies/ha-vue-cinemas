"""Tests for watchlist filtering."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from custom_components.vue_cinemas.config_flow import DEFAULT_WATCHLIST
from custom_components.vue_cinemas.coordinator import CinemaData
from custom_components.vue_cinemas.models import Certificate, Film, FilmDetails
from custom_components.vue_cinemas.watchlist import (
    Watchlist,
    certificate_allowed,
    select_coming_soon,
    select_showings,
)

from .conftest import NOW, load

GENRES = {
    "HO00000506": ["Horror", "Thriller"],
    "HO00000178": ["Family"],
    "HO00000598": ["Animation"],
    "HO00000321": ["Action"],
}


def data(with_genres: bool = True) -> CinemaData:
    """Cinema data built from the fixture."""
    films = [Film.from_api(raw) for raw in load("films.json")["result"]]
    details = (
        {fid: FilmDetails(genres=g) for fid, g in GENRES.items()} if with_genres else {}
    )
    return CinemaData(films=films, details=details, fetched=datetime.fromisoformat(NOW))


def titles(**options: Any) -> list[tuple[str, str]]:
    """Return (start HH:MM day, title) for a watchlist."""
    watchlist = Watchlist.from_data({**DEFAULT_WATCHLIST, **options})
    return [
        (s.session.start.strftime("%d %H:%M"), s.film.title)
        for s in select_showings(data(), watchlist, datetime.fromisoformat(NOW))
    ]


def test_default_watchlist() -> None:
    """Now showing, 7 days: running and upcoming showings in time order."""
    assert titles() == [
        ("05 10:30", "Wen Er Maar Aan"),  # running, ends 12:25
        ("05 14:00", "Wen Er Maar Aan"),
        ("05 21:30", "Clayface"),
        ("06 19:00", "Clayface"),
        ("06 20:00", "Spirited Away"),
    ]


def test_window_and_mode() -> None:
    """Days ahead bounds the window; mode 'all' adds pre-sales."""
    assert titles(days_ahead=0) == [
        ("05 10:30", "Wen Er Maar Aan"),
        ("05 14:00", "Wen Er Maar Aan"),
        ("05 21:30", "Clayface"),
    ]
    assert ("20 16:00", "Wen Er Maar Aan") in titles(days_ahead=15)
    assert ("16 09:00", "Avengers: Doomsday") not in titles(days_ahead=45)
    assert ("16 09:00", "Avengers: Doomsday") in titles(days_ahead=45, mode="all")


def test_filters() -> None:
    """Screen, feature, genre, age and sold-out filters."""
    assert titles(screens=["Zaal 1"]) == [("06 19:00", "Clayface")]
    assert titles(attributes=["D-Box", "Vue Anime"]) == [
        ("06 19:00", "Clayface"),
        ("06 20:00", "Spirited Away"),
    ]
    assert {t for _, t in titles(genres=["Horror"])} == {"Clayface"}
    assert {t for _, t in titles(max_certificate="9")} == {
        "Wen Er Maar Aan",
        "Spirited Away",
    }
    assert ("05 10:30", "Wen Er Maar Aan") not in titles(hide_sold_out=True)


def test_genre_filter_without_genres() -> None:
    """Without scraped genres a genre filter matches nothing."""
    watchlist = Watchlist.from_data({**DEFAULT_WATCHLIST, "genres": ["Horror"]})
    now = datetime.fromisoformat(NOW)
    assert select_showings(data(with_genres=False), watchlist, now) == []
    assert select_coming_soon(data(with_genres=False), watchlist, now) == []


def test_coming_soon() -> None:
    """Coming soon lists films without sessions, and respects filters."""
    now = datetime.fromisoformat(NOW)
    base = {**DEFAULT_WATCHLIST, "include_coming_soon": True}
    soon = select_coming_soon(data(), Watchlist.from_data(base), now)
    assert [f.title for f in soon] == ["Jumanji: Open World"]
    off = Watchlist.from_data({**base, "include_coming_soon": False})
    assert select_coming_soon(data(), off, now) == []
    horror = Watchlist.from_data({**base, "genres": ["Horror"]})
    assert select_coming_soon(data(), horror, now) == []


@pytest.mark.parametrize(
    ("name", "maximum", "allowed"),
    [
        ("16", "12", False),
        ("12", "12", True),
        ("AL", "6", True),
        ("tbc", "6", True),
        (None, "6", True),
        ("18", "any", True),
        ("18", "bogus", True),
    ],
)
def test_certificate_allowed(name: str | None, maximum: str, allowed: bool) -> None:
    """Kijkwijzer comparison."""
    cert = Certificate(name, "") if name else None
    assert certificate_allowed(cert, maximum) is allowed


def test_from_data_defaults() -> None:
    """Missing keys fall back to defaults."""
    watchlist = Watchlist.from_data({})
    assert watchlist.mode == "now_showing"
    assert watchlist.days_ahead == 7
    assert not watchlist.screens
