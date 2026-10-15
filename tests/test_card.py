"""the dashboard card: the file we serve and the place lookup it uses"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.fineday.const import DOMAIN

from .conftest import ENTRY_DATA, KEY, UNIQUE_ID, URL, load

TODAY = "sensor.fine_day_petone_lower_hutt_today"


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, options=None) -> MockConfigEntry:
    aioclient_mock.get(f"{URL}/v1/forecast", json=load("forecast.json"))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data=ENTRY_DATA,
                            options={"daylight_only": True} if options is None else options)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _ask(ws, n, entity_id):
    await ws.send_json({"id": n, "type": "fineday/place", "entity_id": entity_id})
    return await ws.receive_json()


async def test_place_for_the_card(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_ws_client) -> None:
    await _setup(hass, aioclient_mock, {"daylight_only": False})
    ws = await hass_ws_client(hass)

    msg = await _ask(ws, 1, TODAY)
    assert msg["success"], msg
    assert msg["result"] == {
        "latitude": -41.2259,
        "longitude": 174.8855,
        "suburb": "Petone",
        "city": "Lower Hutt",
        "label": "Petone, Lower Hutt",
        "daylight_only": False,
    }
    assert KEY not in str(msg) and URL not in str(msg)  # the key and server stay in HA

    # any of the place's sensors will do
    msg = await _ask(ws, 2, "sensor.fine_day_petone_lower_hutt_dry_days_ahead")
    assert msg["result"]["suburb"] == "Petone"


async def test_place_not_ours(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_ws_client) -> None:
    await _setup(hass, aioclient_mock)
    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    reg = er.async_get(hass)
    someone_elses = reg.async_get_or_create("sensor", "other", "a", config_entry=other).entity_id
    no_entry = reg.async_get_or_create("sensor", "other", "b").entity_id
    ws = await hass_ws_client(hass)

    for n, entity_id in enumerate(["sensor.nope", someone_elses, no_entry], start=1):
        msg = await _ask(ws, n, entity_id)
        assert not msg["success"]
        assert msg["error"]["code"] == "not_found"


async def test_place_for_a_read_only_user(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_ws_client,
                                          hass_read_only_access_token) -> None:
    # dashboards get shown to non admins too
    await _setup(hass, aioclient_mock)
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    msg = await _ask(ws, 1, TODAY)
    assert msg["success"], msg
    assert msg["result"]["daylight_only"] is True


async def test_card_is_served(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_client_no_auth) -> None:
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")  # the real one needs the frontend package, which the tests don't have
    with patch("custom_components.fineday.add_extra_js_url") as add_js:
        await _setup(hass, aioclient_mock)

    add_js.assert_called_once()
    url = add_js.call_args[0][1]
    assert url == "/fineday/fineday-card.js?v=" + (await async_get_integration(hass, DOMAIN)).version

    client = await hass_client_no_auth()
    resp = await client.get(url)
    assert resp.status == 200
    js = await resp.text()
    assert 'customElements.define("fineday-card"' in js
    assert "fineday/place" in js


async def test_no_frontend_no_card(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    # HA without the frontend (just the tests really) still sets up fine, just no card
    with patch("custom_components.fineday.add_extra_js_url") as add_js:
        entry = await _setup(hass, aioclient_mock)
    add_js.assert_not_called()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(TODAY) is not None
