"""Fine Day - is it a good day to get the washing out."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import FineDayApi
from .const import (
    CONF_API_KEY,
    CONF_API_URL,
    CONF_CITY,
    CONF_DAYLIGHT_ONLY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SUBURB,
    DOMAIN,
)
from .coordinator import FineDayConfigEntry, FineDayCoordinator, place_label

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL = "/fineday/fineday-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "fineday-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    websocket_api.async_register_command(hass, ws_place)

    # the dashboard card. loaded on every page so it's just there in Add card,
    # nobody has to touch their resources. a real HA always has the frontend, the tests don't
    if "frontend" in hass.config.components:
        version = (await async_get_integration(hass, DOMAIN)).version
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_FILE), True)])
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")  # new version, new url, so no stale card
    return True


@callback
@websocket_api.websocket_command({vol.Required("type"): "fineday/place", vol.Required("entity_id"): str})
def ws_place(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    # the card asks where one of our sensors is so it can show the same place. not the key, obviously
    ent = er.async_get(hass).async_get(msg["entity_id"])
    entry = hass.config_entries.async_get_entry(ent.config_entry_id) if ent and ent.config_entry_id else None
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Not a Fine Day sensor")
        return
    connection.send_result(msg["id"], {
        "latitude": entry.data[CONF_LATITUDE],
        "longitude": entry.data[CONF_LONGITUDE],
        "suburb": entry.data[CONF_SUBURB],
        "city": entry.data.get(CONF_CITY, ""),
        "label": place_label(entry.data[CONF_SUBURB], entry.data.get(CONF_CITY, "")),
        "daylight_only": entry.options.get(CONF_DAYLIGHT_ONLY, True),
    })


async def async_setup_entry(hass: HomeAssistant, entry: FineDayConfigEntry) -> bool:
    api = FineDayApi(async_get_clientsession(hass), entry.data[CONF_API_URL], entry.data[CONF_API_KEY])
    coordinator = FineDayCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # refresh just after midnight otherwise "today" is yesterday for up to 2h
    @callback
    def _midnight(_now):
        hass.async_create_task(coordinator.async_request_refresh())

    entry.async_on_unload(async_track_time_change(hass, _midnight, hour=0, minute=1, second=0))
    entry.async_on_unload(entry.add_update_listener(_reload))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: FineDayConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FineDayConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
