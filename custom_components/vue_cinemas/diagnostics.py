"""Diagnostics for Vue Cinemas."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import VueCinemasConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VueCinemasConfigEntry
) -> dict[str, Any]:
    """Return diagnostics. Nothing here is personal: no account is involved."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {"title": entry.title, "data": dict(entry.data)},
        "watchlists": [
            {"title": s.title, "type": s.subentry_type, "data": dict(s.data)}
            for s in entry.subentries.values()
        ],
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
        },
        "programme": {
            "fetched": data.fetched.isoformat(),
            "films": len(data.films),
            "films_with_sessions": sum(1 for f in data.films if f.sessions),
            "sessions": sum(len(f.sessions) for f in data.films),
            "films_with_details": len(data.details),
            "details_failed_last_update": data.details_failed,
            "screens": data.screens,
            "attributes": data.attributes,
            "genres": data.genres,
        },
    }
