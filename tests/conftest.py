"""shared bits for the tests"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.fineday.const import (
    CONF_API_KEY,
    CONF_API_URL,
    CONF_CITY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SUBURB,
)

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://fineday.test"
KEY = "fd_" + "0" * 40


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """lets HA load custom_components/fineday"""
    yield


ENTRY_DATA = {
    CONF_API_URL: URL,
    CONF_API_KEY: KEY,
    CONF_LATITUDE: -41.2259,
    CONF_LONGITUDE: 174.8855,
    CONF_SUBURB: "Petone",
    CONF_CITY: "Lower Hutt",
}
UNIQUE_ID = "-41.2259,174.8855"
