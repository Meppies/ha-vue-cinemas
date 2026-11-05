"""JSON-ready views of films and showings for the card and the action."""

from __future__ import annotations

from typing import Any

from .models import Attribute, Certificate, Film, FilmDetails
from .watchlist import Showing


def _attribute(attr: Attribute) -> dict[str, Any]:
    return {
        "name": attr.name,
        "short_name": attr.short_name or attr.name,
        "type": attr.attribute_type,
        "description": attr.description,
        "color": attr.color,
    }


def _certificate(cert: Certificate | None) -> dict[str, Any] | None:
    return {"name": cert.name, "image": cert.image_url} if cert else None


def film_dict(film: Film, details: FilmDetails | None) -> dict[str, Any]:
    """Serialise a film with its page details."""
    return {
        "film_id": film.film_id,
        "title": film.title,
        "original_title": film.original_title,
        "release_date": film.release_date.isoformat() if film.release_date else None,
        "running_time": film.running_time,
        "synopsis": film.synopsis,
        "long_synopsis": details.long_synopsis if details else "",
        "genres": list(details.genres) if details else [],
        "cast": film.cast,
        "director": film.director,
        "distributor": film.distributor,
        "url": film.url,
        "poster": film.poster_url,
        "panel": film.panel_url,
        "trailer": details.trailer_url if details else "",
        "certificate": _certificate(film.certificate),
        "content_descriptors": [_certificate(c) for c in film.content_descriptors],
        "film_attributes": [_attribute(a) for a in film.film_attributes],
    }


def showing_dict(showing: Showing) -> dict[str, Any]:
    """Serialise one showing; the film is referenced by id."""
    session = showing.session
    return {
        "session_id": session.session_id,
        "film_id": showing.film.film_id,
        "start": session.start.isoformat(),
        "end": session.end.isoformat(),
        "screen": session.screen,
        "price": session.price,
        "sold_out": session.sold_out,
        "booking_available": session.booking_available,
        "wheelchair_available": session.wheelchair_available,
        "booking_url": session.booking_url,
        "attributes": [_attribute(a) for a in session.attributes],
    }


def programme_dict(
    showings: list[Showing], coming_soon: list[Film], details: dict[str, FilmDetails]
) -> dict[str, Any]:
    """Serialise a watchlist result, with each film listed once."""
    films: dict[str, dict[str, Any]] = {}
    for showing in showings:
        films.setdefault(showing.film.film_id, film_dict(showing.film, showing.details))
    for film in coming_soon:
        films.setdefault(film.film_id, film_dict(film, details.get(film.film_id)))
    return {
        "showings": [showing_dict(s) for s in showings],
        "coming_soon": [f.film_id for f in coming_soon],
        "films": films,
    }
