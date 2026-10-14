"""sensor tests, using a recorded forecast"""

from __future__ import annotations

import json
from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.fineday.const import DOMAIN

from .conftest import ENTRY_DATA, KEY, UNIQUE_ID, URL, load


def _recorded_today() -> str:
    return load("forecast.json")["forecast"]["days"][0]["date"][:10]


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data=ENTRY_DATA, options={"daylight_only": True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory) -> None:
    # freeze the clock at 8am NZ on the fixture's first day
    freezer.move_to(datetime.fromisoformat(_recorded_today() + "T08:00:00+13:00"))
    aioclient_mock.get(f"{URL}/v1/forecast", json=load("forecast.json"))
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    # key goes in the header, never in the url
    _, url, _, headers = aioclient_mock.mock_calls[0]
    assert headers["X-API-Key"] == KEY
    assert "fd_" not in str(url)

    f = load("forecast.json")["forecast"]
    today = hass.states.get("sensor.fine_day_petone_lower_hutt_today")
    assert today is not None, [s.entity_id for s in hass.states.async_all()]
    assert today.state == f["days"][0]["verdict"].lower()  # yes/maybe/no, shown as Yes/Maybe/No
    assert today.attributes["headline"] in ("Yes, dry today.", "Maybe.", "No, not today.")
    assert today.attributes["morning"] == f["todayParts"][0]["summary"]
    assert "Open-Meteo" in today.attributes["attribution"]

    tomorrow = hass.states.get("sensor.fine_day_petone_lower_hutt_tomorrow")
    assert tomorrow.state == f["days"][1]["verdict"].lower()

    nxt = hass.states.get("sensor.fine_day_petone_lower_hutt_next_dry_window")
    if f["nextGoodWindow"]:
        assert nxt.state == datetime.fromisoformat(f["nextGoodWindow"]["start"] + "+13:00").astimezone().isoformat()
        assert nxt.attributes["window"].endswith(("am", "pm"))

    dry = hass.states.get("sensor.fine_day_petone_lower_hutt_dry_days_ahead")
    assert int(dry.state) == sum(1 for d in f["days"][1:] if d["verdict"] == "Yes")
    assert len(dry.attributes["days"]) == len(f["days"]) - 1

    # 2h later, should fetch again
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/v1/forecast", json=load("forecast.json"))
    freezer.tick(7201)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 1


async def test_revoked_key_starts_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    body = load("error_401.json") | {"error": "invalid_key"}
    aioclient_mock.get(f"{URL}/v1/forecast", status=401, text=json.dumps(body))
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_server_trouble_retries_later(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/v1/forecast", status=503, json={"success": False, "error": "unavailable", "message": "budget"})
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY
