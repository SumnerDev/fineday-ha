from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FineDayApi, FineDayAuthError, FineDayError
from .const import CONF_CITY, CONF_DAYLIGHT_ONLY, CONF_LATITUDE, CONF_LONGITUDE, CONF_SUBURB, DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type FineDayConfigEntry = ConfigEntry[FineDayCoordinator]


def place_label(suburb: str, city: str) -> str:
    # same as the app - "Warkworth, Warkworth" is just "Warkworth"
    if not city or suburb.strip().lower() == city.strip().lower():
        return suburb
    return f"{suburb}, {city}"


class FineDayCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: FineDayConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FineDayConfigEntry, api: FineDayApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_SUBURB]}",
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.label = place_label(entry.data[CONF_SUBURB], entry.data.get(CONF_CITY, ""))

    async def _async_update_data(self) -> dict[str, Any]:
        e = self.config_entry
        try:
            return await self.api.forecast(
                e.data[CONF_LATITUDE],
                e.data[CONF_LONGITUDE],
                self.label,
                e.options.get(CONF_DAYLIGHT_ONLY, True),
            )
        except FineDayAuthError as err:
            # kicks off reauth so you just paste a new key in
            raise ConfigEntryAuthFailed(str(err)) from err
        except FineDayError as err:
            # TODO: one bad poll and it's all unavailable for up to 2h, should hang on to the last good forecast
            raise UpdateFailed(str(err)) from err
