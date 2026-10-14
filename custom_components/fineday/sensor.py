from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, FORECAST_TZ, VERDICTS
from .coordinator import FineDayConfigEntry, FineDayCoordinator

NZ = ZoneInfo(FORECAST_TZ)

# WMO codes, same labels as the app's hero card
CONDITIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Rain", 63: "Rain", 65: "Rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Snow", 73: "Snow", 75: "Snow", 77: "Snow grains", 80: "Rain showers", 81: "Rain showers",
    82: "Rain showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}
HEADLINES = {"yes": "Yes, dry today.", "maybe": "Maybe.", "no": "No, not today."}


def nz_time(s):
    # api times are local NZ without an offset, e.g. 2026-10-14T09:00:00
    if not s:
        return None
    return datetime.fromisoformat(s[:19]).replace(tzinfo=NZ)


def hm(dt):
    s = dt.strftime("%I:%M%p").lower()  # 09:00am
    return s[1:] if s.startswith("0") else s


def fmt_windows(windows):
    # "9:00am to 12:00pm" (the app drops the :00)
    return [f"{hm(nz_time(w['start']))} to {hm(nz_time(w['end']))}" for w in windows]


def find_day(data, offset):
    # days[0] *should* be today but go by date in case the cache straddled midnight
    days = data["forecast"].get("days", [])
    today = datetime.now(NZ).strftime("%Y-%m-%d")
    dates = [d["date"][:10] for d in days]
    i = dates.index(today) + offset if today in dates else offset
    return days[i] if i < len(days) else None


def day_summary(data, day):
    if not day:
        return None
    return data["forecast"].get("dayDetails", {}).get(day["date"][:10], {}).get("summary")


def days_ahead(data):
    today = datetime.now(NZ).strftime("%Y-%m-%d")
    return [d for d in data["forecast"].get("days", []) if d["date"][:10] > today]


def state_key(verdict):
    # server says Yes/Maybe/No, HA wants enum states lowercase (strings.json shows them as Yes/Maybe/No)
    return verdict.lower() if verdict else None


# ---- today ----

def today_state(data):
    d = find_day(data, 0)
    return state_key(d["verdict"] if d else data["forecast"].get("today"))


def today_attrs(data):
    f = data["forecast"]
    d = find_day(data, 0)
    parts = {p["name"].lower(): p["summary"] for p in f.get("todayParts", [])}
    return {
        "headline": HEADLINES.get(today_state(data) or "no"),
        "condition": CONDITIONS.get(f.get("weatherCode")),
        "morning": parts.get("morning"),
        "afternoon": parts.get("noon") or parts.get("afternoon"),  # engine calls it Noon
        "all_day": parts.get("all day"),
        "summary": day_summary(data, d),
        "dry_windows": fmt_windows(d["windows"]) if d else [],
        "temperature": f.get("temperature"),
        "wind_speed_kmh": f.get("windSpeed"),
        "humidity": f.get("humidity"),
        "location": f.get("locationName"),
        "forecast_fetched": data.get("meta", {}).get("fetchedAt"),
    }


# ---- tomorrow ----

def tomorrow_state(data):
    d = find_day(data, 1)
    return state_key(d["verdict"]) if d else None


def tomorrow_attrs(data):
    d = find_day(data, 1)
    if not d:
        return {}
    return {
        "date": d["date"][:10],
        "summary": day_summary(data, d),
        "dry_windows": fmt_windows(d["windows"]),
        "temperature": d.get("temperature"),
        "wind_speed_kmh": d.get("windSpeed"),
        "humidity": d.get("humidity"),
    }


# ---- next window / dry days ----

def next_window_state(data):
    w = data["forecast"].get("nextGoodWindow")
    return nz_time(w["start"]) if w else None


def next_window_attrs(data):
    w = data["forecast"].get("nextGoodWindow")
    if not w:
        return {}
    start, end = nz_time(w["start"]), nz_time(w["end"])
    return {
        "end": end.isoformat(),
        "hours": round((end - start).total_seconds() / 3600, 1),
        "window": fmt_windows([w])[0],
    }


def dry_days_state(data):
    return sum(1 for d in days_ahead(data) if d["verdict"] == "Yes")


def dry_days_attrs(data):
    ahead = days_ahead(data)
    return {
        "days": [{"date": d["date"][:10], "verdict": d["verdict"], "dry_windows": fmt_windows(d["windows"])} for d in ahead],
        "maybe_days": sum(1 for d in ahead if d["verdict"] == "Maybe"),
    }


@dataclass(frozen=True, kw_only=True)
class FineDaySensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]
    attrs_fn: Callable[[dict], dict]


SENSORS = (
    FineDaySensorDescription(key="today", translation_key="today", device_class=SensorDeviceClass.ENUM,
                             options=VERDICTS, value_fn=today_state, attrs_fn=today_attrs),
    FineDaySensorDescription(key="tomorrow", translation_key="tomorrow", device_class=SensorDeviceClass.ENUM,
                             options=VERDICTS, value_fn=tomorrow_state, attrs_fn=tomorrow_attrs),
    FineDaySensorDescription(key="next_dry_window", translation_key="next_dry_window",
                             device_class=SensorDeviceClass.TIMESTAMP, value_fn=next_window_state,
                             attrs_fn=next_window_attrs),
    FineDaySensorDescription(key="dry_days", translation_key="dry_days", native_unit_of_measurement="days",
                             value_fn=dry_days_state, attrs_fn=dry_days_attrs),
)


async def async_setup_entry(hass: HomeAssistant, entry: FineDayConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(FineDaySensor(coordinator, desc) for desc in SENSORS)


class FineDaySensor(CoordinatorEntity[FineDayCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = "Forecast data by Open-Meteo.com, places by LINZ (CC BY 4.0), scored by Fine Day"
    # these change every fetch, don't want them filling up the recorder
    _unrecorded_attributes = frozenset({"days", "dry_windows", "summary", "morning", "afternoon", "all_day"})
    entity_description: FineDaySensorDescription

    def __init__(self, coordinator: FineDayCoordinator, desc: FineDaySensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{desc.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=f"Fine Day {coordinator.label}",
            manufacturer="SumnerD",
            model="Drying forecast",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.sumnerd.co.nz/fineday/",
        )

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        return self.entity_description.attrs_fn(self.coordinator.data)
