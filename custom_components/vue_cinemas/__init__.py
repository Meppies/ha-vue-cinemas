"""The Vue Cinemas integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import VueCinemasClient
from .const import (
    CARD_FILENAME,
    CARD_URL,
    CONF_CINEMA_NAME,
    CONF_GENRES,
    DOMAIN,
    SUBENTRY_WATCHLIST,
)
from .coordinator import VueCinemasConfigEntry, VueCinemasCoordinator
from .services import async_setup_services
from .websocket_api import async_setup_websocket

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_FRONTEND_MODULES = "frontend_extra_module_url"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the card, the websocket command and the action."""
    integration = await async_get_integration(hass, DOMAIN)
    card = Path(__file__).parent / "www" / CARD_FILENAME
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card), cache_headers=False)]
    )
    if _FRONTEND_MODULES in hass.data:
        hass.data[_FRONTEND_MODULES].add(f"{CARD_URL}?v={integration.version}")
    async_setup_websocket(hass)
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: VueCinemasConfigEntry) -> bool:
    """Set up one cinema."""
    client = VueCinemasClient(async_get_clientsession(hass))
    coordinator = VueCinemasCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: _async_check_genres(hass, entry))
    )
    _async_check_genres(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VueCinemasConfigEntry) -> bool:
    """Unload one cinema."""
    ir.async_delete_issue(hass, DOMAIN, f"genres_unavailable_{entry.entry_id}")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: VueCinemasConfigEntry) -> None:
    """Reload after watchlists were added, changed or removed."""
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_check_genres(hass: HomeAssistant, entry: VueCinemasConfigEntry) -> None:
    """Raise a repair issue when genre filters cannot work.

    Genres come from scraping the film pages. If none could be read while a
    watchlist filters on genre, that watchlist silently shows nothing, so
    the user is told instead.
    """
    data = entry.runtime_data.data
    filtering = [
        s.title
        for s in entry.subentries.values()
        if s.subentry_type == SUBENTRY_WATCHLIST and s.data.get(CONF_GENRES)
    ]
    issue_id = f"genres_unavailable_{entry.entry_id}"
    if data and filtering and data.films and not data.genres:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="genres_unavailable",
            translation_placeholders={
                "cinema": entry.data[CONF_CINEMA_NAME],
                "watchlists": ", ".join(filtering),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
