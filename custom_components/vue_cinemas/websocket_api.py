"""Websocket command the dashboard card uses to fetch a full programme."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import websocket_command
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError

from .programme import get_programme, resolve_entity


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    """Register the websocket command."""
    websocket_api.async_register_command(hass, ws_programme)


@websocket_command(
    {
        vol.Required("type"): "vue_cinemas/programme",
        vol.Required("entity_id"): str,
    }
)
@callback
def ws_programme(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the programme behind one of the integration's entities."""
    try:
        entry_id, watchlist_id = resolve_entity(hass, msg["entity_id"])
        programme = get_programme(hass, entry_id, watchlist_id)
    except ServiceValidationError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], programme)
