from django.urls import path, include
from rest_framework.routers import DefaultRouter
from bike_app.api_views import (
    BikeTripViewSet,
    TripSessionViewSet,
    RouteWeatherViewSet,
    ConnectionRequestViewSet,
)

router = DefaultRouter()
router.register(r'trips', BikeTripViewSet, basename='trip')
router.register(r'sessions', TripSessionViewSet, basename='session')
router.register(r'weather', RouteWeatherViewSet, basename='weather')
router.register(r'connections', ConnectionRequestViewSet, basename='connection')

urlpatterns = [
    # REST API endpoints
    path('api/', include(router.urls)),
]
