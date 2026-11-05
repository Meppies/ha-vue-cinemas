# Vue Cinemas for Home Assistant

What is on at your Vue cinema in the Netherlands, filtered the way you want,
in Home Assistant. Pick a cinema, create one or more **watchlists** (for
example "Kids", "Horror", "3D and Dolby Atmos" or "Screen 1 only"), and put
the bundled dashboard card on a dashboard: the showings in time order, and a
tap on a showing opens everything Vue publishes about the film and that
showing.

![Vue Cinemas card](icon.png)

> This integration is not affiliated with or endorsed by Vue. It reads the
> same public data the vuecinemas.nl website uses. Vue publishes no official
> API, so a change to their site can break it; see
> [Known limitations](#known-limitations).

## Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [The dashboard card](#the-dashboard-card)
- [Action: `vue_cinemas.get_showings`](#action-vue_cinemasget_showings)
- [Examples](#examples)
- [How data is updated](#how-data-is-updated)
- [Supported cinemas](#supported-cinemas)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Removal](#removal)

## Features

- Every Vue cinema in the Netherlands (20 at the time of writing).
- **One entry per cinema, any number of watchlists per cinema.** Each
  watchlist has its own filters and its own device and entities.
- Filters per watchlist: now showing only, or also pre-sales and premières;
  days ahead (0 to 90); screens; genres; features such as 3D, Dolby Atmos,
  D-Box, Infinity Vision, Vue Plus, *Nederlandse Versie* or Vue Anime;
  maximum Kijkwijzer age rating; hide sold-out showings; list coming-soon
  films.
- Per watchlist: a **next showing** sensor, a **showings** count sensor and a
  **programme** calendar.
- A **dashboard card** with a visual editor. Showings are grouped by day in
  time order with poster, screen, Kijkwijzer rating, features and sold-out or
  "showing now" state. Tapping a showing opens a dialog with the backdrop,
  poster, Kijkwijzer rating and content descriptors, date, time, screen,
  price, wheelchair space, feature explanations, other showings of the same
  film, synopsis, genre, running time, release date, director, cast,
  distributor, the trailer and a **Buy tickets** button.
- A live **seat plan** per showing in that dialog: screen, rows and aisles,
  free and taken seats, wheelchair spaces, seat types with their price
  (Lux, D-BOX, Ultra Lux and so on) and how full the showing is. It is
  fetched only when you open it.
- Dutch and English, following your Home Assistant language.

## Installation

### HACS (recommended)

1. In HACS, open the menu (three dots) and choose **Custom repositories**.
2. Add `https://github.com/Meppies/ha-vue-cinemas` with type **Integration**.
3. Search for **Vue Cinemas** in HACS and download it.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/vue_cinemas` into the `custom_components` folder of
   your Home Assistant configuration directory.
2. Restart Home Assistant.

The card is served and registered by the integration itself. There is no
separate Lovelace resource to add.

## Configuration

### Add a cinema

1. Go to **Settings → Devices & services → Add integration** and choose
   **Vue Cinemas**.
2. Choose the cinema.

| Field | Description |
|---|---|
| Cinema | The Vue cinema whose programme you want. Cinemas already added are not offered again. |

A watchlist called **Alles** (everything, 7 days, now showing) is created
with it, so the card works straight away.

### Add or change a watchlist

On the cinema's entry, choose **Add watchlist**. To change one, open the
watchlist's menu (three dots) and choose **Reconfigure**.

| Option | Description | Default |
|---|---|---|
| Name | Shown on the device and in the card. Must be unique per cinema. | — |
| What to show | *Now showing* only lists films already released. *Also pre-sales and premières* adds showings of films not yet out. | Now showing |
| Days ahead | How far ahead to look. 0 is today only. | 7 |
| Screens | Only showings in these screens. Empty is all screens. | all |
| Genres | Only films in at least one of these genres. | all |
| Features | Only showings with at least one of these features. | all |
| Maximum age rating | Hide films with a higher Kijkwijzer age. Films not yet rated (*tbc*) are always shown. | No limit |
| Hide sold-out showings | Leave sold-out showings out. | off |
| List coming-soon films | Also list announced films without showings yet, releasing within 90 days. | on |

Screens, genres and features are offered from what the cinema actually has in
its programme at that moment. A value you saved earlier stays selectable even
if the cinema no longer offers it.

## Entities

Each watchlist is a device, *Vue <cinema> · <watchlist>*, with:

| Entity | State | Attributes |
|---|---|---|
| `sensor.…_next_showing` | Start time of the next showing that has not started yet (timestamp). | `film`, `screen`, `end`, `attributes` (features), `film_id`, `session_id`, `poster`, `booking_url` |
| `sensor.…_showings` | Number of showings still to start in the window. | `films` (number of distinct films) |
| `calendar.…_programme` | On while a showing in the watchlist is running. | Calendar events: *Film (Screen)*, with features, price and booking link in the description. |

The sensors move on to the next showing at the moment a showing starts, not
only on the next update.

## The dashboard card

Add a card and pick **Vue Cinemas** from the list, or use YAML:

```yaml
type: custom:vue-cinemas-card
entity: sensor.vue_amersfoort_alles_showings
```

| Option | Description | Default |
|---|---|---|
| `entity` | Any sensor or calendar of the watchlist. Required. | — |
| `title` | Card title. Empty shows *Vue <cinema> · <watchlist>*. | — |
| `show_posters` | Poster thumbnails in the list. | `true` |
| `show_coming_soon` | The coming-soon posters below the list (if the watchlist lists them). | `true` |
| `max_showings` | Show at most this many showings. `0` is all. | `0` |

Press **Escape** or the close button to close the dialog. The list and the
dialog work with the keyboard.

## Action: `vue_cinemas.get_showings`

Returns the full programme of one watchlist: cinema, watchlist, every
showing with its details, every film with its details, and the coming-soon
list. This is the same data the card uses.

| Field | Description |
|---|---|
| `entity_id` | Any sensor or calendar of the watchlist. |

It raises an error if the entity is not a Vue Cinemas watchlist entity or the
cinema is not loaded.

## Examples

### Notify when a new film appears in a watchlist

```yaml
automation:
  - alias: "New horror film at Vue"
    triggers:
      - trigger: state
        entity_id: sensor.vue_amersfoort_horror_showings
        attribute: films
    conditions:
      - "{{ trigger.to_state.attributes.films | int(0) > trigger.from_state.attributes.films | int(0) }}"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "New horror at Vue Amersfoort. Next: {{ state_attr('sensor.vue_amersfoort_horror_next_showing', 'film') }}"
```

### Reminder two hours before a showing

```yaml
automation:
  - alias: "Vue showing in two hours"
    triggers:
      - trigger: calendar
        event: start
        offset: "-2:00:00"
        entity_id: calendar.vue_amersfoort_kids_programme
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "{{ trigger.calendar_event.summary }} starts at {{ as_datetime(trigger.calendar_event.start).strftime('%H:%M') }}"
```

### Tonight's films in a template

```yaml
action: vue_cinemas.get_showings
data:
  entity_id: sensor.vue_amersfoort_alles_showings
response_variable: programme
# {{ programme.showings | map(attribute='film_id') | map('extract', programme.films) | map(attribute='title') | unique | list }}
```

## Use cases

- A wall tablet in the living room showing what is on tonight.
- A "Kids" watchlist with a maximum age rating of 6 and *Nederlandse Versie*,
  for Saturday afternoon plans.
- A "Big screen" watchlist with Infinity Vision, Dolby Atmos and D-Box.
- A calendar of the films you are waiting for, with a phone reminder.

## How data is updated

- Every **30 minutes** the integration fetches the full programme of each
  cinema in one request: all films with all their showings. The API needs an
  anonymous guest token, which the integration requests from Vue and renews
  about every twelve hours; no account is involved. Watchlists are
  filters over that data, so adding watchlists adds no requests.
- **Genres, the long synopsis and the trailer** are not in that data. They are
  read once per film from the film's page on vuecinemas.nl and kept for
  **7 days**, shared by all cinemas and kept across restarts. On the first
  start that means one page per film, three at a time: for a large cinema
  about 125 pages of roughly 80 kB (about 10 MB, a few seconds). After that
  only new films are fetched, plus each film again once a week.
- If an update fails, entities become unavailable and the integration retries
  on the next interval. The card keeps the last data and says it is out of
  date.

## Supported cinemas

All Vue cinemas in the Netherlands listed on vuecinemas.nl. Vue cinemas in
other countries (myvue.com and others) run on the same platform but are not
supported in this version.

## Known limitations

- **Unofficial API.** Vue has no public API. If Vue changes its website the
  integration may stop working until it is updated.
- **Genres are scraped** from the film pages and come in English (the card
  translates the common ones to Dutch). If they cannot be read, a repair issue
  appears for watchlists that filter on genre, because those would otherwise
  show nothing.
- **Language features** are Vue's own labels: *Netherlands* is shown as
  *OV · NL ondertiteld* (original version with Dutch subtitles) and
  *Nederlandse Versie* as *Nederlands gesproken*. That reading is based on
  the programme, not on documentation from Vue.
- Prices are Vue's displayed standard price; discounts, Unlimited and seat
  types are not included.
- No seat availability beyond sold out and wheelchair space.
- Tickets are bought on vuecinemas.nl; the integration cannot book or
  reserve seats. The seat plan is read-only and shows the state at the moment
  you open it.
- Some film backdrops on vuecinemas.nl link to a missing image; the dialog
  then shows the poster without a backdrop.

## Troubleshooting

- **"Could not reach vuecinemas.nl" when adding.** Home Assistant could not
  reach the site. Check the internet connection of Home Assistant and press
  **Submit** to try again.
- **Entities are unavailable.** Updates are failing. Download the diagnostics
  of the entry (entry menu → **Download diagnostics**): `last_exception` shows
  the reason.
- **A watchlist is empty.** Every filter must match: try removing filters one
  at a time. A genre filter without readable genres matches nothing; check
  **Settings → Repairs**.
- **The card says "Custom element doesn't exist".** Refresh the browser (on
  the app: clear the frontend cache) after installing or updating.
- **Debug logging:**

  ```yaml
  logger:
    logs:
      custom_components.vue_cinemas: debug
  ```

## Removal

1. Remove the card(s) from your dashboards.
2. Go to **Settings → Devices & services → Vue Cinemas**, open each cinema's
   menu and choose **Delete**. This removes its watchlists, devices and
   entities.
3. In HACS, open **Vue Cinemas** and choose **Remove**, or delete
   `custom_components/vue_cinemas` for a manual install.
4. Restart Home Assistant.

## Development

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r tests/requirements_test.txt
pytest --cov
mypy custom_components/vue_cinemas
```

## Licence

MIT. See [LICENSE](LICENSE).
