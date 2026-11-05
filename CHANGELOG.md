# Changelog

## 1.1.0 — 2026-11-05

- Seat plan in the card's detail dialog: rows, aisles, free and taken seats,
  wheelchair spaces, seat types with price and occupancy, fetched on demand
  through the new `vue_cinemas/seats` websocket command.
- Backdrops that fail to load are dropped instead of leaving an empty banner.
- Coming-soon list limited to releases within 90 days (Vue announces films
  up to a year ahead).

## 1.0.0 — 2026-11-05

First release.

- One config entry per Vue cinema in the Netherlands; watchlists as subentries
  with filters for mode, days ahead, screens, genres, features, Kijkwijzer age,
  sold out and coming soon.
- Per watchlist: next-showing and showings sensors and a programme calendar.
- `vue_cinemas.get_showings` action and a websocket command for the card.
- Bundled `vue-cinemas-card` with visual editor and detail dialog.
- Diagnostics, repair issue for unreadable genres, Dutch and English.
