"""
redis_client.py
─────────────────────────────────────────────────────────────────────────────
Centralised Redis helper for the bike app.

Key schema
──────────
  trip:<id>:specs      → Hash  { bikename, capacity, mileage,
                                  fuel_consumed, fuel_cost, total_time }
  trip:<id>:fuel_stops  → String (JSON)  Pre-calculated 70% refuel point
                                         and nearby petrol stations.
"""
import json
import redis
from django.conf import settings

# Single connection pool — shared across the process
_redis = redis.from_url(
    getattr(settings, 'REDIS_URL', 'redis://localhost:6379'),
    decode_responses=True   # return str, not bytes
)

SPECS_TTL = 60 * 60 * 24 * 7   # 7 days


def _specs_key(trip_id: int) -> str:
    return f"trip:{trip_id}:specs"


def save_bike_specs(trip_id: int, data: dict) -> None:
    """
    Write (or merge) bike spec fields into the Redis hash for a trip.
    All values are coerced to strings.
    Automatically refreshes the 7-day TTL.
    """
    key = _specs_key(trip_id)
    _redis.hset(key, mapping={k: str(v) for k, v in data.items()})
    _redis.expire(key, SPECS_TTL)


def get_bike_specs(trip_id: int) -> dict:
    """
    Retrieve all fields from the bike spec hash.
    Returns an empty dict if nothing is stored yet.
    """
    return _redis.hgetall(_specs_key(trip_id))


# ─── Fuel Stops (pre-calculated 70% refuel point + nearby pumps) ─────────────

def _fuel_stops_key(trip_id: int) -> str:
    return f"trip:{trip_id}:fuel_stops"


def save_fuel_stops(trip_id: int, data: dict) -> None:
    """
    Cache the pre-calculated 70% refuel point and nearby petrol stations.
    Stored as a JSON string (not a hash) because the structure is nested.
    """
    key = _fuel_stops_key(trip_id)
    _redis.set(key, json.dumps(data))
    _redis.expire(key, SPECS_TTL)


def get_fuel_stops(trip_id: int) -> dict:
    """
    Retrieve the pre-calculated fuel stops payload from Redis.
    Returns an empty dict if nothing is cached.
    """
    raw = _redis.get(_fuel_stops_key(trip_id))
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


# ─── Cleanup ──────────────────────────────────────────────────────────────────

def delete_bike_specs(trip_id: int) -> None:
    """Remove all Redis keys for a trip — called when a trip is deleted."""
    _redis.delete(_specs_key(trip_id))
    _redis.delete(_fuel_stops_key(trip_id))
