from django.db import models
from django.contrib.gis.db import models as gis_models


class BikeTrip(models.Model):
    bikename = models.CharField(max_length=100)
    fueltank_capacity = models.FloatField(help_text="Fuel tank capacity in liters")
    average_mileage = models.FloatField(help_text="Average mileage in km/liter")
    starting_location = models.TextField()
    destination_location = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bikename} - {self.starting_location} to {self.destination_location}"

    class Meta:
        ordering = ['-created_at']


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
