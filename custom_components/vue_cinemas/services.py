"""The vue_cinemas.get_showings action."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SERVICE_GET_SHOWINGS
from .programme import get_programme, resolve_entity

SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the action."""

    async def get_showings(call: ServiceCall) -> ServiceResponse:
        entry_id, watchlist_id = resolve_entity(hass, call.data[ATTR_ENTITY_ID])
        return get_programme(hass, entry_id, watchlist_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SHOWINGS,
        get_showings,
        schema=SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
