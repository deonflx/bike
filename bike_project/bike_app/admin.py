from django.contrib import admin
from .models import BikeTrip

@admin.register(BikeTrip)
class BikeTripAdmin(admin.ModelAdmin):
    list_display = ('bikename', 'starting_location', 'destination_location', 'average_mileage', 'fueltank_capacity', 'created_at')
    search_fields = ('bikename', 'starting_location', 'destination_location')
    list_filter = ('created_at', 'average_mileage')
    readonly_fields = ('created_at',)
