# Weather-Aware Truck Routing

**Live demo:** https://weather-aware-truck-routing-jade.vercel.app

**Demo video (7 min, narrated):** [docs/weather-aware-truck-routing-demo.mp4](docs/weather-aware-truck-routing-demo.mp4). It covers planning a trip, a storm scenario where the fastest route isn't the safest, the core code, and the tests.

A React + Django app that helps a truck driver pick the safest route. Given an origin, destination, departure time and load weight, it builds three route options, forecasts the weather at checkpoints along each one for the time the truck will actually be there, scores the risk, and recommends a route.

All third-party services are free and need no API keys:

| Purpose | Service |
| --- | --- |
| Geocoding | [Nominatim](https://nominatim.org/) (OpenStreetMap) |
| Routing | [OSRM](https://project-osrm.org/) public server |
| Weather | [Open-Meteo](https://open-meteo.com/) hourly forecast |
| Map | [Leaflet](https://leafletjs.com/) + OpenStreetMap tiles |

## Running locally

Requirements: Python 3.11+ and Node 18+.

```bash
# Backend (http://127.0.0.1:8000)
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt
python manage.py runserver

# Frontend (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to Django, so no CORS setup is needed.

### Tests

```bash
cd backend && source venv/bin/activate
python manage.py test routing
```

The tests cover every risk threshold boundary, the load rules, checkpoint sampling, ETA calculation, route ranking and the API's error responses. External services are mocked.

### Configuration

All optional, via environment variables:

| Variable | Default |
| --- | --- |
| `DJANGO_SECRET_KEY` | random key per process (the app stores no sessions or signed data) |
| `DJANGO_DEBUG` | `0` (set to `1` locally for Django error pages) |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `OSRM_URL` | `https://router.project-osrm.org` |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org/search` |
| `OPEN_METEO_URL` | `https://api.open-meteo.com/v1/forecast` |
| `HTTP_USER_AGENT` | `weather-aware-truck-routing/1.0` (Nominatim requires an identifying agent) |

### Deploying

The app is hosted on [Vercel](https://vercel.com) as a single project: the React build is served as static files, and `api/plan.py` runs the Django app as a Python function at `/api/plan`. The settings live in `vercel.json`, and Python dependencies come from the root `requirements.txt`.

```bash
vercel deploy --prod
```

## How it works

1. **Geocode** origin and destination with Nominatim.
2. **Route options.** Ask OSRM for up to three routes. OSRM often returns fewer, so the remainder come from routing through waypoints offset to either side of the direct line. Candidates more than 1.6× the fastest route's distance, or overlapping an existing route by more than 80%, are discarded.
3. **Truck ETAs.** OSRM's public server only has a car profile, so each road segment is capped at 65 mph. ETAs come from the cumulative segment times along the route.
4. **Checkpoints** are placed every 10, 25 or 50 miles (user's choice), plus the destination.
5. **Weather at ETA.** Each checkpoint gets the Open-Meteo forecast for its estimated arrival time. Wind uses the nearest hour. Rain (rain + showers) and snowfall use the hour ending at or after the ETA, because Open-Meteo reports precipitation as the total of the preceding hour.
6. **Risk** is the worst of wind, rain and snow, after the load rules are applied.
7. **Score and recommend** (below).
8. **Heatmap.** A grid of cells within about 40 miles of any route, with the forecast risk for each hour from departure to 48 hours later. The window is cut short if the forecast ends sooner.

Requests that can't succeed (departure in the past or after the forecast ends, origin and destination identical or under a mile apart) are rejected before the slow API calls. If an extra detour route fails to load, the plan continues with the routes it already has. Checkpoint and heatmap weather is fetched in parallel.

### Risk rules

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Shared boundaries belong to the higher band (0.25 in/hr of rain is High). The top values that the table writes as inclusive stay in their band: 1.00 in/hr of rain and 3.0 in/hr of snow are Severe.

Load rules:

- Wind ≥ 55 mph → No Travel for any load
- Wind 45–54 mph and load > 30,000 lb → No Travel
- Wind 35–44 mph and load > 40,000 lb → Severe

### Recommendation

Each stretch between two checkpoints counts at the worse of its two endpoint risks. This is deliberately cautious. Routes are then ranked by:

1. Fewest **No Travel** miles
2. Fewest **Severe** miles
3. Fewest **High** miles
4. Lowest **average risk** (distance-weighted, Low = 0 … No Travel = 4)
5. Shortest **travel time**

Step 1 is an addition to the spec's list: a route with No Travel miles should never beat one that only has Severe miles. Values are compared at the precision shown to the driver (0.1 mi, 0.01 average risk, whole minutes), so two routes 20 seconds apart count as tied. The response explains the deciding criterion, for example *"Route A has the fewest Severe miles: 0.0 mi vs 35.2 mi on Route B."* If even the best route crosses No Travel conditions, the app also warns the driver to consider delaying.

## API

`POST /api/plan`

```json
{
  "origin": "Chicago, IL",
  "destination": "Minneapolis, MN",
  "departure": "2026-10-18T14:00:00Z",
  "load_lb": 45000,
  "interval_mi": 25
}
```

`interval_mi` must be 10, 25 or 50 (default 25). The response contains:

- `recommended` and `recommendation` (`reason`, `warning`)
- `routes[]`: distance, duration, arrival, rank, miles per risk level, average and worst risk, geometry, and `checkpoints[]` (mile, position, ETA, wind, rain, snow, risk, contributing factors)
- `heatmap`: grid cells with hourly risk, wind, rain and snow for hours 0–48

Errors return `{"detail": "..."}`: 400 for problems the user can fix (unknown place, past departure, trip beyond the forecast window) and 502 when a third-party service fails or returns an unexpected response. Invalid fields return DRF's per-field errors with status 400.

## Limitations

- **Car routing.** OSRM's public server doesn't know truck restrictions such as low bridges, weight limits or hazmat routes. Self-hosting OSRM with a truck profile, or using a commercial truck-routing API, would fix this.
- **No hours-of-service breaks.** ETAs assume continuous driving.
- **Forecast horizon.** Open-Meteo forecasts 16 days, counted from 00:00 UTC today, so trips must arrive before that window ends.
- **Free-tier limits.** Open-Meteo allows about 10,000 location lookups per day. One plan uses a few hundred (checkpoints are de-duplicated across routes), so heavy use will hit the limit. Nominatim allows one request per second. The backend spaces its requests accordingly, but only within one process, so running several server workers would need a shared limiter such as Redis.
- **Response time.** A plan takes about 5–8 seconds, mostly spent waiting on the external APIs.

## Project structure

```
api/plan.py          Vercel entry point for the Django API
vercel.json          Vercel build and function settings
requirements.txt     Python dependencies
backend/
  config/            Django settings and URL root
  routing/
    risk.py          Threshold and load rules
    geo.py           Distance, interpolation, checkpoint sampling
    clients.py       Nominatim, OSRM and Open-Meteo clients
    planner.py       Route options, ETAs, weather, scoring, heatmap
    serializers.py   Request validation
    views.py         POST /api/plan
    tests/
frontend/
  src/
    App.jsx
    api.js
    risk.js          Risk colours and formatters
    components/      TripForm, Recommendation, RouteCards, CheckpointTable, RouteMap
```
