# Fine Day for Home Assistant

Is today a good day to get the washing out? [Fine Day](https://www.sumnerd.co.nz/fineday/) scores every daylight hour on rain, humidity, temperature and wind and gives you a Yes / Maybe / No. This brings that into HA as sensors so you can actually do something with it (nag me when tomorrow's a Yes, that kind of thing).

NZ only, same as the app. Only after the card on your dashboard? That doesn't need a key, see [On your dashboard](#on-your-dashboard).

<p>
  <img src="https://raw.githubusercontent.com/SumnerDev/fineday-ha/master/images/card-light.png" alt="The Fine Day card for Petone, light theme: No, not today, with tomorrow and the next few days below" width="49%">
  <img src="https://raw.githubusercontent.com/SumnerDev/fineday-ha/master/images/card-dark.png" alt="The same card in the dark theme" width="49%">
</p>

## You need a key

The forecast is worked out on the Fine Day server, so you need an API key. Email **hello@sumnerd.co.nz** about Fine Day and I'll sort you one.

## Install

Needs Home Assistant 2025.3 or newer.

**HACS**: click this, then Download, then restart HA.

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SumnerDev&repository=fineday-ha&category=integration)

Or in HACS open the three dots menu (top right) > Custom repositories, paste `https://github.com/SumnerDev/fineday-ha` and pick type Integration.

**Manual**: copy `custom_components/fineday` into your HA `config/custom_components/` folder and restart.

Then add it here, or go to Settings > Devices & services > Add integration > Fine Day:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=fineday)

The server address is already filled in (`https://fineday-api.sumnerd.co.nz`), so paste your key. Then either use your home location (Fine Day finds the suburb nearest the home you set in Home Assistant) or search for a place. Add more places the same way, it won't ask for the key again.

## Sensors

Per suburb, e.g. for Petone:

| Entity | State | Handy attributes |
|---|---|---|
| `sensor.fine_day_petone_lower_hutt_today` | Yes / Maybe / No | headline, condition, morning, afternoon (or all_day when it's dry right through), summary, dry_windows, temperature, wind_speed_kmh, humidity |
| `sensor.fine_day_petone_lower_hutt_tomorrow` | Yes / Maybe / No | summary, dry_windows, temperature... |
| `sensor.fine_day_petone_lower_hutt_next_dry_window` | when the next dry window starts | end, hours, window |
| `sensor.fine_day_petone_lower_hutt_dry_days_ahead` | number of Yes days in the next ~13 | days (each day's verdict + windows), maybe_days |

Today and Tomorrow show as Yes, Maybe or No, but underneath the state is `yes`, `maybe` or `no`, so use lowercase in automations and templates.

Updates every 2 hours and just after midnight. To turn off "daylight hours only", hit Configure on the Fine Day integration page. Moved, or picked the wrong Hillcrest? Delete that place there and add the right one, then fix the entity ids in your cards.

## Example automation

```yaml
alias: Washing tomorrow
triggers:
  - trigger: time
    at: "19:30:00"
conditions:
  - condition: state
    entity_id: sensor.fine_day_petone_lower_hutt_tomorrow
    state: "yes"
actions:
  - action: notify.mobile_app_my_phone
    data:
      title: Fine Day
      message: >
        Tomorrow's a Yes: {{ state_attr('sensor.fine_day_petone_lower_hutt_tomorrow', 'dry_windows') | join(', ') }}
```

## On your dashboard

### The Fine Day card

This is the Fine Day website in a Webpage card, so it doesn't need a key, or even the integration.

Easiest way: make it at [sumnerd.co.nz/fineday/card](https://www.sumnerd.co.nz/fineday/card/). Find your place (or use your location), check the preview, copy the code, then in HA edit your dashboard, add a Webpage card, hit Show code editor and paste it in.

Or by hand, paste this and change the place:

```yaml
type: iframe
url: https://www.sumnerd.co.nz/fineday/embed/?q=Petone&theme=auto
aspect_ratio: 120%
grid_options:
  rows: 8
```

`grid_options` sets the height in a sections view (the default for new dashboards) and `aspect_ratio` does it in a masonry view, each ignores the other. Shorter than that and you only see today.

Change `Petone` to your suburb, then check the name at the top of the card is the place you meant:

- Use your suburb, not the city. `q=Hamilton` on its own gets you Hamilton Central.
- Macrons are optional, `q=Taupo` finds Taupō, and Mt, Pt and St work too (`q=Mt+Eden`).
- If the name's used in more than one town, add the town after a comma: `q=Hillcrest,+Hamilton`. If that town hasn't got one, the card says so and tells you which towns have.
- Still not right? Give it the spot instead: `?lat=-41.2259&lon=174.8855&suburb=Petone`.

Other settings go on the end with `&`:

| Setting | What it does | Default |
|---|---|---|
| `theme` | `light`, `dark`, or `auto` to follow your device | `light` |
| `bg=transparent` | lets the dashboard show through behind it | off |
| `days` | how many days to list under today, 1 to 14 | 14 |
| `daylight=0` | scores every hour, not just sunrise to sunset | daylight only |
| `refresh` | minutes between refreshes, 10 to 1440 | 120 |

### Your own card

This one's built from the sensors, so it needs the integration and a key. Swap `petone_lower_hutt` for your place (Developer tools > States, search `fine_day`, if you're not sure):

```yaml
type: entities
title: Fine Day
entities:
  - entity: sensor.fine_day_petone_lower_hutt_today
    name: Today
  - entity: sensor.fine_day_petone_lower_hutt_tomorrow
    name: Tomorrow
  - entity: sensor.fine_day_petone_lower_hutt_next_dry_window
    name: Next dry window
  - entity: sensor.fine_day_petone_lower_hutt_dry_days_ahead
    name: Dry days ahead
```

Tap a row for the summary and dry windows.

## Notes

- If your key gets revoked or replaced, HA flags Fine Day under Settings > Devices & services and asks you for the new one.
- Each key has a daily request limit. Normal use is about 12 requests a day per suburb so you won't get near it.
- A key is for one household. The server notes the IP addresses a key's used from that day (wiped the next day), and after a few in a day it turns new ones away until midnight.
- What the server sees: your key, the suburb you picked (its centre point, not your address) and your IP address. Your home location only goes out if you pick "Use my home location", rounded to about 1 km, just to find the nearest suburb.
- Forecast data from [Open-Meteo](https://open-meteo.com), places from LINZ (CC BY 4.0).

## Licence

MIT, see [LICENSE](LICENSE). That covers the code here, not the Fine Day server.
