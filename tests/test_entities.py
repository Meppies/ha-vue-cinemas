"""Tests for sensors, calendar, websocket, action and diagnostics."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    WebSocketGenerator,
)

from custom_components.vue_cinemas.const import DOMAIN, SERVICE_GET_SHOWINGS
from custom_components.vue_cinemas.programme import get_programme

from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import SEATS_URL, load, subentry_id

NEXT = "sensor.vue_amersfoort_alles_next_showing"
COUNT = "sensor.vue_amersfoort_alles_showings"
CALENDAR = "calendar.vue_amersfoort_alles_programme"


async def test_sensors(
    hass: HomeAssistant, setup_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Next showing and count follow the clock."""
    state = hass.states.get(NEXT)
    assert state.state == "2026-11-05T13:00:00+00:00"
    assert state.attributes["film"] == "Wen Er Maar Aan"
    assert state.attributes["screen"] == "Zaal 2"
    assert state.attributes["booking_url"].endswith("/13100")
    count = hass.states.get(COUNT)
    assert count.state == "4"
    assert count.attributes["films"] == 3
    assert count.attributes["unit_of_measurement"] == "showings"

    # When the 14:00 showing starts, the sensors move on without a refresh.
    freezer.move_to("2026-11-05T14:00:01+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(NEXT).attributes["film"] == "Clayface"
    assert hass.states.get(COUNT).state == "3"


async def test_sensor_without_upcoming(
    hass: HomeAssistant, setup_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """After the last showing the next-showing sensor is unknown."""
    freezer.move_to("2026-11-30T12:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(NEXT)
    assert state.state == "unknown"
    assert "film" not in state.attributes
    assert hass.states.get(COUNT).state == "0"


async def test_calendar(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """The calendar shows the current showing and answers range queries."""
    state = hass.states.get(CALENDAR)
    assert state.state == "on"  # the 10:30 showing is still running
    assert state.attributes["message"] == "Wen Er Maar Aan (Zaal 2)"
    assert state.attributes["location"] == "Vue Amersfoort"

    client = await hass_client()
    response = await client.get(
        f"/api/calendars/{CALENDAR}?start=2026-11-06T00:00:00%2B01:00"
        "&end=2026-12-31T00:00:00%2B01:00"
    )
    events = await response.json()
    assert [e["summary"] for e in events] == [
        "Clayface (Zaal 1)",
        "Spirited Away (Zaal 4)",
        "Wen Er Maar Aan (Zaal 5)",
    ]
    assert "Dolby Atmos" in events[0]["description"]
    assert events[0]["uid"] == "1001-13210"


async def test_websocket(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """The card's websocket command returns the full programme."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "vue_cinemas/programme", "entity_id": COUNT})
    msg = await client.receive_json()
    assert msg["success"]
    result: dict[str, Any] = msg["result"]
    assert result["cinema"] == {"id": "1001", "name": "Amersfoort"}
    assert result["watchlist"]["name"] == "Alles"
    assert result["available"] is True
    assert [s["session_id"] for s in result["showings"]] == [
        "13101", "13100", "13204", "13210", "13300"
    ]
    assert result["coming_soon"] == ["HO00000321"]
    clay = result["films"]["HO00000506"]
    assert clay["genres"] == ["Horror", "Thriller"]
    assert clay["certificate"]["name"] == "16"
    assert [c["name"] for c in clay["content_descriptors"]] == ["Angst", "Geweld"]
    assert clay["trailer"].endswith("/iframe")
    assert result["films"]["HO00000598"]["film_attributes"][0]["name"] == "Vue Anime"
    sold = result["showings"][0]
    assert sold["sold_out"] is True
    assert sold["attributes"][0]["short_name"] == "NV"

    await client.send_json_auto_id(
        {"type": "vue_cinemas/programme", "entity_id": "sensor.nope"}
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_action(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """The get_showings action returns the same programme."""
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_SHOWINGS,
        {"entity_id": CALENDAR},
        blocking=True,
        return_response=True,
    )
    assert len(response["showings"]) == 5

    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"x": {}}})
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SHOWINGS,
            {"entity_id": "input_boolean.x"},
            blocking=True,
            return_response=True,
        )
    assert err.value.translation_key == "unknown_entity"


async def test_programme_errors(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Lookups by id fail with translated errors."""
    with pytest.raises(ServiceValidationError) as err:
        get_programme(hass, "missing", "x")
    assert err.value.translation_key == "unknown_entry"
    with pytest.raises(ServiceValidationError) as err:
        get_programme(hass, setup_entry.entry_id, "missing")
    assert err.value.translation_key == "unknown_watchlist"
    sub = subentry_id(setup_entry)
    assert get_programme(hass, setup_entry.entry_id, sub)["watchlist"]["id"] == sub
    await hass.config_entries.async_unload(setup_entry.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        get_programme(hass, setup_entry.entry_id, sub)
    assert err.value.translation_key == "entry_not_loaded"


async def test_entity_registry(
    hass: HomeAssistant, setup_entry: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Entities carry stable unique ids and their watchlist."""
    entry = entity_registry.async_get(COUNT)
    sub = subentry_id(setup_entry)
    assert entry.unique_id == f"{sub}_showings"
    assert entry.config_subentry_id == sub


async def test_diagnostics(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Diagnostics summarise the programme."""
    diag = await get_diagnostics_for_config_entry(hass, hass_client, setup_entry)
    assert diag["entry"]["data"]["cinema_id"] == "1001"
    assert diag["watchlists"][0]["title"] == "Alles"
    assert diag["programme"]["films"] == 5
    assert diag["programme"]["sessions"] == 7
    assert diag["programme"]["genres"] == ["Horror", "Thriller"]
    assert diag["coordinator"]["last_exception"] is None



async def test_websocket_seats(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The card fetches a seat plan on demand."""
    aioclient_mock.get(SEATS_URL, json=load("seats.json"))
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "vue_cinemas/seats", "entity_id": COUNT, "session_id": "13210"}
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["screen"] == "Zaal 1"
    assert len(msg["result"]["rows"]) == 4

    await client.send_json_auto_id(
        {"type": "vue_cinemas/seats", "entity_id": "sensor.nope", "session_id": "1"}
    )
    msg = await client.receive_json()
    assert msg["error"]["code"] == "not_found"

    aioclient_mock.clear_requests()
    aioclient_mock.get(SEATS_URL, status=500, text="down")
    await client.send_json_auto_id(
        {"type": "vue_cinemas/seats", "entity_id": COUNT, "session_id": "13210"}
    )
    msg = await client.receive_json()
    assert msg["error"]["code"] == "unavailable"
