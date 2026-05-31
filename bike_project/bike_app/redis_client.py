"""
redis_client.py
─────────────────────────────────────────────────────────────────────────────
Centralised Redis helper for the bike app.

Key schema
──────────
  trip:<id>:specs    → Hash  { bikename, capacity, mileage,
                                fuel_consumed, fuel_cost, total_time }
"""
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


def delete_bike_specs(trip_id: int) -> None:
    """Remove the entire hash — called when a trip is deleted."""
    _redis.delete(_specs_key(trip_id))
