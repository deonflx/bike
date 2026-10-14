import json
import time
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point, LineString
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import BikeTrip, TripSession, RouteWeather, ConnectionRequest
from .serializers import (
    BikeTripSerializer,
    TripSessionSerializer,
    RouteWeatherSerializer,
    ConnectionRequestSerializer
)
from .redis_client import (
    save_bike_specs, get_bike_specs,
    save_fuel_stops, get_fuel_stops,
    save_ai_summary, get_ai_summary,
    save_ai_weather, get_ai_weather,
    save_ai_tips, get_ai_tips,
    delete_trip_cache,
)
from .ai_helper import generate_content, get_bike_specs_from_ai
from .views import (
    _geocode,
    _trip_capacity_mileage,
    _compute_refuel_point_and_pumps,
    _get_or_create_route_path,
    _calculate_route_overlap,
    _haversine_km,
    _fetch_and_store_weather,
    _attach_spec_display,
)

User = get_user_model()


class BikeTripViewSet(viewsets.ModelViewSet):
    """
    Handles all trip operations:
    - CRUD on BikeTrip
    - Auto-geocoding + Gemini bike spec lookup + Redis caching on create
    - AI trip summary & weather generation
    - Co-traveler & route-matching discovery
    - Live trip session launching
    """
    queryset = BikeTrip.objects.all().order_by('-created_at')
    serializer_class = BikeTripSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        bikename = self.request.data.get('bikename', '').strip()
        starting_name = self.request.data.get('starting_name', '').strip()
        destination_name = self.request.data.get('destination_name', '').strip()

        # 1. Geocode locations into PostGIS Points (Nominatim with slight delay)
        starting_point = _geocode(starting_name) if starting_name else None
        time.sleep(1.0)
        destination_point = _geocode(destination_name) if destination_name else None

        # 2. Query specs (referring to 100_popular_bikes_india CSV via AI, with fallback)
        specs = get_bike_specs_from_ai(bikename)
        capacity = float(specs.get('capacity', 15.0))
        mileage = float(specs.get('mileage', 35.0))

        # 3. Save instance with spatial points & specs
        user = self.request.user if self.request.user.is_authenticated else None
        trip = serializer.save(
            user=user,
            capacity=capacity,
            mileage=mileage,
            starting_point=starting_point,
            destination_point=destination_point
        )

        # 4. Cache specs in Redis
        save_bike_specs(trip.id, {
            'bikename': bikename,
            'capacity': capacity,
            'mileage': mileage,
        })

        # 5. Pre-calculate refuel point, nearby petrol pumps, & route path geometry
        if starting_point and destination_point:
            try:
                fuel_stop_data = _compute_refuel_point_and_pumps(
                    starting_point, destination_point, capacity, mileage
                )
                save_fuel_stops(trip.id, fuel_stop_data)
                coords = fuel_stop_data.get('coords')
                if coords and len(coords) >= 2:
                    trip.route_path = LineString(coords, srid=4326)
                    trip.save(update_fields=['route_path'])
            except Exception as e:
                print(f"[API] Fuel stop computation failed for Trip #{trip.id}: {e}")

    def perform_destroy(self, instance):
        delete_trip_cache(instance.pk)
        instance.delete()

    @action(detail=True, methods=['get'])
    def fuel_stops(self, request, pk=None):
        """Fetch pre-cached refuel points and petrol pumps from Redis"""
        trip = self.get_object()
        data = get_fuel_stops(trip.id)
        if not data:
            return Response({'needed': False, 'stations': []})
        return Response(data)

    @action(detail=True, methods=['post'])
    def start_session(self, request, pk=None):
        """Start or resume a live tracking session for this trip"""
        trip = self.get_object()
        session = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_ACTIVE).first()
        if not session:
            session = TripSession.objects.create(
                bike_trip=trip,
                current_location=trip.starting_point
            )
        serializer = TripSessionSerializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def generate_summary(self, request, pk=None):
        """Generate or retrieve cached AI route & weather advisory"""
        trip = self.get_object()
        force_refresh = request.query_params.get('refresh') == 'true'

        if not force_refresh:
            cached_summary = get_ai_summary(trip.pk)
            if cached_summary:
                return Response({'status': 'ok', 'html': cached_summary, 'cached': True})

        capacity, mileage = _trip_capacity_mileage(trip)

        try:
            weather_text = get_ai_weather(trip.pk)
            if not weather_text:
                cached_weather = RouteWeather.objects.filter(bike_trip=trip)
                if cached_weather.exists():
                    weather_text = ' | '.join(w.description for w in cached_weather)
                else:
                    weather_text = _fetch_and_store_weather(trip)
                save_ai_weather(trip.pk, weather_text)

            prompt = f"""
You are an intelligent trip analyzer for a motorcycle app.
Bike: {trip.bikename} | From: {trip.starting_name} → {trip.destination_name}
Tank: {capacity}L | Mileage: {mileage} km/l
Weather along route: {weather_text}

Return a concise HTML snippet (use <b>, <br>, <ul>, <li> only — no markdown, no html/body tags):

<b>⛽ Fuel Efficiency & Cost:</b> {mileage} km/l. Consumed: [liters with 10% detour buffer]L ≈ ₹[cost at ₹113/L]<br><br>
<b>🌤️ Route Weather:</b> [1-sentence summary of {weather_text}]<br><br>
<b>⏱️ Total Time:</b> [driving time estimate] driving + [break time], total ≈ [grand total]
"""
            response_text = generate_content(prompt)
            html = response_text.replace('```html', '').replace('```', '').strip()

            save_ai_summary(trip.pk, html)
            save_ai_weather(trip.pk, weather_text)

            return Response({'status': 'ok', 'html': html, 'cached': False})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='ai_tips')
    def ai_tips(self, request, pk=None):
        """Generate or retrieve cached AI advice / tips for route map"""
        trip = self.get_object()
        data = request.data or {}
        force_refresh = data.get('refresh', False) or request.query_params.get('refresh') == 'true'

        if not force_refresh:
            cached_html = get_ai_tips(trip.pk)
            if cached_html:
                return Response({'status': 'ok', 'html': cached_html, 'cached': True})

        capacity, mileage = _trip_capacity_mileage(trip)
        max_range = capacity * mileage

        try:
            distance = data.get('distance', 0)
            duration_mins = data.get('duration', 0)
            weather_conditions = data.get('weather', [])

            weather_text = ', '.join(weather_conditions) if weather_conditions else 'Unknown weather'
            prompt = f"""
You are an expert motorcycle touring advisor.
Bike: {trip.bikename} | From: {trip.starting_name} → {trip.destination_name}
Distance: {distance} km | Drive time: {duration_mins} min
Tank: {capacity}L | Mileage: {mileage} km/l | Max range: {max_range:.0f} km
Weather: {weather_text}

Provide a detailed advisory covering:
1. Total estimated fuel cost (₹113/L assumed)
2. Total trip time with a break schedule
3. Route & safety advice given the weather
"""
            import markdown
            response_text = generate_content(prompt)
            html = markdown.markdown(response_text)
            save_ai_tips(trip.pk, html)
            return Response({'status': 'ok', 'html': html, 'cached': False})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def co_travelers(self, request, pk=None):
        """Find matching co-travelers and riders sharing this route"""
        trip = self.get_object()
        radius_km = 50.0

        _get_or_create_route_path(trip)
        co_query = BikeTrip.objects.exclude(pk=trip.pk).select_related('user')
        dest_clean = (trip.destination_name or '').strip()
        dest_city = dest_clean.split(',')[0].strip()

        filter_q = Q()
        if trip.destination_point:
            filter_q |= Q(
                destination_point__isnull=False,
                destination_point__distance_lte=(trip.destination_point, D(km=radius_km))
            )
        if dest_city:
            filter_q |= Q(destination_name__icontains=dest_city)
        elif dest_clean:
            filter_q |= Q(destination_name__iexact=dest_clean)

        if trip.route_path:
            filter_q |= Q(route_path__isnull=False, route_path__bboverlaps=trip.route_path)

        try:
            if trip.destination_point:
                raw_candidates = list(
                    co_query.filter(filter_q)
                    .annotate(dest_distance=Distance('destination_point', trip.destination_point))
                )
            else:
                raw_candidates = list(co_query.filter(filter_q))
        except Exception:
            raw_candidates = list(co_query.all()[:20])

        active_co_sessions = {
            s.bike_trip_id: s
            for s in TripSession.objects.filter(
                bike_trip__in=raw_candidates, status=TripSession.STATUS_ACTIVE
            )
        }

        results = []
        for rider in raw_candidates:
            dist_km = None
            if hasattr(rider, 'dest_distance') and rider.dest_distance is not None:
                dist_km = round(rider.dest_distance.km, 2)
            elif trip.destination_point and rider.destination_point:
                dist_km = round(_haversine_km(
                    trip.destination_point.y, trip.destination_point.x,
                    rider.destination_point.y, rider.destination_point.x
                ), 2)

            overlap = _calculate_route_overlap(trip, rider)
            is_dest_match = (dist_km is not None and dist_km <= radius_km) or (
                dest_city and dest_city.lower() in (rider.destination_name or '').lower()
            )

            if not (is_dest_match or overlap['is_match']):
                continue

            active_session = active_co_sessions.get(rider.pk)
            results.append({
                'id': rider.pk,
                'bikename': rider.bikename,
                'starting_name': rider.starting_name,
                'destination_name': rider.destination_name,
                'dist_km': dist_km,
                'shared_route_km': overlap['shared_km'],
                'overlap_pct': overlap['overlap_pct'],
                'is_same_direction': overlap['is_same_direction'],
                'is_live': bool(active_session),
                'live_session_id': active_session.pk if active_session else None,
            })

        return Response(results)


class TripSessionViewSet(viewsets.ModelViewSet):
    """
    Handles live tracking sessions:
    - GET /api/sessions/<id>/
    - PATCH /api/sessions/<id>/ with {"lat": ..., "lng": ...}
    - POST /api/sessions/<id>/end_session/
    """
    queryset = TripSession.objects.all()
    serializer_class = TripSessionSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=['post'])
    def end_session(self, request, pk=None):
        session = self.get_object()
        session.status = TripSession.STATUS_COMPLETED
        session.save(update_fields=['status'])
        serializer = self.get_serializer(session)
        return Response(serializer.data)


class RouteWeatherViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RouteWeather.objects.all()
    serializer_class = RouteWeatherSerializer
    permission_classes = [permissions.AllowAny]


class ConnectionRequestViewSet(viewsets.ModelViewSet):
    queryset = ConnectionRequest.objects.all().order_by('-created_at')
    serializer_class = ConnectionRequestSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(sender=user)

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        conn = self.get_object()
        action_val = request.data.get('status')
        if action_val in ['accepted', 'rejected']:
            conn.status = action_val
            conn.save(update_fields=['status'])
            serializer = self.get_serializer(conn)
            return Response(serializer.data)
        return Response({'error': 'Invalid status. Use accepted or rejected.'}, status=status.HTTP_400_BAD_REQUEST)