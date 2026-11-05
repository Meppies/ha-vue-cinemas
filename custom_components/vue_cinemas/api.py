"""Async client for the (unofficial) Vue Cinemas Netherlands web API.

Vue publishes no documented API. This client uses the JSON endpoints that
www.vuecinemas.nl itself calls, plus the film page for the few fields the
JSON omits (genres, long synopsis, trailer). The HTTP session is injected
by Home Assistant.

Every API call needs an anonymous guest token. The site gets one with
`POST /auth/token`, which sets it as the `microservicesToken` cookie; the API
also accepts it as a bearer token, which keeps it out of Home Assistant's
shared cookie jar. Tokens last about twelve hours.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta
import html
import json
import re
from typing import Any

import aiohttp

from .const import API_URL, BASE_URL, REQUEST_TIMEOUT
from .models import Cinema, Film, FilmDetails

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_TOKEN_COOKIE = "microservicesToken"
_TOKEN_MARGIN = timedelta(minutes=10)
_TOKEN_FALLBACK_LIFETIME = timedelta(hours=1)
_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "nl-NL",
    "User-Agent": "HomeAssistant-VueCinemas/1.0 (+https://github.com/Meppies/ha-vue-cinemas)",
}


class VueCinemasError(Exception):
    """Base error."""


class VueCinemasConnectionError(VueCinemasError):
    """The API could not be reached or timed out."""


class VueCinemasResponseError(VueCinemasError):
    """The API answered with something we could not use."""


def token_expiry(token: str) -> datetime | None:
    """Read the `exp` claim of a JWT without verifying it."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(int(claims["exp"]), UTC)
    except (IndexError, ValueError, KeyError, TypeError):
        return None


class VueCinemasClient:
    """Client for www.vuecinemas.nl."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise with an injected aiohttp session."""
        self._session = session
        self._token: str | None = None
        self._token_expires = datetime.min.replace(tzinfo=UTC)
        self._token_lock = asyncio.Lock()

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        token: str | None = None,
    ) -> tuple[aiohttp.ClientResponse, str]:
        """Send a request and return the response with its body text."""
        headers = dict(_HEADERS)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.request(
                    method, url, params=params, headers=headers
                )
                text = await response.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VueCinemasConnectionError(str(err) or type(err).__name__) from err
        return response, text

    async def _get(self, url: str, params: dict[str, str] | None = None) -> str:
        """GET a public page and return the body text."""
        response, text = await self._request("GET", url, params)
        if response.status >= 400:
            raise VueCinemasResponseError(f"HTTP {response.status} for {url}")
        return text

    async def _async_token(self, stale: str | None = None) -> str:
        """Return a valid guest token, fetching a new one when needed.

        `stale` is a token the API just rejected; it is replaced even if it
        has not expired yet.
        """
        async with self._token_lock:
            now = datetime.now(UTC)
            if (
                self._token
                and self._token != stale
                and now < self._token_expires - _TOKEN_MARGIN
            ):
                return self._token
            response, _ = await self._request("POST", f"{API_URL}/auth/token")
            cookie = response.cookies.get(_TOKEN_COOKIE)
            if response.status >= 400 or cookie is None or not cookie.value:
                raise VueCinemasResponseError(
                    f"No guest token (HTTP {response.status})"
                )
            self._token = cookie.value
            self._token_expires = token_expiry(cookie.value) or (
                now + _TOKEN_FALLBACK_LIFETIME
            )
            return self._token

    async def _get_json(
        self, path: str, params: dict[str, str] | None = None
    ) -> Any:
        """GET an API path with the guest token and return its `result` member."""
        url = f"{API_URL}{path}"
        token = await self._async_token()
        response, text = await self._request("GET", url, params, token)
        if response.status == 401:
            token = await self._async_token(stale=token)
            response, text = await self._request("GET", url, params, token)
        if response.status >= 400:
            raise VueCinemasResponseError(f"HTTP {response.status} for {path}")
        try:
            payload = json.loads(text)
        except ValueError as err:
            raise VueCinemasResponseError(f"Invalid JSON from {path}") from err
        if not isinstance(payload, dict) or payload.get("responseCode", 0) != 0:
            raise VueCinemasResponseError(f"Unexpected response from {path}")
        return payload.get("result")

    async def async_get_cinemas(self) -> list[Cinema]:
        """Return all cinemas, sorted by name."""
        result = await self._get_json("/showings/cinemas")
        if not isinstance(result, list):
            raise VueCinemasResponseError("Cinema list missing")
        cinemas = [
            Cinema.from_api(item)
            for group in result
            for item in group.get("cinemas") or []
        ]
        return sorted(cinemas, key=lambda c: c.name.casefold())

    async def async_get_films(self, cinema_id: str) -> list[Film]:
        """Return all films with all sessions for one cinema."""
        result = await self._get_json(
            f"/showings/cinemas/{cinema_id}/films",
            {"minEmbargoLevel": "1", "includeSessionAttributes": "true"},
        )
        if not isinstance(result, list):
            raise VueCinemasResponseError("Film list missing")
        return [Film.from_api(item) for item in result]

    async def async_get_film_details(self, slug: str) -> FilmDetails:
        """Scrape genres, long synopsis and trailer from the film page."""
        page = await self._get(f"{BASE_URL}/film/{slug}")
        match = _NEXT_DATA.search(page)
        if match is None:
            raise VueCinemasResponseError(f"No page data for film {slug}")
        try:
            film: dict[str, Any] = json.loads(match.group(1))["props"]["pageProps"][
                "layoutData"
            ]["sitecore"]["context"]["film"]
        except (ValueError, KeyError, TypeError) as err:
            raise VueCinemasResponseError(f"Unexpected page data for {slug}") from err
        return parse_film_details(film)


def _value(node: Any, *keys: str) -> Any:
    """Walk nested Sitecore field objects, returning None on any gap."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def parse_film_details(film: dict[str, Any]) -> FilmDetails:
    """Parse the Sitecore `context.film` object."""
    genres = [
        str(name)
        for item in _value(film, "genres", "targetItems") or []
        if (name := _value(item, "genreName", "value"))
    ]
    uid = _value(
        film, "featuredTrailer", "targetItem", "streamVideo", "targetItem", "uid", "value"
    )
    hls = _value(
        film, "featuredTrailer", "targetItem", "streamVideo", "targetItem", "hls", "url"
    )
    trailer = ""
    if uid and isinstance(hls, str) and "/manifest/" in hls:
        trailer = f"{hls.split(str(uid))[0]}{uid}/iframe"
    return FilmDetails(
        genres=genres,
        long_synopsis=html.unescape(str(_value(film, "longSynopsis", "value") or "")),
        trailer_url=trailer,
        fetched=datetime.now(UTC),
    )
