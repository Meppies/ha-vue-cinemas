"""Tests for setup, unload, the card, repairs and the details cache."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    flush_store,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.vue_cinemas.config_flow import DEFAULT_WATCHLIST
from custom_components.vue_cinemas.const import (
    CARD_URL,
    DOMAIN,
    STORAGE_KEY,
    SUBENTRY_WATCHLIST,
)
from custom_components.vue_cinemas.coordinator import get_details_cache

from .conftest import FILMS_URL, load, mock_api, watchlist

ISSUE = "genres_unavailable_{}"


async def test_setup_and_unload(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """The entry loads, creates entities and unloads cleanly."""
    assert setup_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.vue_amersfoort_alles_showings") is not None
    assert hass.states.get("calendar.vue_amersfoort_alles_programme") is not None
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    assert setup_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failing API retries setup later."""
    aioclient_mock.get(FILMS_URL, status=500, text="down")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unavailable_and_recovery(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities go unavailable on failure and come back."""
    entity = "sensor.vue_amersfoort_alles_showings"
    aioclient_mock.clear_requests()
    aioclient_mock.get(FILMS_URL, status=500, text="down")
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity).state == "unavailable"
    aioclient_mock.clear_requests()
    mock_api(aioclient_mock)
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity).state != "unavailable"


async def test_watchlist_added_reloads(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Adding and removing a watchlist adds and removes its entities."""
    hass.config_entries.async_add_subentry(
        setup_entry,
        ConfigSubentry(
            subentry_type=SUBENTRY_WATCHLIST,
            title="3D",
            data={**DEFAULT_WATCHLIST, "attributes": ["3D"]},
            unique_id=None,
        ),
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.vue_amersfoort_3d_showings") is not None
    sub_id = next(s.subentry_id for s in setup_entry.subentries.values() if s.title == "3D")
    hass.config_entries.async_remove_subentry(setup_entry, sub_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.vue_amersfoort_3d_showings") is None


@pytest.mark.parametrize("subentries", [[watchlist("Horror", genres=["Horror"])]])
async def test_genre_repair_issue(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    issue_registry: ir.IssueRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Unreadable genres raise a repair issue that clears once they return."""
    mock_api(aioclient_mock, pages=False)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    issue = issue_registry.async_get_issue(DOMAIN, ISSUE.format(config_entry.entry_id))
    assert issue is not None
    assert issue.translation_placeholders == {"cinema": "Amersfoort", "watchlists": "Horror"}

    aioclient_mock.clear_requests()
    mock_api(aioclient_mock)
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert issue_registry.async_get_issue(DOMAIN, ISSUE.format(config_entry.entry_id)) is None


@pytest.mark.parametrize("subentries", [[watchlist("Horror", genres=["Horror"])]])
async def test_repair_issue_removed_on_unload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Unloading removes the issue."""
    mock_api(aioclient_mock, pages=False)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, ISSUE.format(config_entry.entry_id)) is None


async def test_details_cached(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Film pages are fetched once, persisted, and refreshed after a week."""
    pages = [c for c in aioclient_mock.mock_calls if "/film/" in str(c[1])]
    assert len(pages) == 5
    cache = get_details_cache(hass)
    assert cache.get("clayface") is not None
    await flush_store(cache._store)  # noqa: SLF001
    assert "clayface" in hass_storage[STORAGE_KEY]["data"]

    aioclient_mock.clear_requests()
    mock_api(aioclient_mock)
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not [c for c in aioclient_mock.mock_calls if "/film/" in str(c[1])]

    freezer.tick(timedelta(days=8))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len([c for c in aioclient_mock.mock_calls if "/film/" in str(c[1])]) == 5


async def test_details_loaded_from_storage(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
) -> None:
    """Fresh stored details are not fetched again after a restart."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {
            slug: {
                "genres": ["Drama"],
                "long_synopsis": "",
                "trailer_url": "",
                "fetched": "2026-11-05T10:00:00+00:00",
            }
            for slug in ("clayface", "wen-er-maar-aan", "spirited-away", "avengers-doomsday", "jumanji-open-world")
        },
    }
    mock_api(aioclient_mock)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert not [c for c in aioclient_mock.mock_calls if "/film/" in str(c[1])]
    assert config_entry.runtime_data.data.genres == ["Drama"]


async def test_card_served(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """The card is served by the integration."""
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    assert "vue-cinemas-card" in await response.text()


async def test_card_registered_with_frontend(
    hass: HomeAssistant, config_entry: MockConfigEntry, api: AiohttpClientMocker
) -> None:
    """When the frontend is loaded the card module is added to it."""
    hass.data["frontend_extra_module_url"] = set()
    assert await async_setup_component(hass, DOMAIN, {})
    assert any(url.startswith(CARD_URL) for url in hass.data["frontend_extra_module_url"])


async def test_films_payload_used(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Coordinator data reflects the fixture."""
    data = setup_entry.runtime_data.data
    assert len(data.films) == len(load("films.json")["result"])
    assert data.screens[0] == "Zaal 1"
    assert data.details_failed == 0
