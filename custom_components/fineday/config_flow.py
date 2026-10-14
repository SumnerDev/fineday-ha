from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FineDayAddressError, FineDayApi, FineDayAuthError, FineDayError, FineDayLimitError
from .const import (
    CONF_API_KEY,
    CONF_API_URL,
    CONF_CITY,
    CONF_DAYLIGHT_ONLY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SUBURB,
    DEFAULT_API_URL,
    DOMAIN,
    KEY_CONTACT,
)
from .coordinator import place_label

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class FineDayConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._url = DEFAULT_API_URL
        self._key = ""
        self._results: list[dict[str, Any]] = []

    def _api(self, url, key):
        return FineDayApi(async_get_clientsession(self.hass), url, key)

    async def _try_key(self, url, key):
        # a search proves the server is up AND the key works, health doesn't check the key
        try:
            await self._api(url, key).search("auckland")
        except FineDayAuthError:
            return "invalid_auth"
        except FineDayAddressError:
            return "address_blocked"
        except FineDayLimitError:
            return "rate_limited"
        except FineDayError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        # already got one place? reuse its server + key, straight to the suburb
        current = self._async_current_entries()
        if user_input is None and current:
            self._url = current[0].data[CONF_API_URL]
            self._key = current[0].data[CONF_API_KEY]
            return await self.async_step_place()

        errors = {}
        if user_input is not None:
            url = user_input[CONF_API_URL].strip().rstrip("/")
            key = user_input[CONF_API_KEY].strip()
            if not url.startswith(("https://", "http://")):
                errors[CONF_API_URL] = "invalid_url"
            elif err := await self._try_key(url, key):
                errors["base"] = err
            else:
                self._url, self._key = url, key
                return await self.async_step_place()

        schema = vol.Schema({
            vol.Required(CONF_API_URL, default=self._url): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(CONF_API_KEY): PASSWORD,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors,
                                    description_placeholders={"contact": KEY_CONTACT})

    async def async_step_place(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                self._results = await self._api(self._url, self._key).search(user_input["query"].strip())
            except FineDayAuthError:
                errors["base"] = "invalid_auth"
            except FineDayAddressError:
                errors["base"] = "address_blocked"
            except FineDayLimitError:
                errors["base"] = "rate_limited"
            except FineDayError:
                errors["base"] = "cannot_connect"
            else:
                if not self._results:
                    errors["query"] = "no_match"
                elif len(self._results) == 1:
                    return await self._make_entry(self._results[0])
                else:
                    return await self.async_step_pick()

        return self.async_show_form(step_id="place", data_schema=vol.Schema({vol.Required("query"): str}),
                                    errors=errors)

    async def async_step_pick(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input["place"] == "again":
                return await self.async_step_place()
            return await self._make_entry(self._results[int(user_input["place"])])

        opts = [SelectOptionDict(value=str(i), label=place_label(r["suburb"], r["city"]))
                for i, r in enumerate(self._results)]
        # server only sends back the first 20, so give people a way out
        opts.append(SelectOptionDict(value="again", label="None of these, search again"))
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema({
                vol.Required("place"): SelectSelector(SelectSelectorConfig(options=opts, mode=SelectSelectorMode.LIST))
            }),
        )

    async def _make_entry(self, place):
        lat, lon = float(place["latitude"]), float(place["longitude"])
        await self.async_set_unique_id(f"{lat:.4f},{lon:.4f}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=place_label(place["suburb"], place["city"]),
            data={
                CONF_API_URL: self._url,
                CONF_API_KEY: self._key,
                CONF_LATITUDE: lat,
                CONF_LONGITUDE: lon,
                CONF_SUBURB: place["suburb"],
                CONF_CITY: place["city"],
            },
            options={CONF_DAYLIGHT_ONLY: True},
        )

    # key got revoked / swapped -> HA asks for the new one
    async def async_step_reauth(self, entry_data) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            if err := await self._try_key(entry.data[CONF_API_URL], key):
                errors["base"] = err
            else:
                # update any other places on the same server too, saves doing it 3 times
                for other in self._async_current_entries():
                    if other.entry_id != entry.entry_id and other.data[CONF_API_URL] == entry.data[CONF_API_URL]:
                        self.hass.config_entries.async_update_entry(other, data={**other.data, CONF_API_KEY: key})
                        self.hass.config_entries.async_schedule_reload(other.entry_id)
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: key})

        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_API_KEY): PASSWORD}),
                                    errors=errors, description_placeholders={"contact": KEY_CONTACT})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FineDayOptionsFlow()


class FineDayOptionsFlow(OptionsFlow):
    # TODO: can't change the server address after setup yet, could go here
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_DAYLIGHT_ONLY, True)
        return self.async_show_form(step_id="init",
                                    data_schema=vol.Schema({vol.Required(CONF_DAYLIGHT_ONLY, default=current): bool}))
