"""Config flow for Vue Cinemas: one entry per cinema, watchlists as subentries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import VueCinemasClient, VueCinemasError
from .const import (
    CERTIFICATE_ANY,
    CERTIFICATES,
    CONF_ATTRIBUTES,
    CONF_CINEMA_ID,
    CONF_CINEMA_NAME,
    CONF_DAYS_AHEAD,
    CONF_GENRES,
    CONF_HIDE_SOLD_OUT,
    CONF_INCLUDE_COMING_SOON,
    CONF_MAX_CERTIFICATE,
    CONF_MODE,
    CONF_SCREENS,
    DEFAULT_DAYS_AHEAD,
    DOMAIN,
    LOGGER,
    MAX_DAYS_AHEAD,
    MODE_NOW_SHOWING,
    MODES,
    SUBENTRY_WATCHLIST,
)
from .coordinator import CinemaData, VueCinemasCoordinator
from .models import Cinema

DEFAULT_WATCHLIST: dict[str, Any] = {
    CONF_MODE: MODE_NOW_SHOWING,
    CONF_DAYS_AHEAD: DEFAULT_DAYS_AHEAD,
    CONF_SCREENS: [],
    CONF_GENRES: [],
    CONF_ATTRIBUTES: [],
    CONF_MAX_CERTIFICATE: CERTIFICATE_ANY,
    CONF_HIDE_SOLD_OUT: False,
    CONF_INCLUDE_COMING_SOON: True,
}


class VueCinemasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Vue cinema."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._cinemas: dict[str, Cinema] = {}

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Watchlists are subentries of a cinema."""
        return {SUBENTRY_WATCHLIST: WatchlistSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a cinema."""
        errors: dict[str, str] = {}
        if user_input is not None and user_input.get(CONF_CINEMA_ID) in self._cinemas:
            cinema = self._cinemas[user_input[CONF_CINEMA_ID]]
            await self.async_set_unique_id(cinema.cinema_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Vue {cinema.name}",
                data={CONF_CINEMA_ID: cinema.cinema_id, CONF_CINEMA_NAME: cinema.name},
                subentries=[
                    {
                        "subentry_type": SUBENTRY_WATCHLIST,
                        "title": "Alles",
                        "data": DEFAULT_WATCHLIST,
                        "unique_id": None,
                    }
                ],
            )

        client = VueCinemasClient(async_get_clientsession(self.hass))
        try:
            cinemas = await client.async_get_cinemas()
        except VueCinemasError as err:
            LOGGER.debug("Cinema list unavailable: %s", err)
            errors["base"] = "cannot_connect"
            cinemas = []
        self._cinemas = {c.cinema_id: c for c in cinemas}
        configured = self._async_current_ids(include_ignore=False)
        options = [
            SelectOptionDict(value=c.cinema_id, label=c.name)
            for c in cinemas
            if c.cinema_id not in configured
        ]
        if cinemas and not options:
            return self.async_abort(reason="all_configured")
        # Without a cinema list the form is a plain retry button.
        schema = (
            vol.Schema(
                {
                    vol.Required(CONF_CINEMA_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            )
            if options
            else vol.Schema({})
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


def _select(options: list[str], current: list[str]) -> SelectSelector:
    """Multi-select over the known options plus anything already chosen."""
    values = list(dict.fromkeys([*options, *current]))
    return SelectSelector(
        SelectSelectorConfig(
            options=values,
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=False,
            sort=False,
        )
    )


def watchlist_schema(data: CinemaData, defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the watchlist form from what the cinema actually offers."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): TextSelector(),
            vol.Required(
                CONF_MODE, default=defaults.get(CONF_MODE, MODE_NOW_SHOWING)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=MODES,
                    mode=SelectSelectorMode.LIST,
                    translation_key=CONF_MODE,
                )
            ),
            vol.Required(
                CONF_DAYS_AHEAD,
                default=defaults.get(CONF_DAYS_AHEAD, DEFAULT_DAYS_AHEAD),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=MAX_DAYS_AHEAD, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_SCREENS, default=list(defaults.get(CONF_SCREENS, []))
            ): _select(data.screens, list(defaults.get(CONF_SCREENS, []))),
            vol.Optional(
                CONF_GENRES, default=list(defaults.get(CONF_GENRES, []))
            ): _select(data.genres, list(defaults.get(CONF_GENRES, []))),
            vol.Optional(
                CONF_ATTRIBUTES, default=list(defaults.get(CONF_ATTRIBUTES, []))
            ): _select(data.attributes, list(defaults.get(CONF_ATTRIBUTES, []))),
            vol.Required(
                CONF_MAX_CERTIFICATE,
                default=defaults.get(CONF_MAX_CERTIFICATE, CERTIFICATE_ANY),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[CERTIFICATE_ANY, *CERTIFICATES],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_MAX_CERTIFICATE,
                )
            ),
            vol.Required(
                CONF_HIDE_SOLD_OUT, default=defaults.get(CONF_HIDE_SOLD_OUT, False)
            ): BooleanSelector(),
            vol.Required(
                CONF_INCLUDE_COMING_SOON,
                default=defaults.get(CONF_INCLUDE_COMING_SOON, True),
            ): BooleanSelector(),
        }
    )


def _clean_input(user_input: dict[str, Any]) -> dict[str, Any]:
    data = {k: v for k, v in user_input.items() if k != CONF_NAME}
    data[CONF_DAYS_AHEAD] = int(data[CONF_DAYS_AHEAD])
    return {**DEFAULT_WATCHLIST, **data}


class WatchlistSubentryFlow(ConfigSubentryFlow):
    """Add or change a watchlist."""

    def _coordinator(self) -> VueCinemasCoordinator | None:
        entry = self._get_entry()
        if entry.state is not ConfigEntryState.LOADED:
            return None
        coordinator: VueCinemasCoordinator = entry.runtime_data
        return coordinator

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a watchlist."""
        coordinator = self._coordinator()
        if coordinator is None:
            return self.async_abort(reason="entry_not_loaded")
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            elif any(
                s.title.casefold() == name.casefold()
                for s in self._get_entry().subentries.values()
            ):
                errors[CONF_NAME] = "name_exists"
            else:
                return self.async_create_entry(title=name, data=_clean_input(user_input))
        defaults = {**DEFAULT_WATCHLIST, **(user_input or {})}
        return self.async_show_form(
            step_id="user",
            data_schema=watchlist_schema(coordinator.data, defaults),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a watchlist."""
        coordinator = self._coordinator()
        if coordinator is None:
            return self.async_abort(reason="entry_not_loaded")
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            elif any(
                s.title.casefold() == name.casefold()
                and s.subentry_id != subentry.subentry_id
                for s in self._get_entry().subentries.values()
            ):
                errors[CONF_NAME] = "name_exists"
            else:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=name,
                    data=_clean_input(user_input),
                )
        defaults = {
            **DEFAULT_WATCHLIST,
            **subentry.data,
            CONF_NAME: subentry.title,
            **(user_input or {}),
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=watchlist_schema(coordinator.data, defaults),
            errors=errors,
        )
