"""Fixtures for Vue Cinemas tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.vue_cinemas.config_flow import DEFAULT_WATCHLIST
from custom_components.vue_cinemas.const import (
    API_URL,
    BASE_URL,
    CONF_CINEMA_ID,
    CONF_CINEMA_NAME,
    DOMAIN,
    SUBENTRY_WATCHLIST,
)

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN_URL = f"{API_URL}/auth/token"
CINEMAS_URL = f"{API_URL}/showings/cinemas"
FILMS_URL = f"{API_URL}/showings/cinemas/1001/films"
SEATS_URL = f"{API_URL}/booking/Session/1001/13210/seats"
SLUGS = [
    "clayface",
    "wen-er-maar-aan",
    "spirited-away",
    "avengers-doomsday",
    "jumanji-open-world",
]
NOW = "2026-11-05T12:00:00+01:00"


def make_token(exp: int = 1_793_934_000, jti: str = "a") -> str:
    """A JWT-shaped guest token; the default expires 2026-11-05 ~23:00 UTC."""
    body = base64.urlsafe_b64encode(
        json.dumps({"jti": jti, "exp": exp}).encode()
    ).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{body}.sig"


def load(name: str) -> Any:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def film_page() -> str:
    """The film page fixture."""
    return (FIXTURES / "film_page.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


@pytest.fixture(autouse=True)
async def amsterdam(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Run every test in Amsterdam at a fixed moment."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to(NOW)


def mock_token(aioclient_mock: AiohttpClientMocker, token: str | None = None) -> None:
    """Register the guest token endpoint."""
    aioclient_mock.post(
        TOKEN_URL,
        json={"result": {}, "responseCode": 0},
        cookies={"microservicesToken": token or make_token()},
    )


def mock_api(
    aioclient_mock: AiohttpClientMocker,
    *,
    films: Any = None,
    pages: bool = True,
) -> None:
    """Register the standard API responses."""
    mock_token(aioclient_mock)
    aioclient_mock.get(CINEMAS_URL, json=load("cinemas.json"))
    aioclient_mock.get(FILMS_URL, json=films if films is not None else load("films.json"))
    for slug in SLUGS:
        if pages:
            aioclient_mock.get(f"{BASE_URL}/film/{slug}", text=film_page())
        else:
            aioclient_mock.get(f"{BASE_URL}/film/{slug}", status=404, text="gone")


@pytest.fixture
def api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Standard API responses."""
    mock_api(aioclient_mock)
    return aioclient_mock


def watchlist(title: str = "Alles", **data: Any) -> ConfigSubentryData:
    """Build watchlist subentry data."""
    return ConfigSubentryData(
        subentry_type=SUBENTRY_WATCHLIST,
        title=title,
        data={**DEFAULT_WATCHLIST, **data},
        unique_id=None,
    )


@pytest.fixture
def subentries() -> list[ConfigSubentryData]:
    """Watchlists for the default entry."""
    return [watchlist()]


@pytest.fixture
def config_entry(subentries: list[ConfigSubentryData]) -> MockConfigEntry:
    """A Vue Amersfoort entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Vue Amersfoort",
        unique_id="1001",
        data={CONF_CINEMA_ID: "1001", CONF_CINEMA_NAME: "Amersfoort"},
        subentries_data=subentries,
    )


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, api: AiohttpClientMocker
) -> MockConfigEntry:
    """Set up the entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def subentry_id(entry: MockConfigEntry, title: str = "Alles") -> str:
    """Return the id of a watchlist by title."""
    return next(s.subentry_id for s in entry.subentries.values() if s.title == title)
