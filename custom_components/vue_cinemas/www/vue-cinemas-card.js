/*
 * vue-cinemas-card: the programme of a Vue Cinemas watchlist, in time order,
 * with a detail dialog per showing. Served by the vue_cinemas integration.
 */
const CARD_VERSION = "1.1.1";

const I18N = {
  nl: {
    today: "Vandaag",
    tomorrow: "Morgen",
    now: "Nu bezig",
    soldOut: "Uitverkocht",
    screen: "Zaal",
    nothing: "Geen voorstellingen die aan deze kijklijst voldoen.",
    comingSoon: "Binnenkort",
    release: "Release",
    unknownRelease: "Datum volgt",
    tickets: "Tickets kopen",
    filmPage: "Filmpagina",
    trailer: "Trailer",
    close: "Sluiten",
    director: "Regie",
    cast: "Cast",
    distributor: "Distributeur",
    genres: "Genre",
    runtime: "Speelduur",
    minutes: "min",
    otherShowings: "Andere voorstellingen",
    thisShowing: "Deze voorstelling",
    price: "Prijs",
    wheelchair: "Rolstoelplek beschikbaar",
    noWheelchair: "Geen rolstoelplek beschikbaar",
    unavailable: "Programma kon niet worden bijgewerkt; dit is de laatst bekende stand.",
    error: "Kon het programma niet laden",
    pickEntity: "Kies een sensor of kalender van een Vue-kijklijst.",
    more: (n) => `+${n} meer`,
    updated: "Bijgewerkt",
    rating: "Kijkwijzer",
    seatPlan: "Zaalindeling",
    hideSeatPlan: "Zaalindeling verbergen",
    screenLabel: "Scherm",
    occupied: (p) => `${p}% bezet`,
    seatFree: "Vrij",
    seatTaken: "Bezet",
    seatWheelchair: "Rolstoelplek",
    seatCompanion: "Begeleider",
    seatUnavailable: "Niet beschikbaar",
    row: "Rij",
    seat: "stoel",
    seatsLoading: "Zaalindeling laden…",
    seatsError: "Zaalindeling niet beschikbaar",
  },
  en: {
    today: "Today",
    tomorrow: "Tomorrow",
    now: "Showing now",
    soldOut: "Sold out",
    screen: "Screen",
    nothing: "No showings match this watchlist.",
    comingSoon: "Coming soon",
    release: "Release",
    unknownRelease: "Date to follow",
    tickets: "Buy tickets",
    filmPage: "Film page",
    trailer: "Trailer",
    close: "Close",
    director: "Director",
    cast: "Cast",
    distributor: "Distributor",
    genres: "Genre",
    runtime: "Running time",
    minutes: "min",
    otherShowings: "Other showings",
    thisShowing: "This showing",
    price: "Price",
    wheelchair: "Wheelchair space available",
    noWheelchair: "No wheelchair space available",
    unavailable: "The programme could not be updated; showing the last known state.",
    error: "Could not load the programme",
    pickEntity: "Choose a sensor or calendar of a Vue watchlist.",
    more: (n) => `+${n} more`,
    updated: "Updated",
    rating: "Age rating",
    seatPlan: "Seat plan",
    hideSeatPlan: "Hide seat plan",
    screenLabel: "Screen",
    occupied: (p) => `${p}% taken`,
    seatFree: "Free",
    seatTaken: "Taken",
    seatWheelchair: "Wheelchair space",
    seatCompanion: "Companion",
    seatUnavailable: "Unavailable",
    row: "Row",
    seat: "seat",
    seatsLoading: "Loading seat plan…",
    seatsError: "Seat plan unavailable",
  },
};

// Vue's genre names come in English; show them in Dutch for Dutch users.
const GENRES_NL = {
  Action: "Actie",
  Adventure: "Avontuur",
  Animation: "Animatie",
  Biography: "Biografie",
  Comedy: "Komedie",
  Crime: "Misdaad",
  Documentary: "Documentaire",
  Drama: "Drama",
  Family: "Familie",
  Fantasy: "Fantasy",
  History: "Geschiedenis",
  Horror: "Horror",
  Music: "Muziek",
  Musical: "Musical",
  Mystery: "Mysterie",
  Romance: "Romantiek",
  "Science Fiction": "Sciencefiction",
  "Sci-Fi": "Sciencefiction",
  Thriller: "Thriller",
  War: "Oorlog",
  Western: "Western",
};

const ATTRIBUTE_LABELS_NL = {
  Netherlands: "OV · NL ondertiteld",
  "Nederlandse Versie": "Nederlands gesproken",
  "English subtitles": "Engels ondertiteld",
};

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const safeUrl = (value) => {
  try {
    const url = new URL(String(value || ""), window.location.href);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch (_err) {
    return "";
  }
};

const fireEvent = (node, type, detail) => {
  node.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
};

class VueCinemasCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._programme = null;
    this._error = null;
    this._loading = false;
    this._lastStateStamp = null;
    this._dialog = null;
    this._timer = null;
    this._onKey = this._onKey.bind(this);
  }

  static getConfigElement() {
    return document.createElement("vue-cinemas-card-editor");
  }

  static getStubConfig(hass) {
    const entities = Object.values(hass?.entities || {}).filter(
      (e) => e.platform === "vue_cinemas" && e.entity_id.startsWith("sensor."),
    );
    const showings = entities.find((e) => e.entity_id.endsWith("_showings")) || entities[0];
    return { entity: showings ? showings.entity_id : "" };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    this._config = {
      show_posters: true,
      show_coming_soon: true,
      max_showings: 0,
      ...config,
    };
    this._programme = null;
    this._lastStateStamp = null;
    this._render();
    this._maybeFetch(true);
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeFetch(false);
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._timer = window.setInterval(() => this._maybeFetch(true), 5 * 60 * 1000);
    this._maybeFetch(true);
  }

  disconnectedCallback() {
    window.clearInterval(this._timer);
    this._timer = null;
    this._closeDialog();
  }

  getCardSize() {
    const n = this._programme?.showings?.length || 3;
    return Math.min(12, 2 + n);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  get _t() {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return I18N[lang] || I18N.en;
  }

  get _isNl() {
    return this._t === I18N.nl;
  }

  _maybeFetch(force) {
    const entity = this._config?.entity;
    if (!this._hass || !entity) {
      this._render();
      return;
    }
    const state = this._hass.states[entity];
    const stamp = state ? `${state.last_updated}|${state.state}` : "missing";
    if (!force && stamp === this._lastStateStamp) return;
    this._lastStateStamp = stamp;
    this._fetch();
  }

  async _fetch() {
    if (this._loading || !this._hass) return;
    this._loading = true;
    try {
      this._programme = await this._hass.callWS({
        type: "vue_cinemas/programme",
        entity_id: this._config.entity,
      });
      this._error = null;
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  // ---------- formatting ----------
  _tz() {
    return this._hass?.config?.time_zone || undefined;
  }

  _locale() {
    return this._isNl ? "nl-NL" : this._hass?.locale?.language || "en-GB";
  }

  _fmtTime(iso) {
    const pref = this._hass?.locale?.time_format;
    const opts = { hour: "2-digit", minute: "2-digit", timeZone: this._tz() };
    if (pref === "24") opts.hourCycle = "h23";
    if (pref === "12") opts.hour12 = true;
    return new Intl.DateTimeFormat(this._locale(), opts).format(new Date(iso));
  }

  _dayKey(iso) {
    return new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone: this._tz(),
    }).format(new Date(iso));
  }

  _fmtDay(iso) {
    const key = this._dayKey(iso);
    const now = new Date();
    if (key === this._dayKey(now.toISOString())) return this._t.today;
    if (key === this._dayKey(new Date(now.getTime() + 864e5).toISOString())) return this._t.tomorrow;
    return new Intl.DateTimeFormat(this._locale(), {
      weekday: "long",
      day: "numeric",
      month: "long",
      timeZone: this._tz(),
    }).format(new Date(iso));
  }

  _fmtDate(isoDate) {
    if (!isoDate) return this._t.unknownRelease;
    return new Intl.DateTimeFormat(this._locale(), {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(`${isoDate}T00:00:00Z`));
  }

  _genre(name) {
    return this._isNl ? GENRES_NL[name] || name : name;
  }

  _attrLabel(attr) {
    if (this._isNl && ATTRIBUTE_LABELS_NL[attr.name]) return ATTRIBUTE_LABELS_NL[attr.name];
    if (attr.name === "Netherlands") return "OV · Dutch subtitles";
    if (attr.name === "Nederlandse Versie") return "Dutch spoken";
    return attr.short_name || attr.name;
  }

  _chips(attributes) {
    return (attributes || [])
      .map((a) => {
        const accent = a.color ? ` style="--chip-accent:${esc(a.color)}"` : "";
        const cls = a.color ? "chip accent" : "chip";
        return `<span class="${cls}"${accent}>${esc(this._attrLabel(a))}</span>`;
      })
      .join("");
  }

  _rating(cert, size = "small") {
    if (!cert || !cert.name) return "";
    const img = safeUrl(cert.image);
    const label = `${this._t.rating} ${cert.name.toUpperCase()}`;
    return img
      ? `<img class="rating ${size}" src="${esc(img)}" alt="${esc(label)}" title="${esc(label)}">`
      : `<span class="chip">${esc(label)}</span>`;
  }

  // ---------- rendering ----------
  _render() {
    if (!this.shadowRoot) return;
    const t = this._t;
    const cfg = this._config || {};
    const p = this._programme;
    let body;

    if (!cfg.entity) {
      body = `<div class="empty">${esc(t.pickEntity)}</div>`;
    } else if (this._error && !p) {
      body = `<div class="empty warn" role="alert"><ha-icon icon="mdi:alert-circle-outline"></ha-icon> ${esc(t.error)}: ${esc(this._error)}</div>`;
    } else if (!p) {
      body = `<div class="loading"><ha-icon icon="mdi:movie-roll"></ha-icon></div>`;
    } else {
      body = this._renderProgramme(p);
    }

    const title =
      cfg.title ??
      (p ? `Vue ${p.cinema.name}${p.watchlist.name ? ` · ${p.watchlist.name}` : ""}` : "Vue");

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        ${title ? `<h1 class="card-header"><ha-icon icon="mdi:filmstrip"></ha-icon><span>${esc(title)}</span></h1>` : ""}
        <div class="content">${body}</div>
      </ha-card>
      <div class="dialog-host"></div>`;

    this.shadowRoot.querySelectorAll("[data-session]").forEach((el) => {
      el.addEventListener("click", () => this._openDialog(el.dataset.film, el.dataset.session));
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          this._openDialog(el.dataset.film, el.dataset.session);
        }
      });
    });
    this.shadowRoot.querySelectorAll("[data-soon]").forEach((el) => {
      el.addEventListener("click", () => this._openDialog(el.dataset.soon, null));
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          this._openDialog(el.dataset.soon, null);
        }
      });
    });
    if (this._dialog) this._renderDialog();
  }

  _renderProgramme(p) {
    const t = this._t;
    const cfg = this._config;
    const now = Date.now();
    let showings = p.showings || [];
    const max = Number(cfg.max_showings) || 0;
    const hidden = max > 0 ? Math.max(0, showings.length - max) : 0;
    if (max > 0) showings = showings.slice(0, max);

    let html = "";
    if (!p.available) {
      html += `<div class="notice" role="status"><ha-icon icon="mdi:cloud-alert"></ha-icon><span>${esc(t.unavailable)}</span></div>`;
    }
    if (!showings.length) {
      html += `<div class="empty">${esc(t.nothing)}</div>`;
    }

    let currentDay = null;
    for (const s of showings) {
      const film = p.films[s.film_id] || {};
      const day = this._dayKey(s.start);
      if (day !== currentDay) {
        if (currentDay !== null) html += `</ul>`;
        html += `<h2 class="day">${esc(this._fmtDay(s.start))}</h2><ul class="list">`;
        currentDay = day;
      }
      const running = new Date(s.start).getTime() <= now && new Date(s.end).getTime() > now;
      const poster = cfg.show_posters && safeUrl(film.poster)
        ? `<img class="poster" loading="lazy" src="${esc(safeUrl(film.poster))}" alt="">`
        : "";
      const status = s.sold_out
        ? `<span class="badge soldout"><ha-icon icon="mdi:close-circle"></ha-icon>${esc(t.soldOut)}</span>`
        : running
          ? `<span class="badge now"><ha-icon icon="mdi:play-circle"></ha-icon>${esc(t.now)}</span>`
          : "";
      html += `
        <li class="row${s.sold_out ? " is-soldout" : ""}${running ? " is-now" : ""}" tabindex="0" role="button"
            data-film="${esc(s.film_id)}" data-session="${esc(s.session_id)}"
            aria-label="${esc(`${this._fmtTime(s.start)} ${film.title || ""} ${s.screen || ""}`)}">
          <div class="time"><span class="start">${esc(this._fmtTime(s.start))}</span><span class="end">${esc(this._fmtTime(s.end))}</span></div>
          ${poster}
          <div class="info">
            <div class="title">${esc(film.title || s.film_id)}</div>
            <div class="meta">
              ${s.screen ? `<span class="screen"><ha-icon icon="mdi:seat"></ha-icon>${esc(s.screen)}</span>` : ""}
              ${this._rating(film.certificate)}
              ${status}
            </div>
            <div class="chips">${this._chips(s.attributes)}</div>
          </div>
          <ha-icon class="chevron" icon="mdi:chevron-right"></ha-icon>
        </li>`;
    }
    if (currentDay !== null) html += `</ul>`;
    if (hidden) html += `<div class="more">${esc(t.more(hidden))}</div>`;

    const soon = cfg.show_coming_soon ? p.coming_soon || [] : [];
    if (soon.length) {
      html += `<h2 class="day">${esc(t.comingSoon)}</h2><ul class="soon">`;
      for (const id of soon) {
        const film = p.films[id] || {};
        const poster = safeUrl(film.poster);
        html += `
          <li tabindex="0" role="button" data-soon="${esc(id)}" aria-label="${esc(film.title || id)}">
            ${poster ? `<img loading="lazy" src="${esc(poster)}" alt="">` : `<div class="noposter"><ha-icon icon="mdi:movie-open"></ha-icon></div>`}
            <div class="soon-title">${esc(film.title || id)}</div>
            <div class="soon-date">${esc(this._fmtDate(film.release_date))}</div>
          </li>`;
      }
      html += `</ul>`;
    }
    if (p.updated) {
      html += `<div class="updated">${esc(t.updated)} ${esc(this._fmtTime(p.updated))}</div>`;
    }
    return html;
  }

  // ---------- dialog ----------
  _openDialog(filmId, sessionId) {
    this._dialog = { filmId, sessionId, trailer: false, opener: this.shadowRoot.activeElement };
    window.addEventListener("keydown", this._onKey);
    this._renderDialog();
  }

  _closeDialog() {
    const opener = this._dialog?.opener;
    this._dialog = null;
    window.removeEventListener("keydown", this._onKey);
    const host = this.shadowRoot?.querySelector(".dialog-host");
    if (host) host.innerHTML = "";
    if (opener && typeof opener.focus === "function") opener.focus();
  }

  _onKey(ev) {
    if (ev.key === "Escape" && this._dialog) {
      ev.stopPropagation();
      this._closeDialog();
    }
  }

  async _loadSeats(sessionId) {
    this._dialog = { ...this._dialog, seats: { loading: true } };
    this._renderDialog();
    try {
      const plan = await this._hass.callWS({
        type: "vue_cinemas/seats",
        entity_id: this._config.entity,
        session_id: sessionId,
      });
      if (this._dialog?.sessionId !== sessionId) return;
      this._dialog = { ...this._dialog, seats: { plan } };
    } catch (err) {
      if (this._dialog?.sessionId !== sessionId) return;
      this._dialog = { ...this._dialog, seats: { error: err?.message || String(err) } };
    }
    this._renderDialog();
  }

  _renderSeats(state) {
    const t = this._t;
    if (state.loading) return `<div class="seats-msg">${esc(t.seatsLoading)}</div>`;
    if (state.error) return `<div class="seats-msg warn">${esc(t.seatsError)}</div>`;
    const plan = state.plan;
    const areas = Object.fromEntries((plan.areas || []).map((a) => [a.code, a]));
    const cols = Math.max(1, plan.columns || 1);
    const statusLabel = {
      free: t.seatFree,
      taken: t.seatTaken,
      wheelchair: t.seatWheelchair,
      companion: t.seatCompanion,
      unavailable: t.seatUnavailable,
    };
    const rows = (plan.rows || [])
      .map((row) => {
        if (!row.seats.length) return `<div class="seat-aisle" aria-hidden="true"></div>`;
        const seats = row.seats
          .map((seat) => {
            const area = areas[seat.area];
            const color = seat.status === "free" && area?.color ? ` style="--seat:${esc(area.color)};grid-column:${seat.column + 1}"` : ` style="grid-column:${seat.column + 1}"`;
            const title = `${t.row} ${row.label}, ${t.seat} ${seat.name}${area ? ` · ${area.name}` : ""} · ${statusLabel[seat.status] || seat.status}`;
            const glyph = seat.status === "wheelchair" ? "♿" : seat.status === "taken" ? "✕" : "";
            return `<span class="seat ${esc(seat.status)}"${color} title="${esc(title)}" aria-label="${esc(title)}">${glyph}</span>`;
          })
          .join("");
        return `<div class="seat-row"><span class="row-label">${esc(row.label)}</span><div class="seat-grid" style="grid-template-columns:repeat(${cols}, minmax(0, 1fr))">${seats}</div><span class="row-label">${esc(row.label)}</span></div>`;
      })
      .join("");
    const used = new Set((plan.rows || []).flatMap((r) => r.seats.map((s) => s.area)));
    const money = (cents) =>
      new Intl.NumberFormat(this._locale(), { style: "currency", currency: "EUR" }).format(cents / 100);
    const areaLegend = (plan.areas || [])
      .filter((a) => used.has(a.code))
      .map(
        (a) =>
          `<li title="${esc(a.description)}"><span class="seat free" style="--seat:${esc(a.color || "var(--primary-color)")}"></span>${esc(a.name)}${a.price_cents ? ` · ${esc(money(a.price_cents))}` : ""}</li>`,
      )
      .join("");
    const pct = Math.round((plan.occupancy || 0) * 100);
    return `
      <div class="seatplan" role="img" aria-label="${esc(`${t.seatPlan} ${plan.screen}, ${t.occupied(pct)}`)}">
        <div class="screen-bar">${esc(t.screenLabel)}</div>
        ${rows}
      </div>
      <div class="occupancy"><div class="bar"><span style="width:${pct}%"></span></div><span>${esc(t.occupied(pct))}</span></div>
      <ul class="legend">
        <li><span class="seat free"></span>${esc(t.seatFree)}</li>
        <li><span class="seat taken">✕</span>${esc(t.seatTaken)}</li>
        <li><span class="seat wheelchair">♿</span>${esc(t.seatWheelchair)}</li>
        ${areaLegend}
      </ul>`;
  }

  _renderDialog() {
    const host = this.shadowRoot.querySelector(".dialog-host");
    const p = this._programme;
    if (!host || !p || !this._dialog) return;
    const t = this._t;
    const film = p.films[this._dialog.filmId];
    if (!film) {
      this._closeDialog();
      return;
    }
    const showing = (p.showings || []).find((s) => s.session_id === this._dialog.sessionId);
    const others = (p.showings || []).filter(
      (s) => s.film_id === film.film_id && s.session_id !== this._dialog.sessionId,
    );
    const panel = safeUrl(film.panel);
    const poster = safeUrl(film.poster);
    const trailer = safeUrl(film.trailer);
    const filmUrl = safeUrl(film.url);

    const facts = [
      film.genres?.length
        ? [t.genres, film.genres.map((g) => this._genre(g)).join(", ")]
        : null,
      film.running_time ? [t.runtime, `${film.running_time} ${t.minutes}`] : null,
      [t.release, this._fmtDate(film.release_date)],
      film.director ? [t.director, film.director] : null,
      film.cast ? [t.cast, film.cast] : null,
      film.distributor ? [t.distributor, film.distributor] : null,
    ].filter(Boolean);

    const descriptors = (film.content_descriptors || [])
      .map((c) => {
        const img = safeUrl(c.image);
        const name = String(c.name || "").replace(/-/g, " ");
        return `<span class="descriptor">${img ? `<img src="${esc(img)}" alt="">` : ""}<span>${esc(name)}</span></span>`;
      })
      .join("");

    const shown = new Set(
      (showing?.attributes || [])
        .filter((a) => a.description && a.description !== a.name)
        .map((a) => a.name),
    );
    const filmAttrs = (film.film_attributes || [])
      .filter((a) => a.description && !shown.has(a.name))
      .map((a) => `<p class="attr-desc"><strong>${esc(a.name)}</strong> ${esc(a.description)}</p>`)
      .join("");

    let showingBlock = "";
    if (showing) {
      const attrDescs = (showing.attributes || [])
        .filter((a) => a.description && a.description !== a.name)
        .map((a) => `<li><strong>${esc(this._attrLabel(a))}</strong>: ${esc(a.description)}</li>`)
        .join("");
      const booking = safeUrl(showing.booking_url);
      showingBlock = `
        <section class="showing" aria-label="${esc(t.thisShowing)}">
          <h3>${esc(t.thisShowing)}</h3>
          <div class="when">
            <ha-icon icon="mdi:clock-outline"></ha-icon>
            <span>${esc(this._fmtDay(showing.start))}, ${esc(this._fmtTime(showing.start))} – ${esc(this._fmtTime(showing.end))}</span>
          </div>
          <div class="facts-inline">
            ${showing.screen ? `<span><ha-icon icon="mdi:seat"></ha-icon>${esc(showing.screen)}</span>` : ""}
            ${showing.price ? `<span><ha-icon icon="mdi:ticket"></ha-icon>${esc(showing.price)}</span>` : ""}
            <span><ha-icon icon="mdi:wheelchair-accessibility"></ha-icon>${esc(showing.wheelchair_available ? t.wheelchair : t.noWheelchair)}</span>
            ${showing.sold_out ? `<span class="badge soldout"><ha-icon icon="mdi:close-circle"></ha-icon>${esc(t.soldOut)}</span>` : ""}
          </div>
          <div class="chips">${this._chips(showing.attributes)}</div>
          ${attrDescs ? `<ul class="attr-list">${attrDescs}</ul>` : ""}
          ${this._dialog.seats ? this._renderSeats(this._dialog.seats) : ""}
          <div class="showing-actions">
          ${new Date(showing.end).getTime() > Date.now()
            ? `<button class="button" data-seats><ha-icon icon="mdi:seat-outline"></ha-icon>${esc(this._dialog.seats ? t.hideSeatPlan : t.seatPlan)}</button>`
            : ""}
          ${booking && !showing.sold_out && showing.booking_available
            ? `<a class="button primary" href="${esc(booking)}" target="_blank" rel="noopener noreferrer"><ha-icon icon="mdi:ticket-confirmation"></ha-icon>${esc(t.tickets)}</a>`
            : ""}
          </div>
        </section>`;
    }

    const otherBlock = others.length
      ? `<section><h3>${esc(t.otherShowings)}</h3><div class="others">${others
          .map(
            (s) =>
              `<button class="other${s.sold_out ? " is-soldout" : ""}" data-other="${esc(s.session_id)}">${esc(this._fmtDay(s.start))} ${esc(this._fmtTime(s.start))}${s.screen ? ` · ${esc(s.screen)}` : ""}${s.sold_out ? ` · ${esc(t.soldOut)}` : ""}</button>`,
          )
          .join("")}</div></section>`
      : "";

    const trailerBlock =
      trailer && this._dialog.trailer
        ? `<div class="trailer"><iframe src="${esc(trailer)}?autoplay=true" title="${esc(t.trailer)}" allow="autoplay; fullscreen; encrypted-media; picture-in-picture" allowfullscreen loading="lazy"></iframe></div>`
        : "";

    host.innerHTML = `
      <div class="backdrop" data-close></div>
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="vc-title">
        <button class="close" data-close aria-label="${esc(t.close)}"><ha-icon icon="mdi:close"></ha-icon></button>
        ${panel ? `<div class="panel"><img src="${esc(panel)}" alt=""></div>` : ""}
        <div class="dialog-body">
          <div class="head">
            ${poster ? `<img class="big-poster" src="${esc(poster)}" alt="">` : ""}
            <div>
              <h2 id="vc-title">${esc(film.title)}</h2>
              ${film.original_title && film.original_title !== film.title ? `<div class="original">${esc(film.original_title)}</div>` : ""}
              <div class="ratings">${this._rating(film.certificate, "large")}${descriptors}</div>
            </div>
          </div>
          ${trailerBlock}
          ${showingBlock}
          ${otherBlock}
          <section>
            <p class="synopsis">${esc(film.long_synopsis && film.long_synopsis.length > (film.synopsis || "").length ? `${film.synopsis} ${film.long_synopsis}` : film.synopsis)}</p>
            ${filmAttrs}
            <dl class="facts">${facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
          </section>
          <div class="actions">
            ${trailer && !this._dialog.trailer ? `<button class="button" data-trailer><ha-icon icon="mdi:play"></ha-icon>${esc(t.trailer)}</button>` : ""}
            ${filmUrl ? `<a class="button" href="${esc(filmUrl)}" target="_blank" rel="noopener noreferrer"><ha-icon icon="mdi:open-in-new"></ha-icon>${esc(t.filmPage)}</a>` : ""}
          </div>
        </div>
      </div>`;

    // Vue links some backdrops to its 404 page; drop the banner if it fails.
    const panelImg = host.querySelector(".panel img");
    panelImg?.addEventListener("error", () => panelImg.parentElement?.remove());
    host.querySelectorAll("[data-close]").forEach((el) =>
      el.addEventListener("click", () => this._closeDialog()),
    );
    host.querySelectorAll("[data-other]").forEach((el) =>
      el.addEventListener("click", () => {
        this._dialog = { ...this._dialog, sessionId: el.dataset.other, trailer: false, seats: null };
        this._renderDialog();
      }),
    );
    host.querySelector("[data-seats]")?.addEventListener("click", () => {
      if (this._dialog.seats) {
        this._dialog = { ...this._dialog, seats: null };
        this._renderDialog();
      } else {
        this._loadSeats(this._dialog.sessionId);
      }
    });
    host.querySelector("[data-trailer]")?.addEventListener("click", () => {
      this._dialog = { ...this._dialog, trailer: true };
      this._renderDialog();
    });
    // Keep focus on the seat plan toggle once it has been used.
    (("seats" in this._dialog && host.querySelector("[data-seats]")) || host.querySelector(".close"))?.focus();
  }
}

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .card-header { display: flex; align-items: center; gap: 10px; margin: 0; padding: 16px 16px 4px;
    font-size: 1.25rem; font-weight: 500; line-height: 1.4; color: var(--ha-card-header-color, var(--primary-text-color)); }
  .card-header ha-icon { color: var(--primary-color); }
  .content { padding: 4px 8px 12px; }
  .day { font-size: 0.95rem; font-weight: 600; letter-spacing: 0.02em; margin: 14px 8px 6px;
    color: var(--secondary-text-color); text-transform: capitalize; line-height: 1.5; }
  ul { list-style: none; margin: 0; padding: 0; }
  .row { position: relative; display: flex; align-items: center; gap: 12px; padding: 10px 8px; border-radius: 12px; cursor: pointer;
    line-height: 1.5; outline: none; }
  .row + .row::before { content: ""; position: absolute; top: 0; left: 8px; right: 8px; border-top: 1px solid var(--divider-color); }
  .row:hover, .row:focus-visible { background: var(--secondary-background-color); }
  .row:focus-visible { box-shadow: 0 0 0 2px var(--primary-color) inset; }
  .row.is-soldout .title, .row.is-soldout .time { opacity: 0.6; }
  .row.is-now { background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
  .time { display: flex; flex-direction: column; align-items: flex-start; min-width: 52px; font-variant-numeric: tabular-nums; }
  .time .start { font-size: 1.2rem; font-weight: 600; color: var(--primary-text-color); }
  .time .end { font-size: 0.85rem; color: var(--secondary-text-color); }
  .poster { width: 44px; height: 64px; object-fit: cover; border-radius: 6px; flex: none; background: var(--secondary-background-color); }
  .info { flex: 1; min-width: 0; }
  .title { font-size: 1rem; font-weight: 600; color: var(--primary-text-color); overflow: hidden; text-overflow: ellipsis; }
  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 2px; font-size: 0.9rem; color: var(--secondary-text-color); }
  .meta ha-icon, .facts-inline ha-icon, .badge ha-icon { --mdc-icon-size: 16px; margin-right: 3px; vertical-align: -3px; }
  .screen { white-space: nowrap; }
  .rating.small { height: 20px; width: auto; }
  .rating.large { height: 36px; width: auto; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
  .chip { font-size: 0.8rem; line-height: 1.4; padding: 1px 8px; border-radius: 999px;
    border: 1px solid var(--divider-color); color: var(--primary-text-color); white-space: nowrap; }
  .chip.accent { border-color: var(--chip-accent); box-shadow: inset 3px 0 0 var(--chip-accent); }
  .badge { font-size: 0.8rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
  .badge.soldout { color: var(--error-color); border: 1px solid var(--error-color); }
  .badge.now { color: var(--success-color, #2e7d32); border: 1px solid var(--success-color, #2e7d32); }
  .chevron { color: var(--secondary-text-color); flex: none; }
  .empty, .loading { padding: 24px 8px; color: var(--secondary-text-color); text-align: center; line-height: 1.5; }
  .empty.warn { color: var(--error-color); }
  .notice { display: flex; gap: 8px; align-items: center; margin: 4px 8px; padding: 8px 12px; border-radius: 8px;
    background: color-mix(in srgb, var(--warning-color, #f9a825) 15%, transparent); line-height: 1.5; }
  .more, .updated { padding: 8px; font-size: 0.85rem; color: var(--secondary-text-color); }
  .updated { text-align: right; }
  .soon { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 12px; padding: 0 8px; }
  .soon li { cursor: pointer; border-radius: 8px; outline: none; }
  .soon li:focus-visible { box-shadow: 0 0 0 2px var(--primary-color); }
  .soon img, .soon .noposter { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 8px; background: var(--secondary-background-color); display: flex; align-items: center; justify-content: center; }
  .soon-title { font-size: 0.9rem; font-weight: 600; margin-top: 4px; line-height: 1.35; }
  .soon-date { font-size: 0.8rem; color: var(--secondary-text-color); }

  .backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); z-index: 999; }
  .dialog { position: fixed; z-index: 1000; left: 50%; top: 50%; transform: translate(-50%, -50%);
    width: min(640px, calc(100vw - 24px)); max-height: calc(100vh - 32px); overflow: auto;
    background: var(--ha-card-background, var(--card-background-color, #fff)); color: var(--primary-text-color);
    border-radius: var(--ha-dialog-border-radius, 24px); box-shadow: 0 12px 48px rgba(0, 0, 0, 0.4); line-height: 1.55; }
  @media (max-width: 600px) { .dialog { top: auto; bottom: 0; transform: translate(-50%, 0); border-radius: 20px 20px 0 0; max-height: 92vh; } }
  .dialog-body:first-child, .close + .dialog-body { padding-top: 56px; }
  .close { position: absolute; top: 10px; right: 10px; z-index: 2; border: none; border-radius: 50%; width: 40px; height: 40px;
    background: rgba(0, 0, 0, 0.5); color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .close:focus-visible { outline: 2px solid #fff; }
  .panel { height: 180px; overflow: hidden; background: var(--secondary-background-color); }
  .panel img { width: 100%; height: 100%; object-fit: cover; object-position: center 30%; display: block; }
  .dialog-body { padding: 16px 20px 20px; }
  .head { display: flex; gap: 16px; align-items: flex-end; }
  .panel + .dialog-body .head { margin-top: -72px; }
  .big-poster { width: 104px; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,0.4); flex: none;
    background: var(--secondary-background-color); }
  .head h2 { margin: 0; font-size: 1.45rem; line-height: 1.3; }
  .original { color: var(--secondary-text-color); font-size: 0.9rem; }
  .ratings { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
  .descriptor { display: inline-flex; align-items: center; gap: 4px; font-size: 0.85rem; color: var(--secondary-text-color); }
  .descriptor img { height: 24px; width: auto; }
  section { margin-top: 16px; }
  h3 { margin: 0 0 6px; font-size: 0.95rem; font-weight: 600; color: var(--secondary-text-color); }
  .showing { padding: 12px 14px; border-radius: 14px; background: var(--secondary-background-color); }
  .when { display: flex; align-items: center; gap: 8px; font-size: 1.1rem; font-weight: 600; }
  .facts-inline { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 6px 0; font-size: 0.95rem; }
  .attr-list { margin: 8px 0 0; padding-left: 18px; list-style: disc; font-size: 0.9rem; }
  .attr-desc { font-size: 0.9rem; }
  .synopsis { margin: 0; font-size: 1rem; }
  .facts { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 12px 0 0; font-size: 0.95rem; }
  .facts dt { color: var(--secondary-text-color); }
  .facts dd { margin: 0; }
  .others { display: flex; flex-wrap: wrap; gap: 6px; }
  .other { font: inherit; font-size: 0.9rem; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--divider-color);
    background: transparent; color: var(--primary-text-color); cursor: pointer; }
  .other:hover, .other:focus-visible { border-color: var(--primary-color); }
  .other.is-soldout { opacity: 0.6; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  .button { display: inline-flex; align-items: center; gap: 6px; font: inherit; font-weight: 600; font-size: 0.95rem;
    padding: 8px 16px; border-radius: 999px; border: 1px solid var(--primary-color); color: var(--primary-color);
    background: transparent; cursor: pointer; text-decoration: none; }
  .button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .showing-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .seatplan { margin-top: 14px; padding: 12px 8px; border-radius: 12px; background: var(--card-background-color, #fff); }
  .screen-bar { margin: 0 auto 14px; width: 80%; text-align: center; font-size: 0.8rem; letter-spacing: 0.15em; text-transform: uppercase;
    color: var(--secondary-text-color); border-top: 4px solid var(--secondary-text-color); border-radius: 50% 50% 0 0 / 12px 12px 0 0; padding-top: 4px; }
  .seat-row { display: grid; grid-template-columns: 22px 1fr 22px; align-items: center; gap: 4px; margin: 3px 0; }
  .row-label { font-size: 0.75rem; color: var(--secondary-text-color); text-align: center; font-variant-numeric: tabular-nums; }
  .seat-grid { display: grid; gap: 3px; }
  .seat-aisle { height: 10px; }
  .seat { display: inline-flex; align-items: center; justify-content: center; aspect-ratio: 1; max-width: 24px; width: 100%;
    border-radius: 4px 4px 2px 2px; box-sizing: border-box; font-size: 0.65rem; line-height: 1; }
  .seat.free { border: 2px solid var(--seat, var(--primary-color)); background: transparent; }
  .seat.taken { background: var(--primary-text-color); color: var(--card-background-color, #fff); font-weight: 700; opacity: 0.55; }
  .seat.wheelchair { border: 2px solid var(--primary-text-color); font-size: 0.75rem; }
  .seat.companion { border: 2px dashed var(--secondary-text-color); }
  .seat.unavailable { background: var(--divider-color); }
  .occupancy { display: flex; align-items: center; gap: 10px; margin-top: 10px; font-size: 0.9rem; }
  .occupancy .bar { flex: 1; height: 8px; border-radius: 4px; background: var(--divider-color); overflow: hidden; }
  .occupancy .bar span { display: block; height: 100%; background: var(--primary-color); }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 10px 0 0; padding: 0; font-size: 0.85rem; }
  .legend li { display: inline-flex; align-items: center; gap: 6px; }
  .legend .seat { width: 18px; }
  .seats-msg { margin-top: 12px; color: var(--secondary-text-color); }
  .seats-msg.warn { color: var(--error-color); }
  .button ha-icon { --mdc-icon-size: 18px; }
  .trailer { margin-top: 16px; position: relative; padding-top: 56.25%; border-radius: 12px; overflow: hidden; background: #000; }
  .trailer iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
`;

class VueCinemasCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    else this._render();
  }

  _schema() {
    return [
      { name: "entity", required: true, selector: { entity: { integration: "vue_cinemas" } } },
      { name: "title", selector: { text: {} } },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "show_posters", selector: { boolean: {} } },
          { name: "show_coming_soon", selector: { boolean: {} } },
        ],
      },
      { name: "max_showings", selector: { number: { min: 0, max: 100, mode: "box" } } },
    ];
  }

  _label(field) {
    const nl = (this._hass?.locale?.language || "en").startsWith("nl");
    const labels = nl
      ? {
          entity: "Kijklijst (sensor of kalender)",
          title: "Titel (leeg = bioscoop en kijklijst)",
          show_posters: "Posters tonen",
          show_coming_soon: "Binnenkort tonen",
          max_showings: "Maximaal aantal voorstellingen (0 = alles)",
        }
      : {
          entity: "Watchlist (sensor or calendar)",
          title: "Title (empty = cinema and watchlist)",
          show_posters: "Show posters",
          show_coming_soon: "Show coming soon",
          max_showings: "Maximum showings (0 = all)",
        };
    return labels[field.name] || field.name;
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (field) => this._label(field);
      this._form.addEventListener("value-changed", (ev) => {
        const value = { ...ev.detail.value };
        if (value.title === "") delete value.title;
        this._config = value;
        fireEvent(this, "config-changed", { config: value });
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = { show_posters: true, show_coming_soon: true, max_showings: 0, ...this._config };
  }
}

if (!customElements.get("vue-cinemas-card")) {
  customElements.define("vue-cinemas-card", VueCinemasCard);
}
if (!customElements.get("vue-cinemas-card-editor")) {
  customElements.define("vue-cinemas-card-editor", VueCinemasCardEditor);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "vue-cinemas-card")) {
  window.customCards.push({
    type: "vue-cinemas-card",
    name: "Vue Cinemas",
    description: "Programme of a Vue Cinemas watchlist in time order, with film details on click.",
    preview: true,
    documentationURL: "https://github.com/Meppies/ha-vue-cinemas",
  });
}
console.info(`%c VUE-CINEMAS-CARD %c ${CARD_VERSION} `, "background:#de6a00;color:#fff", "");
