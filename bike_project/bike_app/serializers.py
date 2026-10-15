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
    convoy = serializers.SerializerMethodField()

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
            'convoy',
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

    def get_convoy(self, obj):
        from .services import _haversine_km
        from django.db.models import Q

        if not obj.bike_trip:
            return None

        trip = obj.bike_trip
        trip_user = trip.user

        # Find all accepted connections involving this trip or this user
        trip_conns = list(ConnectionRequest.objects.filter(
            bike_trip=trip,
            status=ConnectionRequest.STATUS_ACCEPTED
        ).select_related('sender', 'receiver', 'bike_trip'))

        user_conns = []
        if trip_user:
            user_conns = list(ConnectionRequest.objects.filter(
                Q(sender=trip_user) | Q(receiver=trip_user),
                status=ConnectionRequest.STATUS_ACCEPTED
            ).select_related('sender', 'receiver', 'bike_trip'))

        all_conns = trip_conns + user_conns
        if not all_conns:
            return None

        # Gather unique partner users and linked trips
        partner_users = {}
        linked_trip_ids = {trip.pk}

        for c in all_conns:
            linked_trip_ids.add(c.bike_trip_id)
            if c.sender and (not trip_user or c.sender.pk != trip_user.pk):
                partner_users[c.sender.pk] = c.sender
            if c.receiver and (not trip_user or c.receiver.pk != trip_user.pk):
                partner_users[c.receiver.pk] = c.receiver

        # Also pull connections across all linked trips in the group
        if linked_trip_ids:
            pack_conns = ConnectionRequest.objects.filter(
                bike_trip_id__in=linked_trip_ids,
                status=ConnectionRequest.STATUS_ACCEPTED
            ).select_related('sender', 'receiver')
            for c in pack_conns:
                if c.sender and (not trip_user or c.sender.pk != trip_user.pk):
                    partner_users[c.sender.pk] = c.sender
                if c.receiver and (not trip_user or c.receiver.pk != trip_user.pk):
                    partner_users[c.receiver.pk] = c.receiver

        if not partner_users:
            return None

        members = []
        current_lat = obj.current_lat
        current_lng = obj.current_lng

        for p_id, partner in partner_users.items():
            # Find an active session for this partner
            partner_session = TripSession.objects.filter(
                bike_trip__user=partner,
                status=TripSession.STATUS_ACTIVE
            ).exclude(pk=obj.pk).select_related('bike_trip').first()

            if not partner_session:
                partner_session = TripSession.objects.filter(
                    bike_trip_id__in=linked_trip_ids,
                    bike_trip__user=partner,
                    status=TripSession.STATUS_ACTIVE
                ).exclude(pk=obj.pk).select_related('bike_trip').first()

            # Bike name
            bikename = None
            if partner_session and partner_session.bike_trip:
                bikename = partner_session.bike_trip.bikename
            else:
                p_trip = BikeTrip.objects.filter(user=partner).first()
                bikename = p_trip.bikename if p_trip else 'Motorcycle'

            p_lat = partner_session.current_lat if partner_session else None
            p_lng = partner_session.current_lng if partner_session else None
            is_live = bool(partner_session and p_lat is not None and p_lng is not None)

            gap_km = None
            if current_lat is not None and current_lng is not None and p_lat is not None and p_lng is not None:
                gap_km = round(_haversine_km(current_lat, current_lng, p_lat, p_lng), 2)

            members.append({
                'user_id': partner.id,
                'username': partner.username,
                'bikename': bikename,
                'is_live': is_live,
                'session_id': partner_session.pk if partner_session else None,
                'coords': {'lat': p_lat, 'lng': p_lng} if is_live else None,
                'updated_at': partner_session.updated_at.isoformat() if partner_session else None,
                'gap_km': gap_km,
            })

        # Sort: live riders first (sorted by closest gap), followed by offline riders
        members.sort(key=lambda m: (not m['is_live'], m['gap_km'] if m['gap_km'] is not None else 999999))

        live_riders = [m for m in members if m['is_live']]
        live_gaps = [m['gap_km'] for m in live_riders if m['gap_km'] is not None]

        min_gap = min(live_gaps) if live_gaps else None
        max_gap = max(live_gaps) if live_gaps else None

        # Lead companion (closest live rider) for backwards compatibility
        first_partner = live_riders[0] if live_riders else members[0]

        # Find WhatsApp group link from this trip or linked pack trips
        whatsapp_link = obj.bike_trip.whatsapp_group_link
        if not whatsapp_link and linked_trip_ids:
            trip_with_wa = BikeTrip.objects.filter(
                pk__in=linked_trip_ids,
                whatsapp_group_link__isnull=False
            ).exclude(whatsapp_group_link='').first()
            if trip_with_wa:
                whatsapp_link = trip_with_wa.whatsapp_group_link

        return {
            'has_partner': True,
            'is_group': len(members) > 1,
            'total_pack_riders': len(members) + 1,
            'active_live_count': len(live_riders),
            'min_gap_km': min_gap,
            'max_gap_km': max_gap,
            'members': members,
            'whatsapp_group_link': whatsapp_link,
            # Backward-compatible single partner attributes:
            'partner_username': first_partner['username'],
            'partner_bikename': first_partner['bikename'],
            'is_live': bool(live_riders),
            'partner_session_id': first_partner['session_id'],
            'partner_coords': first_partner['coords'],
            'partner_updated_at': first_partner['updated_at'],
            'gap_km': first_partner['gap_km'],
        }

    def update(self, instance, validated_data):
        lat = validated_data.pop('lat', None)
        lng = validated_data.pop('lng', None)

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

    starting_name = serializers.ReadOnlyField(source='bike_trip.starting_name')
    destination_name = serializers.ReadOnlyField(source='bike_trip.destination_name')
    whatsapp_group_link = serializers.ReadOnlyField(source='bike_trip.whatsapp_group_link')

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
            'starting_name',
            'destination_name',
            'whatsapp_group_link',
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
            'whatsapp_group_link',
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