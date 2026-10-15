"""
views.py — Legacy compatibility module.
All business logic, geocoding, OSRM routing, and weather services now live in services.py.
All HTTP endpoints are handled by Django REST Framework in api_views.py.
"""

from .services import *  # noqa: F401, F403