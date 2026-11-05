# Changelog

## 1.1.3 — 2026-11-05

- The detail dialog no longer repeats the synopsis. Vue's long synopsis is
  sometimes a rewrite that already contains the short one; it is now shown
  on its own in that case, and still appended when it continues the short
  one.
- Raw HTML no longer shows in the dialog. Some of Vue's feature
  descriptions and long synopses contain markup pasted from an e-mail client
  (`<span data-olk-copy-source=...>`); all CMS text is now converted to plain
  text, including synopses already cached by earlier versions.
- Screenshots in the README, taken on Home Assistant 2026.11 with live data.
- README: entity IDs follow the language of the installation.

## 1.1.2 — 2026-11-05

- The card now adds itself to **Settings → Dashboards → Resources**, the way
  ns-reisadvies does, and is removed from there when the last cinema is
  removed. Before, it was only registered as an extra frontend module, and
  on some installations it did not show up in the card picker.

## 1.1.1 — 2026-11-05

- Ready for the Home Assistant Marketplace (2026.11): integration categories
  in the manifest, translations shipped only in `translations/` (no
  `strings.json`), installation instructions for the Marketplace.

## 1.1.0 — 2026-11-05

- Seat plan in the card's detail dialog: rows, aisles, free and taken seats,
  wheelchair spaces, seat types with price and occupancy, fetched on demand
  through the new `vue_cinemas/seats` websocket command.
- Backdrops that fail to load are dropped instead of leaving an empty banner.

## 1.0.0 — 2026-11-05

First release.

- One config entry per Vue cinema in the Netherlands; watchlists as subentries
  with filters for mode, days ahead, screens, genres, features, Kijkwijzer age,
  sold out and coming soon.
- Per watchlist: next-showing and showings sensors and a programme calendar.
- `vue_cinemas.get_showings` action and a websocket command for the card.
- Bundled `vue-cinemas-card` with visual editor and detail dialog.
- Diagnostics, repair issue for unreadable genres, Dutch and English.
