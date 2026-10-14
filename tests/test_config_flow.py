"""config flow tests"""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.fineday.const import CONF_API_KEY, CONF_API_URL, CONF_DAYLIGHT_ONLY, DOMAIN

from .conftest import ENTRY_DATA, KEY, UNIQUE_ID, URL, load


async def test_full_flow_with_pick(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/v1/search", json=load("search_many.json"))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: URL + "/", CONF_API_KEY: KEY})
    assert result["step_id"] == "place"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "sandy bay"})
    assert result["step_id"] == "pick"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"place": "1"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    picked = load("search_many.json")["results"][1]
    assert result["data"][CONF_API_URL] == URL  # trailing slash trimmed
    assert result["data"]["suburb"] == picked["suburb"]
    assert result["options"] == {CONF_DAYLIGHT_ONLY: True}


async def test_pick_none_of_these_goes_back(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/v1/search", json=load("search_many.json"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: URL, CONF_API_KEY: KEY})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "sandy bay"})
    assert result["step_id"] == "pick"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"place": "again"})
    assert result["step_id"] == "place"  # back to the search, key kept


async def test_single_match_skips_pick(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/v1/search", json=load("search_one.json"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: URL, CONF_API_KEY: KEY})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "petone"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Petone, Lower Hutt"


async def test_bad_key_names_the_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/v1/search", status=401, json=load("error_401.json"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: URL, CONF_API_KEY: "fd_bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["description_placeholders"]["contact"] == "hello@sumnerd.co.nz"


async def test_unreachable_and_bad_url(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/v1/search", exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: URL, CONF_API_KEY: KEY})
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: "fineday.test", CONF_API_KEY: KEY})
    assert result["errors"] == {CONF_API_URL: "invalid_url"}


async def test_second_place_reuses_key_and_refuses_duplicate(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data=ENTRY_DATA).add_to_hass(hass)
    aioclient_mock.get(f"{URL}/v1/search", json=load("search_one.json"))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "place"  # no key screen the second time

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "petone"})
    # same Petone as the entry we already have, so it should bail
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_reauth_updates_the_key(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{URL}/v1/search", json=load("search_one.json"))
    aioclient_mock.get(f"{URL}/v1/forecast", json=load("forecast.json"))

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "fd_new"})
    await hass.async_block_till_done()  # saving the key reloads the entry, let that finish
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "fd_new"


async def test_key_locked_elsewhere(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/v1/search", status=403,
                       json={"success": False, "error": "address_not_allowed", "message": "locked"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_URL: URL, CONF_API_KEY: KEY})
    assert result["errors"] == {"base": "address_blocked"}
