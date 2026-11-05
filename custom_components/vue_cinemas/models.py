"""Typed models for the Vue Cinemas API responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import html
import re
from typing import Any

from .const import BASE_URL, FILM_STATUS_COMING_SOON, HIDDEN_ATTRIBUTES


def _str(value: Any) -> str:
    """Return a stripped string, or an empty string for None."""
    return str(value).strip() if value is not None else ""


_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")


def clean_text(value: Any) -> str:
    """Turn a CMS text field into plain text.

    Vue's CMS leaves HTML entities and, in some descriptions, markup pasted
    from an e-mail client (``<span data-olk-copy-source=...>``).
    """
    text = _TAG.sub(" ", _str(value))
    return _SPACE.sub(" ", html.unescape(text)).strip()


@dataclass(frozen=True, slots=True)
class Cinema:
    """A Vue venue."""

    cinema_id: str
    name: str
    whats_on_url: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Cinema:
        """Build from a `/showings/cinemas` item."""
        return cls(
            cinema_id=_str(raw["cinemaId"]),
            name=_str(raw.get("fullName") or raw.get("cinemaName")),
            whats_on_url=_str(raw.get("whatsOnUrl")),
        )


@dataclass(frozen=True, slots=True)
class Attribute:
    """A showing or film attribute (language, 3D, Dolby Atmos, Vue Anime...)."""

    name: str
    short_name: str
    attribute_type: str
    description: str
    color: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Attribute:
        """Build from an attribute object."""
        return cls(
            name=_str(raw.get("name")),
            short_name=_str(raw.get("shortName")),
            attribute_type=_str(raw.get("attributeType")),
            description=clean_text(raw.get("description")),
            color=_str(raw.get("color")),
        )


def _attributes(raw: list[dict[str, Any]] | None) -> tuple[Attribute, ...]:
    """Parse a list of attributes, dropping internal ones."""
    parsed = (Attribute.from_api(item) for item in raw or [])
    return tuple(a for a in parsed if a.name and a.name not in HIDDEN_ATTRIBUTES)


@dataclass(frozen=True, slots=True)
class Certificate:
    """A Kijkwijzer classification or content descriptor."""

    name: str
    image_url: str

    @classmethod
    def from_api(cls, raw: dict[str, Any] | None) -> Certificate | None:
        """Build from a certificate object; None when empty."""
        if not raw or not raw.get("name"):
            return None
        return cls(name=_str(raw["name"]), image_url=_str(raw.get("src")))


@dataclass(frozen=True, slots=True)
class Session:
    """A single showing of a film."""

    session_id: str
    start: datetime
    end: datetime
    screen: str
    price: str
    sold_out: bool
    booking_available: bool
    wheelchair_available: bool
    booking_url: str
    attributes: tuple[Attribute, ...]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Session:
        """Build from a session object."""
        start = datetime.fromisoformat(raw["showTimeWithTimeZone"])
        end = datetime.fromisoformat(raw["endTime"])
        if end.tzinfo is None:
            end = end.replace(tzinfo=start.tzinfo)
        booking = _str(raw.get("bookingUrl"))
        return cls(
            session_id=_str(raw["sessionId"]),
            start=start,
            end=end,
            screen=_str(raw.get("screenName")),
            price=_str(raw.get("formattedPrice")) if raw.get("isPriceVisible") else "",
            sold_out=bool(raw.get("isSoldOut")),
            booking_available=bool(raw.get("isBookingAvailable")),
            wheelchair_available=bool(raw.get("wheelchairSeatAvailability")),
            booking_url=f"{BASE_URL}{booking}" if booking.startswith("/") else booking,
            attributes=_attributes(raw.get("attributes")),
        )


@dataclass(frozen=True, slots=True)
class Film:
    """A film with its sessions at one cinema."""

    film_id: str
    title: str
    original_title: str
    status: int
    release_date: date | None
    running_time: int
    synopsis: str
    cast: str
    director: str
    distributor: str
    url: str
    poster_url: str
    panel_url: str
    certificate: Certificate | None
    content_descriptors: tuple[Certificate, ...]
    film_attributes: tuple[Attribute, ...]
    sessions: tuple[Session, ...]

    @property
    def slug(self) -> str:
        """The film's slug on vuecinemas.nl, used for the detail page."""
        return self.url.rstrip("/").rsplit("/", 1)[-1] if self.url else ""

    @property
    def is_coming_soon(self) -> bool:
        """True for announced films without sessions yet."""
        return self.status in FILM_STATUS_COMING_SOON or not self.sessions

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Film:
        """Build from a `/showings/.../films` item."""
        release = _str(raw.get("releaseDate"))
        sessions = tuple(
            Session.from_api(session)
            for group in raw.get("showingGroups") or []
            for session in group.get("sessions") or []
        )
        return cls(
            film_id=_str(raw["filmId"]),
            title=clean_text(raw.get("filmTitle")),
            original_title=clean_text(raw.get("originalTitle")),
            status=int(raw.get("filmStatus") or 0),
            release_date=date.fromisoformat(release[:10]) if release else None,
            running_time=int(raw.get("runningTime") or 0),
            synopsis=clean_text(raw.get("synopsisShort")),
            cast=clean_text(raw.get("cast")),
            director=clean_text(raw.get("director")),
            distributor=clean_text(raw.get("distributor")),
            url=_str(raw.get("filmUrl")),
            poster_url=_str(raw.get("posterImageSrc")),
            panel_url=_str(raw.get("panelImageUrl")),
            certificate=Certificate.from_api(raw.get("certificate")),
            content_descriptors=tuple(
                c
                for c in (
                    Certificate.from_api(item)
                    for item in raw.get("secondaryCertificates") or []
                )
                if c is not None
            ),
            film_attributes=_attributes(raw.get("filmAttributes")),
            sessions=tuple(sorted(sessions, key=lambda s: s.start)),
        )


@dataclass(slots=True)
class FilmDetails:
    """Extra film data only published on the film's web page."""

    genres: list[str] = field(default_factory=list)
    long_synopsis: str = ""
    trailer_url: str = ""
    fetched: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise for storage."""
        data = asdict(self)
        data["fetched"] = self.fetched.isoformat() if self.fetched else None
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FilmDetails:
        """Restore from storage."""
        fetched = raw.get("fetched")
        return cls(
            genres=[str(g) for g in raw.get("genres") or []],
            # Cleaned again: copies stored before 1.1.3 may still hold markup.
            long_synopsis=clean_text(raw.get("long_synopsis")),
            trailer_url=str(raw.get("trailer_url") or ""),
            fetched=datetime.fromisoformat(fetched) if fetched else None,
        )


# Vue seat status codes, read from the seat icons the site pairs with them.
SEAT_FREE = "free"
SEAT_TAKEN = "taken"
SEAT_WHEELCHAIR = "wheelchair"
SEAT_COMPANION = "companion"
SEAT_UNAVAILABLE = "unavailable"
_SEAT_STATUS = {
    0: SEAT_FREE,
    1: SEAT_TAKEN,
    3: SEAT_WHEELCHAIR,
    7: SEAT_COMPANION,
    9: SEAT_TAKEN,
    11: SEAT_TAKEN,
}


@dataclass(frozen=True, slots=True)
class Seat:
    """One seat in the plan."""

    name: str
    column: int
    status: str
    area: str


@dataclass(frozen=True, slots=True)
class SeatRow:
    """A row of seats; an empty label marks an aisle."""

    label: str
    index: int
    seats: tuple[Seat, ...]


@dataclass(frozen=True, slots=True)
class SeatArea:
    """A seat category such as Lux or D-BOX."""

    code: str
    name: str
    description: str
    price_cents: int
    color: str


@dataclass(frozen=True, slots=True)
class SeatMap:
    """The seat plan of one session, with live occupancy."""

    screen: str
    occupancy: float
    columns: int
    rows: tuple[SeatRow, ...]
    areas: tuple[SeatArea, ...]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> SeatMap:
        """Build from a `/booking/Session/{cinema}/{session}/seats` result."""
        rows: list[SeatRow] = []
        width = 0
        for row in raw.get("seatRows") or []:
            seats = tuple(
                Seat(
                    name=_str(cell.get("name")),
                    column=int(cell.get("columnIndex") or 0),
                    status=_SEAT_STATUS.get(
                        int(cell.get("seatStatus") or 0), SEAT_UNAVAILABLE
                    ),
                    area=_str(cell.get("areaCategoryCode")),
                )
                for cell in row.get("columns") or []
                if cell
            )
            width = max(width, len(row.get("columns") or []))
            rows.append(
                SeatRow(
                    label=_str(row.get("rowLabel")),
                    index=int(row.get("rowIndex") or 0),
                    seats=tuple(sorted(seats, key=lambda s: s.column)),
                )
            )
        areas = tuple(
            SeatArea(
                code=_str(area.get("areaCategoryCode")),
                name=clean_text(area.get("areaName")),
                description=clean_text(area.get("areaDescription")),
                price_cents=int(area.get("areaMainPriceInCents") or 0),
                color=_str(area.get("areaColor")),
            )
            for area in raw.get("areaCategories") or []
        )
        return cls(
            screen=_str((raw.get("seatingData") or {}).get("screenLabel")),
            occupancy=float(raw.get("sessionOccupancy") or 0.0),
            columns=width,
            rows=tuple(sorted(rows, key=lambda r: r.index)),
            areas=areas,
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the card."""
        return asdict(self)
