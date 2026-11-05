"""Typed models for the Vue Cinemas API responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import html
from typing import Any

from .const import BASE_URL, FILM_STATUS_COMING_SOON, HIDDEN_ATTRIBUTES


def _str(value: Any) -> str:
    """Return a stripped string, or an empty string for None."""
    return str(value).strip() if value is not None else ""


def _clean(value: Any) -> str:
    """Decode HTML entities the CMS leaves in plain-text fields."""
    return html.unescape(_str(value))


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
            description=_clean(raw.get("description")),
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
            title=_clean(raw.get("filmTitle")),
            original_title=_clean(raw.get("originalTitle")),
            status=int(raw.get("filmStatus") or 0),
            release_date=date.fromisoformat(release[:10]) if release else None,
            running_time=int(raw.get("runningTime") or 0),
            synopsis=_clean(raw.get("synopsisShort")),
            cast=_clean(raw.get("cast")),
            director=_clean(raw.get("director")),
            distributor=_clean(raw.get("distributor")),
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
            long_synopsis=str(raw.get("long_synopsis") or ""),
            trailer_url=str(raw.get("trailer_url") or ""),
            fetched=datetime.fromisoformat(fetched) if fetched else None,
        )
