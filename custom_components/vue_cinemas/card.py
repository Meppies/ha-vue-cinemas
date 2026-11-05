"""Make the bundled dashboard card available to the frontend.

The card is registered twice, like ns-reisadvies does: as an extra frontend
module, and as a dashboard resource (Settings → Dashboards → Resources).
The resource is what most installations rely on; the extra module covers
dashboards in YAML mode, which have no editable resource list.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CARD_URL, LOGGER

_FRONTEND_MODULES = "frontend_extra_module_url"
_LOVELACE = "lovelace"


def _base(url: str) -> str:
    return url.split("?", 1)[0]


async def _async_resources(hass: HomeAssistant) -> Any | None:
    """Return the editable dashboard resource collection, or None."""
    lovelace = hass.data.get(_LOVELACE)
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None or not hasattr(resources, "async_create_item"):
        return None  # no dashboards, or resources managed in YAML
    if not getattr(resources, "loaded", True):
        await resources.async_load()
    return resources


async def async_register_card(hass: HomeAssistant, version: str) -> None:
    """Register the card as frontend module and dashboard resource."""
    url = f"{CARD_URL}?v={version}"
    modules = hass.data.get(_FRONTEND_MODULES)
    if modules is not None:
        modules.add(url)
    try:
        resources = await _async_resources(hass)
        if resources is None:
            return
        existing = [
            item
            for item in resources.async_items()
            if _base(str(item.get("url") or "")) == CARD_URL
        ]
        if not existing:
            await resources.async_create_item({"res_type": "module", "url": url})
            return
        first, *duplicates = existing
        if first.get("url") != url:
            await resources.async_update_item(
                first["id"], {"res_type": "module", "url": url}
            )
        for item in duplicates:
            await resources.async_delete_item(item["id"])
    except Exception as err:  # noqa: BLE001 - never block setup on the card
        LOGGER.warning(
            "Could not add the card to the dashboard resources; add %s as a "
            "JavaScript module by hand: %s",
            url,
            err,
        )


async def async_unregister_card(hass: HomeAssistant) -> None:
    """Remove the dashboard resource when the integration is removed."""
    try:
        resources = await _async_resources(hass)
        if resources is None:
            return
        for item in list(resources.async_items()):
            if _base(str(item.get("url") or "")) == CARD_URL:
                await resources.async_delete_item(item["id"])
    except Exception as err:  # noqa: BLE001 - removal must not fail on this
        LOGGER.debug("Card resource not removed: %s", err)
