"""Constants for the Vue Cinemas integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "vue_cinemas"
LOGGER = logging.getLogger(__package__)

BASE_URL: Final = "https://www.vuecinemas.nl"
API_URL: Final = f"{BASE_URL}/api/microservice"

UPDATE_INTERVAL: Final = timedelta(minutes=30)
DETAILS_MAX_AGE: Final = timedelta(days=7)
DETAILS_CONCURRENCY: Final = 3
REQUEST_TIMEOUT: Final = 30

STORAGE_KEY: Final = f"{DOMAIN}.film_details"
STORAGE_VERSION: Final = 1

# Config entry data
CONF_CINEMA_ID: Final = "cinema_id"
CONF_CINEMA_NAME: Final = "cinema_name"

# Watchlist subentry
SUBENTRY_WATCHLIST: Final = "watchlist"
CONF_MODE: Final = "mode"
CONF_DAYS_AHEAD: Final = "days_ahead"
CONF_SCREENS: Final = "screens"
CONF_GENRES: Final = "genres"
CONF_ATTRIBUTES: Final = "attributes"
CONF_MAX_CERTIFICATE: Final = "max_certificate"
CONF_HIDE_SOLD_OUT: Final = "hide_sold_out"
CONF_INCLUDE_COMING_SOON: Final = "include_coming_soon"

MODE_NOW_SHOWING: Final = "now_showing"
MODE_ALL: Final = "all"
MODES: Final = [MODE_NOW_SHOWING, MODE_ALL]

DEFAULT_DAYS_AHEAD: Final = 7
MAX_DAYS_AHEAD: Final = 90

CERTIFICATE_ANY: Final = "any"
# Kijkwijzer age classifications, in ascending order.
CERTIFICATES: Final = ["al", "6", "9", "12", "14", "16", "18"]

# Attributes Vue uses internally that carry no meaning for a viewer.
HIDDEN_ATTRIBUTES: Final = frozenset({"Singleseatrule"})

FILM_STATUS_COMING_SOON: Final = frozenset({0, 3})

# Card
CARD_FILENAME: Final = "vue-cinemas-card.js"
CARD_URL: Final = f"/{DOMAIN}/{CARD_FILENAME}"

# Service
SERVICE_GET_SHOWINGS: Final = "get_showings"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_WATCHLIST_ID: Final = "watchlist_id"
