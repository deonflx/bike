from rest_framework import serializers
from django.contrib.gis.geos import Point
from bike_app.models import BikeTrip, TripSession, RouteWeather, ConnectionRequest
from bike_app.redis_client import get_bike_specs


# ─── 1. Route Weather Serializer ──────────────────────────────────────────────
class RouteWeatherSerializer(serializers.ModelSerializer):
    """
    Serializes weather observations along a route.
    Converts PostGIS Point geometry into clean {lat, lng} JSON, and
    allows creating weather points using separate 'lat' and 'lng' inputs.
    """
    # Output: returns { "lat": 12.97, "lng": 77.59 }
    location = serializers.SerializerMethodField()

    # Input: optional write-only coordinates for POST requests
    lat = serializers.FloatField(write_only=True, required=False)
    lng = serializers.FloatField(write_only=True, required=False)

    class Meta:
        model = RouteWeather
        fields = [
            'id',
            'bike_trip',
            'location',
            'description',
            'lat',
            'lng',
            'recorded_at',
        ]
        read_only_fields = ['id', 'recorded_at']

    def get_location(self, obj):
        if obj.location:
            return {'lat': obj.location.y, 'lng': obj.location.x}
        return None

    def create(self, validated_data):
        lat = validated_data.pop('lat', None)
        lng = validated_data.pop('lng', None)

        if lat is not None and lng is not None:
            validated_data['location'] = Point(lng, lat, srid=4326)

        return super().create(validated_data)


# ─── 2. Trip Session Serializer (Live GPS Tracking) ───────────────────────────
class TripSessionSerializer(serializers.ModelSerializer):
    """
    Serializes live tracking sessions.
    - Output: reads lat/lng from PostGIS and bike name from related trip.
    - Input: accepts live GPS updates via 'lat' and 'lng' float fields.
    """
    # Read-only output fields from model @property methods
    current_lat = serializers.ReadOnlyField()
    current_lng = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    bikename = serializers.ReadOnlyField(source='bike_trip.bikename')
    starting_name = serializers.ReadOnlyField(source='bike_trip.starting_name')
    destination_name = serializers.ReadOnlyField(source='bike_trip.destination_name')
    start_coords = serializers.SerializerMethodField()
    dest_coords = serializers.SerializerMethodField()
    route_coords = serializers.SerializerMethodField()

    # Write-only input fields for phone/browser GPS pings (PATCH / PUT)
    lat = serializers.FloatField(write_only=True, required=False)
    lng = serializers.FloatField(write_only=True, required=False)

    class Meta:
        model = TripSession
        fields = [
            'id',
            'bike_trip',
            'bikename',
            'starting_name',
            'destination_name',
            'status',
            'is_active',
            'current_lat',
            'current_lng',
            'start_coords',
            'dest_coords',
            'route_coords',
            'lat',
            'lng',
            'started_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'started_at', 'updated_at']

    def get_start_coords(self, obj):
        if obj.bike_trip and obj.bike_trip.starting_point:
            return {'lat': obj.bike_trip.starting_point.y, 'lng': obj.bike_trip.starting_point.x}
        return None

    def get_dest_coords(self, obj):
        if obj.bike_trip and obj.bike_trip.destination_point:
            return {'lat': obj.bike_trip.destination_point.y, 'lng': obj.bike_trip.destination_point.x}
        return None

    def get_route_coords(self, obj):
        if obj.bike_trip and obj.bike_trip.route_path:
            # PostGIS LineString coords are (lng, lat) -> convert to Leaflet's [lat, lng]
            return [[pt[1], pt[0]] for pt in obj.bike_trip.route_path.coords]
        return []

    def update(self, instance, validated_data):
        lat = validated_data.pop('lat', None)
        lng = validated_data.pop('lng', None)

        # If incoming GPS coordinates are present, update PostGIS PointField
        if lat is not None and lng is not None:
            instance.current_location = Point(lng, lat, srid=4326)

        return super().update(instance, validated_data)


# ─── 3. Connection Request Serializer (Group Rides) ───────────────────────────
class ConnectionRequestSerializer(serializers.ModelSerializer):
    """
    Serializes rider connection / co-traveler invite requests.
    Includes readable usernames so the frontend does not need extra lookups.
    """
    sender_username = serializers.ReadOnlyField(source='sender.username')
    receiver_username = serializers.ReadOnlyField(source='receiver.username')
    bikename = serializers.ReadOnlyField(source='bike_trip.bikename')

    class Meta:
        model = ConnectionRequest
        fields = [
            'id',
            'sender',
            'sender_username',
            'receiver',
            'receiver_username',
            'bike_trip',
            'bikename',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'sender', 'created_at', 'updated_at']


# ─── 4. Main Bike Trip Serializer ─────────────────────────────────────────────
class BikeTripSerializer(serializers.ModelSerializer):
    """
    Serializes a BikeTrip.
    - Converts PostGIS starting & destination points into {lat, lng} dicts.
    - Pulls bike specifications (capacity, mileage, fuel cost) from Redis.
    """
    owner_username = serializers.ReadOnlyField(source='user.username')
    starting_coords = serializers.SerializerMethodField()
    destination_coords = serializers.SerializerMethodField()
    specs = serializers.SerializerMethodField()

    class Meta:
        model = BikeTrip
        fields = [
            'id',
            'user',
            'owner_username',
            'bikename',
            'capacity',
            'mileage',
            'starting_name',
            'destination_name',
            'starting_coords',
            'destination_coords',
            'specs',
            'created_at',
        ]
        read_only_fields = ['id', 'user', 'created_at']

    def get_starting_coords(self, obj):
        if obj.starting_point:
            return {'lat': obj.starting_point.y, 'lng': obj.starting_point.x}
        return None

    def get_destination_coords(self, obj):
        if obj.destination_point:
            return {'lat': obj.destination_point.y, 'lng': obj.destination_point.x}
        return None

    def get_specs(self, obj):
        """Returns bike specs from Postgres model (with Redis fallback if needed)"""
        capacity = obj.capacity
        mileage = obj.mileage
        if capacity is None or mileage is None:
            r_specs = get_bike_specs(obj.id)
            capacity = capacity if capacity is not None else r_specs.get('capacity')
            mileage = mileage if mileage is not None else r_specs.get('mileage')
        return {
            'bikename': obj.bikename,
            'capacity': capacity,
            'mileage': mileage,
        }