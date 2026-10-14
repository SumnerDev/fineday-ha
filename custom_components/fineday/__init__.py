"""Fine Day - is it a good day to get the washing out."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import FineDayApi
from .const import CONF_API_KEY, CONF_API_URL
from .coordinator import FineDayConfigEntry, FineDayCoordinator

PLATFORMS = [Platform.SENSOR]


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
