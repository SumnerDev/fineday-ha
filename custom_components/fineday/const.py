from datetime import timedelta

DOMAIN = "fineday"

# prefilled on the setup screen so people only need their key
DEFAULT_API_URL = "https://fineday-api.sumnerd.co.nz"

CONF_API_URL = "api_url"
CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_SUBURB = "suburb"
CONF_CITY = "city"
CONF_DAYLIGHT_ONLY = "daylight_only"

# server caches each place for 2h anyway, no point asking more often
UPDATE_INTERVAL = timedelta(hours=2)

KEY_CONTACT = "hello@sumnerd.co.nz"
FORECAST_TZ = "Pacific/Auckland"

VERDICTS = ["yes", "maybe", "no"]
