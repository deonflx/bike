from rest_framework import viewsets, permissions
from bike_app.models import BikeTrip, TripSession, RouteWeather, ConnectionRequest
from bike_app.serializers import (
    BikeTripSerializer,
    TripSessionSerializer,
    RouteWeatherSerializer,
    ConnectionRequestSerializer
)


class BikeTripViewSet(viewsets.ModelViewSet):
    """
    Handles:
    - GET    /api/trips/          (List all trips)
    - POST   /api/trips/          (Create a new trip)
    - GET    /api/trips/<id>/     (Retrieve trip details + Redis specs)
    - DELETE /api/trips/<id>/     (Delete trip)
    """
    queryset = BikeTrip.objects.all()
    serializer_class = BikeTripSerializer
    permission_classes = [permissions.AllowAny]  # Can change to IsAuthenticated later

    def perform_create(self, serializer):
        # Automatically attach the logged-in user if available
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)


class TripSessionViewSet(viewsets.ModelViewSet):
    """
    Handles:
    - GET    /api/sessions/<id>/  (Fetch current live location & status)
    - PATCH  /api/sessions/<id>/  (Send live GPS updates with {"lat": ..., "lng": ...})
    """
    queryset = TripSession.objects.all()
    serializer_class = TripSessionSerializer
    permission_classes = [permissions.AllowAny]


class RouteWeatherViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Handles:
    - GET    /api/weather/        (Read cached route weather points)
    """
    queryset = RouteWeather.objects.all()
    serializer_class = RouteWeatherSerializer
    permission_classes = [permissions.AllowAny]


class ConnectionRequestViewSet(viewsets.ModelViewSet):
    """
    Handles:
    - GET    /api/connections/    (List co-traveler connection requests)
    - POST   /api/connections/    (Send a connection request)
    """
    queryset = ConnectionRequest.objects.all()
    serializer_class = ConnectionRequestSerializer
    permission_classes = [permissions.AllowAny]