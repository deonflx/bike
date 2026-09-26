# Redis + PostGIS Hybrid Storage Architecture

## Overview

We will redesign the data layer so every piece of data lives in the store that makes the most sense for it semantically and architecturally.

## Final Data Split

| Data | Store | Reason |
|---|---|---|
| `starting_point` (lat/lng) | **PostGIS** `PointField` | Spatial queries, indexing |
| `destination_point` (lat/lng) | **PostGIS** `PointField` | Spatial queries, indexing |
| `starting_name` (e.g. "Bangalore") | **PostGIS** `CharField` | Human-readable label |
| `destination_name` (e.g. "Mysore") | **PostGIS** `CharField` | Human-readable label |
| `created_at` | **PostGIS** | Standard timestamp |
| `RouteWeather.location` (lat/lng) | **PostGIS** `PointField` | Tied to geography, spatially reusable |
| `RouteWeather.description` | **PostGIS** `TextField` | Linked to its location |
| `RouteWeather.recorded_at` | **PostGIS** | For cache invalidation |
| `current_location` (live GPS) | **PostGIS** `PointField` | Already there, unchanged |
| `bikename` | **Redis** Hash | Bike spec, not spatial |
| `fueltank_capacity` | **Redis** Hash | Calculated, not spatial |
| `average_mileage` | **Redis** Hash | Calculated, not spatial |
| `ai_fuel_consumed` | **Redis** Hash | Derived calculation |
| `ai_fuel_cost` | **Redis** Hash | Derived calculation |
| `ai_total_time` | **Redis** Hash | Derived calculation |

---

## Proposed Changes

### Component 1 — Database Models (PostGIS)

#### [MODIFY] `bike_app/models.py`

**`BikeTrip` model changes:**
- Remove `fueltank_capacity` and `average_mileage` (moving to Redis).
- Remove `starting_location` and `destination_location` text fields.
- Add `starting_name = CharField(max_length=200)` — human-readable label.
- Add `destination_name = CharField(max_length=200)` — human-readable label.
- Add `starting_point = PointField(null=True)` — geocoded lat/lng.
- Add `destination_point = PointField(null=True)` — geocoded lat/lng.

**New `RouteWeather` model:**
```python
class RouteWeather(models.Model):
    bike_trip    = models.ForeignKey(BikeTrip, on_delete=models.CASCADE, related_name='weather_points')
    location     = PointField(srid=4326)           # exact GPS of weather sample
    description  = models.TextField()               # AI/Open-Meteo weather text
    recorded_at  = models.DateTimeField(auto_now_add=True)
```

#### [NEW] Migration
- Run `python manage.py makemigrations` and `python manage.py migrate` after model changes.

---

### Component 2 — Redis Client Utility

#### [NEW] `bike_app/redis_client.py`
A small, reusable module that handles all Redis operations:

```python
import redis, json
from django.conf import settings

r = redis.from_url(settings.REDIS_URL)

def save_bike_specs(trip_id: int, data: dict):
    """Store bike specs hash in Redis with 7-day TTL"""
    key = f"trip:{trip_id}:specs"
    r.hset(key, mapping={k: str(v) for k, v in data.items()})
    r.expire(key, 60 * 60 * 24 * 7)  # 7 days TTL

def get_bike_specs(trip_id: int) -> dict:
    """Retrieve bike specs hash from Redis"""
    return r.hgetall(f"trip:{trip_id}:specs")
```

#### [MODIFY] `settings.py`
Add:
```python
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
```

---

### Component 3 — Views

#### [MODIFY] `views.py` — `bike_submit`
1. Use **Nominatim** to geocode `starting_name` → `Point(lng, lat)` and `destination_name` → `Point(lng, lat)`.
2. Call **Gemini** to get bike `capacity` and `mileage`.
3. Save slim `BikeTrip` (only names + spatial points) to **PostGIS**.
4. Call `save_bike_specs(trip.id, { bikename, capacity, mileage })` to write to **Redis**.

#### [MODIFY] `views.py` — `customer_detail`
1. Fetch `BikeTrip` from PostGIS (names + spatial points).
2. Call `get_bike_specs(trip.id)` to fetch bike data from Redis.
3. Pass both to the template as context.

#### [MODIFY] `views.py` — `generate_customer_summary`
1. Fetch spatial points from PostGIS.
2. Fetch bike specs from Redis.
3. Fetch weather from the `RouteWeather` table (filtered by `bike_trip`).
4. If no weather exists yet, call Open-Meteo API at 3 sampled points along the route and save results to `RouteWeather` (PostGIS).
5. Call **Gemini** with all combined data to generate summary.
6. Store `ai_fuel_consumed`, `ai_fuel_cost`, `ai_total_time` back to Redis: `save_bike_specs(trip.id, { ...insights })`.
7. Return the formatted HTML.

---

### Component 4 — Templates

#### [MODIFY] `customer_detail.html`
- Update specs cards to read from the `bike_specs` dict (Redis) passed in context.
- Display `starting_name` and `destination_name` from PostGIS.

#### [MODIFY] `customer_list.html`
- Table rows display `starting_name` and `destination_name` from PostGIS.

---

## Data Flow Diagram

```
[User fills form]
      │
      ▼
[Nominatim] ──geocodes──▶ [PostGIS: starting_point, destination_point]
[Gemini API] ──specs──▶   [Redis:   trip:<id>:specs { capacity, mileage }]

[Customer Detail page loads]
      │
      ├──▶ [PostGIS] → fetch BikeTrip (name + spatial points)
      ├──▶ [Redis]   → fetch specs (capacity, mileage)
      └──▶ [AI summary endpoint]
                │
                ├──▶ [PostGIS RouteWeather] → fetch cached weather (or call Open-Meteo & save)
                ├──▶ [Gemini] → calculate fuel cost, time, insights
                └──▶ [Redis] → cache ai_fuel_cost, ai_total_time back
```

---

## Verification Plan

1. Submit a new trip → check PostgreSQL: `SELECT * FROM bike_app_biketrip;` — should have Point data, NO capacity/mileage columns.
2. Check Redis: `redis-cli HGETALL trip:1:specs` — should show bikename, capacity, mileage.
3. Check PostGIS: `SELECT * FROM bike_app_routeweather;` — should show weather points after visiting a customer detail page.
4. Confirm customer detail page renders all fields correctly from both stores.

---

## Open Questions

> [!IMPORTANT]
> **Is the Redis server installed and running?** You have the Python `redis` client, but the server must be running on port 6379. Run `redis-cli ping` — if you get `PONG` we can start immediately. If not, let me know and I will set it up first (via WSL or a Windows installer).

> [!NOTE]
> This plan requires a **database migration** that will DROP the `fueltank_capacity` and `average_mileage` columns and convert location text fields to spatial Points. **Any existing records will lose their specs data** (it was text anyway). We can migrate existing records manually if needed.
