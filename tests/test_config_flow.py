"""Tests for the config flow and the watchlist subentry flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.vue_cinemas.config_flow import DEFAULT_WATCHLIST
from custom_components.vue_cinemas.const import DOMAIN, SUBENTRY_WATCHLIST

from .conftest import CINEMAS_URL, load, mock_token, subentry_id


async def test_user_flow(hass: HomeAssistant, api: AiohttpClientMocker) -> None:
    """Picking a cinema creates an entry with a default watchlist."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cinema_id": "1001"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vue Amersfoort"
    assert result["data"] == {"cinema_id": "1001", "cinema_name": "Amersfoort"}
    assert result["result"].unique_id == "1001"
    subentries = list(result["result"].subentries.values())
    assert [(s.title, s.subentry_type) for s in subentries] == [
        ("Alles", SUBENTRY_WATCHLIST)
    ]
    assert dict(subentries[0].data) == DEFAULT_WATCHLIST
    await hass.async_block_till_done()


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A connection problem shows an error; retrying recovers."""
    mock_token(aioclient_mock)
    aioclient_mock.get(CINEMAS_URL, status=503, text="down")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(CINEMAS_URL, json=load("cinemas.json"))
    assert result["data_schema"].schema == {}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cinema_id": "1006"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vue Alkmaar"


async def test_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Configured cinemas are hidden; all configured aborts."""
    config_entry.add_to_hass(hass)
    mock_token(aioclient_mock)
    aioclient_mock.get(CINEMAS_URL, json=load("cinemas.json"))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    options = result["data_schema"].schema["cinema_id"].config["options"]
    assert [o["value"] for o in options] == ["1006", "1007"]
    for cinema in ("1006", "1007"):
        MockConfigEntry(domain=DOMAIN, unique_id=cinema).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "all_configured"


async def test_unique_id_race(
    hass: HomeAssistant, config_entry: MockConfigEntry, api: AiohttpClientMocker
) -> None:
    """A cinema configured while the form was open aborts."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cinema_id": "1001"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_add_watchlist(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """A watchlist is created from the cinema's real options."""
    result = await hass.config_entries.subentries.async_init(
        (setup_entry.entry_id, SUBENTRY_WATCHLIST), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    assert schema["screens"].config["options"] == [
        "Zaal 1", "Zaal 2", "Zaal 3", "Zaal 4", "Zaal 5"
    ]
    assert schema["genres"].config["options"] == ["Horror", "Thriller"]
    assert "D-Box" in schema["attributes"].config["options"]
    assert "Singleseatrule" not in schema["attributes"].config["options"]

    user_input = {
        "name": "Alles",
        "mode": "all",
        "days_ahead": 14.0,
        "screens": ["Zaal 1"],
        "genres": [],
        "attributes": ["D-Box"],
        "max_certificate": "16",
        "hide_sold_out": True,
        "include_coming_soon": False,
    }
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )
    assert result["errors"] == {"name": "name_exists"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**user_input, "name": "  "}
    )
    assert result["errors"] == {"name": "name_required"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**user_input, "name": "D-Box"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    sub = setup_entry.subentries[subentry_id(setup_entry, "D-Box")]
    assert sub.data["days_ahead"] == 14
    assert sub.data["screens"] == ["Zaal 1"]
    assert hass.states.get("sensor.vue_amersfoort_d_box_showings") is not None


async def test_reconfigure_watchlist(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """A watchlist can be renamed and refiltered."""
    hass.config_entries.async_add_subentry(
        setup_entry,
        ConfigSubentry(
            subentry_type=SUBENTRY_WATCHLIST,
            title="Kids",
            data={**DEFAULT_WATCHLIST, "screens": ["Zaal 99"]},
            unique_id=None,
        ),
    )
    await hass.async_block_till_done()
    sub_id = subentry_id(setup_entry, "Kids")
    result = await setup_entry.start_subentry_reconfigure_flow(hass, sub_id)
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    # A saved value no longer offered by the cinema stays selectable.
    assert "Zaal 99" in schema["screens"].config["options"]
    base = {**DEFAULT_WATCHLIST, "days_ahead": 3}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**base, "name": "alles"}
    )
    assert result["errors"] == {"name": "name_exists"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**base, "name": ""}
    )
    assert result["errors"] == {"name": "name_required"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**base, "name": "Kinderen", "max_certificate": "6"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    sub = setup_entry.subentries[sub_id]
    assert sub.title == "Kinderen"
    assert sub.data["max_certificate"] == "6"
    assert sub.data["screens"] == []


async def test_watchlist_entry_not_loaded(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Watchlists need a loaded cinema for their options."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_WATCHLIST), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"
    result = await config_entry.start_subentry_reconfigure_flow(
        hass, subentry_id(config_entry)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"
