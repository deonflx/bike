"""
redis_client.py
─────────────────────────────────────────────────────────────────────────────
Centralised Redis helper for the bike app with graceful offline fallbacks.

Key schema:
──────────
  trip:<id>:fuel_stops  → String (JSON)  Pre-calculated 70% refuel point
                                         and nearby petrol stations.
  trip:<id>:ai_summary  → String (HTML)  Cached Gemini AI route analysis.
  trip:<id>:ai_tips     → String (HTML)  Cached Gemini road advice & tips.
  trip:<id>:ai_weather  → String (Text)  Cached route weather text.

(Note: Bike machine specs such as tank capacity and mileage are stored
permanently in the PostgreSQL database on the BikeTrip model.)
"""
import json
import logging
import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Single connection pool — shared across the process
_redis = redis.from_url(
    getattr(settings, 'REDIS_URL', 'redis://localhost:6379'),
    decode_responses=True   # return str, not bytes
)

CACHE_TTL = 60 * 60 * 24 * 7   # 7 days


# ─── Fuel Stops (pre-calculated 70% refuel point + nearby pumps) ─────────────

def _fuel_stops_key(trip_id: int) -> str:
    return f"trip:{trip_id}:fuel_stops"


def save_fuel_stops(trip_id: int, data: dict) -> None:
    """
    Cache the pre-calculated 70% refuel point and nearby petrol stations.
    Stored as a JSON string because the structure is nested.
    """
    try:
        key = _fuel_stops_key(trip_id)
        _redis.set(key, json.dumps(data))
        _redis.expire(key, CACHE_TTL)
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to save fuel stops for trip {trip_id}: {e}")


def get_fuel_stops(trip_id: int) -> dict:
    """
    Retrieve the pre-calculated fuel stops payload from Redis.
    Returns an empty dict if nothing is cached or Redis is offline.
    """
    try:
        raw = _redis.get(_fuel_stops_key(trip_id))
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to get fuel stops for trip {trip_id}: {e}")
    return {}


# ─── AI Advice / Tips & Summaries ───────────────────────────────────────────

def _ai_tips_key(trip_id: int) -> str:
    return f"trip:{trip_id}:ai_tips"


def save_ai_tips(trip_id: int, html_content: str, ttl: int = CACHE_TTL) -> None:
    """
    Cache generated AI advice HTML for a trip.
    """
    try:
        key = _ai_tips_key(trip_id)
        _redis.set(key, html_content)
        _redis.expire(key, ttl)
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to save AI tips for trip {trip_id}: {e}")


def get_ai_tips(trip_id: int) -> str | None:
    """
    Retrieve cached AI advice HTML from Redis.
    Returns None if not found or Redis is offline.
    """
    try:
        return _redis.get(_ai_tips_key(trip_id))
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to get AI tips for trip {trip_id}: {e}")
        return None


def _ai_summary_key(trip_id: int) -> str:
    return f"trip:{trip_id}:ai_summary"


def save_ai_summary(trip_id: int, html_content: str, ttl: int = CACHE_TTL) -> None:
    """
    Cache generated AI summary HTML for a trip.
    """
    try:
        key = _ai_summary_key(trip_id)
        _redis.set(key, html_content)
        _redis.expire(key, ttl)
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to save AI summary for trip {trip_id}: {e}")


def get_ai_summary(trip_id: int) -> str | None:
    """
    Retrieve cached AI summary HTML from Redis.
    Returns None if not found or Redis is offline.
    """
    try:
        return _redis.get(_ai_summary_key(trip_id))
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to get AI summary for trip {trip_id}: {e}")
        return None


def _ai_weather_key(trip_id: int) -> str:
    return f"trip:{trip_id}:ai_weather"


def save_ai_weather(trip_id: int, weather_text: str, ttl: int = CACHE_TTL) -> None:
    """
    Cache route weather text for a trip in Redis.
    """
    try:
        key = _ai_weather_key(trip_id)
        _redis.set(key, weather_text)
        _redis.expire(key, ttl)
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to save AI weather for trip {trip_id}: {e}")


def get_ai_weather(trip_id: int) -> str | None:
    """
    Retrieve cached route weather text from Redis.
    """
    try:
        return _redis.get(_ai_weather_key(trip_id))
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to get AI weather for trip {trip_id}: {e}")
        return None


# ─── Cleanup ──────────────────────────────────────────────────────────────────

def delete_trip_cache(trip_id: int) -> None:
    """Remove transient Redis cache keys when an expedition is deleted."""
    try:
        _redis.delete(_fuel_stops_key(trip_id))
        _redis.delete(_ai_tips_key(trip_id))
        _redis.delete(_ai_summary_key(trip_id))
        _redis.delete(_ai_weather_key(trip_id))
    except redis.RedisError as e:
        logger.warning(f"[Redis] Unable to delete Redis keys for trip {trip_id}: {e}")
