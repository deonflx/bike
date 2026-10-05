from django.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.auth.models import User


class BikeTrip(models.Model):
    """
    Stores route/spatial data in PostGIS.
    Bike specs (capacity, mileage) live in Redis under key trip:<id>:specs.
    """
    user                 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips', null=True, blank=True)
    bikename             = models.CharField(max_length=100)

    # Human-readable location labels
    starting_name        = models.CharField(max_length=200, default='')
    destination_name     = models.CharField(max_length=200, default='')

    # Geocoded spatial points (SRID 4326 = WGS-84 lat/lng)
    starting_point       = gis_models.PointField(srid=4326, null=True, blank=True)
    destination_point    = gis_models.PointField(srid=4326, null=True, blank=True)

    created_at           = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bikename} — {self.starting_name} → {self.destination_name}"

    class Meta:
        ordering = ['-created_at']

    # Legacy text accessors so templates don't break during migration
    @property
    def starting_location(self):
        return self.starting_name

    @property
    def destination_location(self):
        return self.destination_name


class TripSession(models.Model):
    STATUS_ACTIVE    = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES   = [('active', 'Active'), ('completed', 'Completed')]

    bike_trip        = models.ForeignKey(BikeTrip, on_delete=models.CASCADE, related_name='sessions')
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    current_location = gis_models.PointField(null=True, blank=True, srid=4326)
    started_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Session #{self.pk} — {self.bike_trip.bikename} ({self.status})"

    @property
    def is_active(self):
        return self.status == self.STATUS_ACTIVE

    @property
    def current_lat(self):
        return self.current_location.y if self.current_location else None

    @property
    def current_lng(self):
        return self.current_location.x if self.current_location else None


class RouteWeather(models.Model):
    """
    Stores weather observations tied to specific geographic points along a route.
    Lives in PostGIS so weather data is spatially queryable and reusable.
    """
    bike_trip    = models.ForeignKey(BikeTrip, on_delete=models.CASCADE, related_name='weather_points')
    location     = gis_models.PointField(srid=4326)   # GPS point of observation
    description  = models.TextField()                  # weather summary text
    recorded_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['recorded_at']

    def __str__(self):
        return f"Weather @ ({self.location.y:.2f}, {self.location.x:.2f}) for Trip #{self.bike_trip_id}"


class ConnectionRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    # The user sending the request
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_requests')
    
    # The user receiving the request
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_requests')
    
    # The specific trip they are connecting about
    bike_trip = models.ForeignKey(BikeTrip, on_delete=models.CASCADE, related_name='connection_requests')
    
    # Track the state of the request
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Prevent a user from spamming the same person with multiple requests for the same trip
        unique_together = ('sender', 'receiver', 'bike_trip')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender.username} to {self.receiver.username} for trip {self.bike_trip_id} ({self.status})"