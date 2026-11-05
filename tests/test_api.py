"""Tests for the API client and models."""

from __future__ import annotations

from datetime import date
from typing import Any

import aiohttp
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.vue_cinemas.api import (
    VueCinemasClient,
    VueCinemasConnectionError,
    VueCinemasResponseError,
    parse_film_details,
    token_expiry,
)
from custom_components.vue_cinemas.const import BASE_URL
from custom_components.vue_cinemas.models import Certificate, FilmDetails

from .conftest import (
    CINEMAS_URL,
    FILMS_URL,
    TOKEN_URL,
    film_page,
    load,
    make_token,
    mock_token,
)



async def test_cinemas(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Cinemas are flattened and sorted by name."""
    mock_token(aioclient_mock)
    aioclient_mock.get(CINEMAS_URL, json=load("cinemas.json"))
    cinemas = await VueCinemasClient(async_get_clientsession(hass)).async_get_cinemas()
    assert [c.name for c in cinemas] == ["Alkmaar", "Amersfoort", "Deventer"]
    assert cinemas[1].cinema_id == "1001"
    assert cinemas[1].whats_on_url.endswith("/amersfoort/nu-in-de-bioscoop")


async def test_films(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Films parse with sorted sessions, prices, attributes and certificates."""
    mock_token(aioclient_mock)
    aioclient_mock.get(FILMS_URL, json=load("films.json"))
    films = await VueCinemasClient(async_get_clientsession(hass)).async_get_films("1001")
    assert aioclient_mock.mock_calls[1][3]["Authorization"] == f"Bearer {make_token()}"
    assert aioclient_mock.mock_calls[1][1].query == {
        "minEmbargoLevel": "1",
        "includeSessionAttributes": "true",
    }
    clay = films[0]
    assert clay.slug == "clayface"
    assert clay.release_date == date(2026, 10, 22)
    assert clay.certificate == Certificate("16", clay.certificate.image_url)  # type: ignore[union-attr]
    assert [c.name for c in clay.content_descriptors] == ["Angst", "Geweld"]
    session = clay.sessions[1]
    assert session.screen == "Zaal 1"
    assert session.start.isoformat() == "2026-11-06T19:00:00+01:00"
    assert session.end.isoformat() == "2026-11-06T21:19:00+01:00"
    assert session.price == "€ 10,00"
    assert session.booking_url == f"{BASE_URL}/kopen/overzicht/1001/HO00000506/13210"
    # The internal "Singleseatrule" attribute is dropped.
    assert [a.name for a in session.attributes] == ["Netherlands", "D-Box", "Dolby Atmos"]
    wen = films[1]
    assert [s.start.strftime("%H:%M") for s in wen.sessions][:2] == ["10:30", "14:00"]
    spirited = films[2]
    assert spirited.film_attributes[0].description.startswith("Jouw favoriete manga’s")
    jumanji = films[4]
    assert jumanji.is_coming_soon
    assert jumanji.certificate is not None and jumanji.certificate.name == "tbc"
    assert not films[0].is_coming_soon


async def test_film_details(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Genres, long synopsis and trailer come from the film page."""
    aioclient_mock.get(f"{BASE_URL}/film/clayface", text=film_page())
    details = await VueCinemasClient(
        async_get_clientsession(hass)
    ).async_get_film_details("clayface")
    assert details.genres == ["Horror", "Thriller"]
    assert details.long_synopsis == "Een langere beschrijving met ë entiteit."
    assert details.trailer_url == (
        "https://customer-s5ao6f6rq71kswao.cloudflarestream.com/"
        "deda75ed966fe5b239762c3cc2f43220/iframe"
    )
    restored = FilmDetails.from_dict(details.as_dict())
    assert restored == details


def test_details_without_optional_fields() -> None:
    """Missing Sitecore fields give empty values, not errors."""
    details = parse_film_details({"genres": {"targetItems": [{"genreName": {}}]}})
    assert details.genres == []
    assert details.long_synopsis == ""
    assert details.trailer_url == ""
    assert FilmDetails.from_dict({}).fetched is None


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"exc": aiohttp.ClientError()}, VueCinemasConnectionError),
        ({"exc": TimeoutError()}, VueCinemasConnectionError),
        ({"status": 500, "text": "oops"}, VueCinemasResponseError),
        ({"text": "not json"}, VueCinemasResponseError),
        ({"json": {"responseCode": 1, "result": None}}, VueCinemasResponseError),
        ({"json": {"responseCode": 0, "result": {}}}, VueCinemasResponseError),
    ],
)
async def test_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict[str, Any],
    error: type[Exception],
) -> None:
    """Transport and payload problems raise typed errors."""
    mock_token(aioclient_mock)
    aioclient_mock.get(CINEMAS_URL, **kwargs)
    aioclient_mock.get(FILMS_URL, **kwargs)
    client = VueCinemasClient(async_get_clientsession(hass))
    with pytest.raises(error):
        await client.async_get_cinemas()
    with pytest.raises(error):
        await client.async_get_films("1001")


@pytest.mark.parametrize(
    "page",
    [
        "<html>no data</html>",
        '<script id="__NEXT_DATA__" type="application/json">{"props": {}}</script>',
        '<script id="__NEXT_DATA__" type="application/json">{broken</script>',
    ],
)
async def test_details_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, page: str
) -> None:
    """A film page without usable data raises."""
    aioclient_mock.get(f"{BASE_URL}/film/x", text=page)
    with pytest.raises(VueCinemasResponseError):
        await VueCinemasClient(async_get_clientsession(hass)).async_get_film_details("x")


async def test_token_reused_and_renewed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: Any
) -> None:
    """One token serves many calls until it nears expiry."""
    mock_token(aioclient_mock)
    aioclient_mock.get(CINEMAS_URL, json=load("cinemas.json"))
    client = VueCinemasClient(async_get_clientsession(hass))
    await client.async_get_cinemas()
    await client.async_get_cinemas()
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert len(posts) == 1
    freezer.move_to("2026-11-06T02:55:00+00:00")
    await client.async_get_cinemas()
    assert len([c for c in aioclient_mock.mock_calls if c[0] == "POST"]) == 2


async def test_401_gets_new_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A rejected token is replaced once, then the call is retried."""
    calls = 0

    async def films(method: str, url: Any, data: Any) -> Any:
        nonlocal calls
        calls += 1
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        if calls == 1:
            return AiohttpClientMockResponse(method, url, status=401, text="")
        return AiohttpClientMockResponse(method, url, json=load("films.json"))

    mock_token(aioclient_mock)
    aioclient_mock.get(FILMS_URL, side_effect=films)
    films_list = await VueCinemasClient(async_get_clientsession(hass)).async_get_films("1001")
    assert len(films_list) == 5
    assert len([c for c in aioclient_mock.mock_calls if c[0] == "POST"]) == 2


async def test_token_failures(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No token cookie, or a refused token request, is an error."""
    aioclient_mock.post(TOKEN_URL, json={"result": {}, "responseCode": 0})
    with pytest.raises(VueCinemasResponseError):
        await VueCinemasClient(async_get_clientsession(hass)).async_get_cinemas()
    aioclient_mock.clear_requests()
    aioclient_mock.post(TOKEN_URL, status=500, cookies={"microservicesToken": "x"})
    with pytest.raises(VueCinemasResponseError):
        await VueCinemasClient(async_get_clientsession(hass)).async_get_cinemas()


async def test_opaque_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A token without a readable expiry is used for an hour."""
    mock_token(aioclient_mock, token="not-a-jwt")
    aioclient_mock.get(CINEMAS_URL, json=load("cinemas.json"))
    assert token_expiry("not-a-jwt") is None
    await VueCinemasClient(async_get_clientsession(hass)).async_get_cinemas()
    assert aioclient_mock.mock_calls[1][3]["Authorization"] == "Bearer not-a-jwt"
