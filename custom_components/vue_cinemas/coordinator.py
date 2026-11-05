"""Data update coordinator for one Vue cinema."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import VueCinemasClient, VueCinemasError
from .const import (
    CONF_CINEMA_ID,
    DETAILS_CONCURRENCY,
    DETAILS_MAX_AGE,
    DOMAIN,
    LOGGER,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .models import Film, FilmDetails

type VueCinemasConfigEntry = ConfigEntry[VueCinemasCoordinator]


@dataclass(slots=True)
class CinemaData:
    """Everything known about one cinema's programme."""

    films: list[Film]
    details: dict[str, FilmDetails]
    fetched: datetime
    details_failed: int = 0
    screens: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)


class FilmDetailsCache:
    """Film page details shared by every cinema, persisted between restarts."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the cache."""
        self._store: Store[dict[str, dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._data: dict[str, FilmDetails] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load from disk once."""
        async with self._lock:
            if self._loaded:
                return
            stored = await self._store.async_load() or {}
            self._data = {
                slug: FilmDetails.from_dict(raw) for slug, raw in stored.items()
            }
            self._loaded = True

    def get(self, slug: str) -> FilmDetails | None:
        """Return cached details for a film slug."""
        return self._data.get(slug)

    def is_fresh(self, slug: str, now: datetime) -> bool:
        """True when cached details are younger than the maximum age."""
        details = self._data.get(slug)
        return bool(details and details.fetched and now - details.fetched < DETAILS_MAX_AGE)

    def set(self, slug: str, details: FilmDetails) -> None:
        """Store details and schedule a save."""
        self._data[slug] = details
        self._store.async_delay_save(self._serialise, 30)

    def _serialise(self) -> dict[str, dict[str, Any]]:
        return {slug: details.as_dict() for slug, details in self._data.items()}


def get_details_cache(hass: HomeAssistant) -> FilmDetailsCache:
    """Return the integration-wide details cache."""
    cache: FilmDetailsCache | None = hass.data.get(DOMAIN)
    if cache is None:
        cache = hass.data[DOMAIN] = FilmDetailsCache(hass)
    return cache


class VueCinemasCoordinator(DataUpdateCoordinator[CinemaData]):
    """Fetches the programme of one cinema."""

    config_entry: VueCinemasConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VueCinemasConfigEntry,
        client: VueCinemasClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_CINEMA_ID]}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.cinema_id: str = entry.data[CONF_CINEMA_ID]
        self.details_cache = get_details_cache(hass)

    async def _async_setup(self) -> None:
        """Load the details cache before the first refresh."""
        await self.details_cache.async_load()

    async def _async_update_data(self) -> CinemaData:
        """Fetch films and sessions, then enrich with film page details."""
        try:
            films = await self.client.async_get_films(self.cinema_id)
        except VueCinemasError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        failed = await self._async_refresh_details(films)
        details = {
            film.film_id: d
            for film in films
            if (d := self.details_cache.get(film.slug)) is not None
        }
        return CinemaData(
            films=films,
            details=details,
            fetched=dt_util.utcnow(),
            details_failed=failed,
            screens=_sorted_screens({s.screen for f in films for s in f.sessions}),
            attributes=sorted(
                {a.name for f in films for s in f.sessions for a in s.attributes}
                | {a.name for f in films for a in f.film_attributes},
                key=str.casefold,
            ),
            genres=sorted(
                {g for d in details.values() for g in d.genres}, key=str.casefold
            ),
        )

    async def _async_refresh_details(self, films: list[Film]) -> int:
        """Fetch missing or stale film page details; return the failure count.

        Details are best effort: a failure keeps any older cached copy and
        never fails the update itself.
        """
        now = dt_util.utcnow()
        slugs = sorted(
            {
                f.slug
                for f in films
                if f.slug and not self.details_cache.is_fresh(f.slug, now)
            }
        )
        if not slugs:
            return 0
        semaphore = asyncio.Semaphore(DETAILS_CONCURRENCY)

        async def fetch(slug: str) -> bool:
            async with semaphore:
                try:
                    details = await self.client.async_get_film_details(slug)
                except VueCinemasError as err:
                    LOGGER.debug("Details for %s unavailable: %s", slug, err)
                    return False
                self.details_cache.set(slug, details)
                return True

        results = await asyncio.gather(*(fetch(slug) for slug in slugs))
        return results.count(False)


def _sorted_screens(screens: set[str]) -> list[str]:
    """Sort 'Zaal 2' before 'Zaal 10'."""

    def key(name: str) -> tuple[int, str]:
        digits = "".join(ch for ch in name if ch.isdigit())
        return (int(digits) if digits else 0, name.casefold())

    return sorted((s for s in screens if s), key=key)
