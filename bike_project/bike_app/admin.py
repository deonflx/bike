from django.contrib import admin
# pyrefly: ignore [missing-import]
from .models import BikeTrip, RouteWeather


@admin.register(BikeTrip)
class BikeTripAdmin(admin.ModelAdmin):
    list_display  = ('bikename', 'starting_name', 'destination_name', 'created_at')
    search_fields = ('bikename', 'starting_name', 'destination_name')
    list_filter   = ('created_at',)
    readonly_fields = ('created_at',)


@admin.register(RouteWeather)
class RouteWeatherAdmin(admin.ModelAdmin):
    list_display  = ('bike_trip', 'description', 'recorded_at')
    list_filter   = ('recorded_at',)
    readonly_fields = ('recorded_at',)
