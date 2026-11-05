"""Look up a watchlist's full programme, shared by the websocket API and the action."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import CONF_CINEMA_ID, CONF_CINEMA_NAME, DOMAIN, SUBENTRY_WATCHLIST
from .coordinator import VueCinemasConfigEntry
from .serialise import programme_dict
from .watchlist import Watchlist, select_coming_soon, select_showings


def resolve_entity(hass: HomeAssistant, entity_id: str) -> tuple[str, str]:
    """Map one of our entities to (config entry id, watchlist id)."""
    entry = er.async_get(hass).async_get(entity_id)
    if (
        entry is None
        or entry.platform != DOMAIN
        or not entry.config_entry_id
        or not entry.config_subentry_id
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_entity",
            translation_placeholders={"entity_id": entity_id},
        )
    return entry.config_entry_id, entry.config_subentry_id


def get_watchlist_entry(
    hass: HomeAssistant, entry_id: str, watchlist_id: str
) -> tuple[VueCinemasConfigEntry, ConfigSubentry]:
    """Return a loaded cinema entry and one of its watchlists, or raise."""
    entry: VueCinemasConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_entry",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"cinema": entry.title},
        )
    subentry = entry.subentries.get(watchlist_id)
    if subentry is None or subentry.subentry_type != SUBENTRY_WATCHLIST:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_watchlist",
            translation_placeholders={"watchlist_id": watchlist_id},
        )
    return entry, subentry


def get_programme(
    hass: HomeAssistant, entry_id: str, watchlist_id: str
) -> dict[str, Any]:
    """Return the serialised programme of one watchlist."""
    entry, subentry = get_watchlist_entry(hass, entry_id, watchlist_id)
    coordinator = entry.runtime_data
    data = coordinator.data
    watchlist = Watchlist.from_data(subentry.data)
    now = dt_util.now()
    showings = select_showings(data, watchlist, now)
    coming_soon = select_coming_soon(data, watchlist, now)
    return {
        "cinema": {
            "id": entry.data[CONF_CINEMA_ID],
            "name": entry.data[CONF_CINEMA_NAME],
        },
        "watchlist": {"id": subentry.subentry_id, "name": subentry.title},
        "updated": data.fetched.isoformat(),
        "available": coordinator.last_update_success,
        **programme_dict(showings, coming_soon, data.details),
    }
