import json
import math
import os
import time
import requests as http_requests
from .models import ConnectionRequest

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from dotenv import load_dotenv

load_dotenv(override=True)

# pyrefly: ignore [missing-import]
from .models import BikeTrip, TripSession, RouteWeather
# pyrefly: ignore [missing-import]
from .redis_client import save_bike_specs, get_bike_specs, delete_bike_specs, save_fuel_stops, get_fuel_stops
# pyrefly: ignore [missing-import]
from .ai_helper import generate_content


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _geocode(place_name: str):
    """
    Convert a place name to (lat, lng) using Nominatim (India-restricted).
    Returns a Point(lng, lat) or None on failure.
    """
    try:
        r = http_requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': place_name, 'format': 'json', 'limit': 1, 'countrycodes': 'in'},
            headers={'User-Agent': 'BikeTripRoutingApp/1.0 (contact: admin@bikerouteapp.com)'},
            timeout=5
        )
        results = r.json()
        if results:
            lat = float(results[0]['lat'])
            lng = float(results[0]['lon'])
            return Point(lng, lat, srid=4326)
    except Exception as e:
        print(f"Geocode failed for '{place_name}':", e)
    return None


def _haversine_km(lat1, lng1, lat2, lng2):
    """
    Calculate the great-circle distance (km) between two WGS-84 points
    using the Haversine formula.
    """
    R = 6371.0  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_refuel_point_and_pumps(starting_point, destination_point, capacity, mileage):
    """
    1. Query OSRM for the actual driving route geometry & distance.
    2. Walk along road coordinates until accumulated distance = 70% of max fuel range.
    3. Query Overpass API for amenity=fuel within 2 km of that highway point.
    Returns a dict with refuel_point, total_distance_km, and stations list.
    Falls back to straight-line interpolation if OSRM fails.
    """
    max_range_km    = capacity * mileage
    refuel_target_km = max_range_km * 0.70

    start_lng, start_lat = starting_point.x, starting_point.y
    dest_lng, dest_lat    = destination_point.x, destination_point.y

    # ── Step 1: Get driving route from OSRM ──────────────────────────────
    coords = None
    total_distance_km = None

    try:
        osrm_url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{start_lng},{start_lat};{dest_lng},{dest_lat}"
            f"?overview=full&geometries=geojson"
        )
        r = http_requests.get(osrm_url, timeout=4.0)
        data = r.json()

        if data.get('code') == 'Ok' and data.get('routes'):
            route = data['routes'][0]
            total_distance_km = route['distance'] / 1000.0  # meters → km
            coords = route['geometry']['coordinates']       # [[lng, lat], ...]
            print(f"[OSRM] Route distance: {total_distance_km:.1f} km, "
                  f"{len(coords)} coordinate points")
    except Exception as e:
        print(f"[OSRM] Failed, falling back to straight-line: {e}")

    # ── Fallback: straight-line interpolation if OSRM failed ─────────────
    if coords is None:
        total_distance_km = _haversine_km(start_lat, start_lng, dest_lat, dest_lng)
        coords = [[start_lng, start_lat], [dest_lng, dest_lat]]
        print(f"[Fallback] Straight-line distance: {total_distance_km:.1f} km")

    # ── Step 2: Check if refueling is even needed ────────────────────────
    if total_distance_km <= refuel_target_km:
        return {
            'needed': False,
            'reason': f'Trip ({total_distance_km:.1f} km) is within '
                      f'70% fuel range ({refuel_target_km:.1f} km)',
            'total_distance_km': round(total_distance_km, 1),
            'max_range_km': round(max_range_km, 1),
        }

    # ── Step 3: Walk along route coordinates to find the refuel point ────
    accumulated_km = 0.0
    refuel_lat, refuel_lng = None, None

    for i in range(len(coords) - 1):
        lng1, lat1 = coords[i]
        lng2, lat2 = coords[i + 1]
        segment_km = _haversine_km(lat1, lng1, lat2, lng2)

        if accumulated_km + segment_km >= refuel_target_km:
            # Interpolate within this segment
            remaining_km = refuel_target_km - accumulated_km
            fraction = remaining_km / segment_km if segment_km > 0 else 0
            refuel_lat = lat1 + fraction * (lat2 - lat1)
            refuel_lng = lng1 + fraction * (lng2 - lng1)
            break

        accumulated_km += segment_km

    # Safety fallback if loop didn't break (unlikely)
    if refuel_lat is None:
        refuel_lat = coords[-1][1]
        refuel_lng = coords[-1][0]

    print(f"[Refuel Point] At {refuel_target_km:.1f} km → "
          f"({refuel_lat:.5f}, {refuel_lng:.5f})")

    # ── Step 4: Query Overpass API with expanding radius ─────────────────
    stations = []
    search_radii_km = [2, 5, 10, 20, 50]
    used_radius_km = search_radii_km[0]

    for radius_km in search_radii_km:
        try:
            radius_m = radius_km * 1000
            overpass_query = f"""
            [out:json];
            node["amenity"="fuel"](around:{radius_m},{refuel_lat},{refuel_lng});
            out body;
            """
            r = http_requests.post(
                'https://overpass-api.de/api/interpreter',
                data={'data': overpass_query},
                timeout=8.0
            )
            elements = r.json().get('elements', [])

            for elem in elements:
                tags = elem.get('tags', {})
                pump_lat = elem.get('lat')
                pump_lng = elem.get('lon')
                dist_km = _haversine_km(refuel_lat, refuel_lng, pump_lat, pump_lng)
                stations.append({
                    'name':     tags.get('name', 'Fuel Station'),
                    'brand':    tags.get('brand', 'Unknown'),
                    'lat':      pump_lat,
                    'lng':      pump_lng,
                    'distance_km': round(dist_km, 2),
                })

            stations.sort(key=lambda s: s['distance_km'])
            used_radius_km = radius_km
            print(f"[Overpass] Radius {radius_km} km → "
                  f"found {len(stations)} fuel stations")

            if stations:
                break  # Found stations, stop expanding

            print(f"[Overpass] No stations at {radius_km} km, expanding…")
        except Exception as e:
            print(f"[Overpass] Petrol pump lookup failed at {radius_km} km: {e}")
            used_radius_km = radius_km
            break  # Don't retry on network/API errors

    return {
        'needed': True,
        'total_distance_km': round(total_distance_km, 1),
        'max_range_km': round(max_range_km, 1),
        'refuel_distance_km': round(refuel_target_km, 1),
        'search_radius_km': used_radius_km,
        'refuel_point': {
            'lat': round(refuel_lat, 6),
            'lng': round(refuel_lng, 6),
        },
        'stations': stations,
    }


# ─── Bike Trip Form ────────────────────────────────────────────────────────────

def bike_form(request):
    """Display the bike information form"""
    return render(request, 'bike_form.html')


@require_http_methods(["POST"])
def bike_submit(request):
    """
    Handle bike form submission.
    - Geocodes start/destination → stored as PostGIS PointField
    - Fetches bike specs from Gemini → stored in Redis hash
    """
    bikename         = request.POST.get('bikename', '').strip()
    starting_name    = request.POST.get('starting_location', '').strip()
    destination_name = request.POST.get('destination_location', '').strip()

    # 1. Geocode locations (PostGIS) - Needs delay for Nominatim rate limits (1 req/sec)
    starting_point    = _geocode(starting_name)
    time.sleep(1.2)
    destination_point = _geocode(destination_name)

    # 2. Fetch bike specs via Gemini/OpenAI (will go to Redis)
    try:
        prompt = (
            f"Return the average fuel tank capacity (liters) and average mileage (km/l) "
            f"for the motorcycle model '{bikename}'. "
            f"Return ONLY a JSON object with keys 'capacity' and 'mileage'. "
            f"Example: {{\"capacity\": 15, \"mileage\": 35}}"
        )
        response_text = generate_content(prompt)
        raw_text = response_text.replace('```json', '').replace('```', '').strip()
        specs    = json.loads(raw_text)
        capacity = float(specs.get('capacity', 15))
        mileage  = float(specs.get('mileage', 35))
    except Exception as e:
        print("Gemini spec lookup failed:", e)
        capacity = 15.0
        mileage  = 35.0

    # 3. Save slim trip to PostGIS (location only)
    trip = BikeTrip.objects.create(
        user              = request.user if request.user.is_authenticated else None,
        bikename          = bikename,
        starting_name     = starting_name,
        destination_name  = destination_name,
        starting_point    = starting_point,
        destination_point = destination_point,
    )

    # 4. Save bike specs to Redis
    save_bike_specs(trip.id, {
        'bikename': bikename,
        'capacity': capacity,
        'mileage':  mileage,
    })

    # 5. Pre-calculate 70% refuel point & cache nearby petrol pumps in Redis
    if starting_point and destination_point:
        try:
            fuel_stop_data = _compute_refuel_point_and_pumps(
                starting_point, destination_point, capacity, mileage
            )
            save_fuel_stops(trip.id, fuel_stop_data)
            print(f"[Trip #{trip.id}] Fuel stop data cached in Redis")
        except Exception as e:
            print(f"[Trip #{trip.id}] Fuel stop computation failed: {e}")

    return redirect('customer_list')


def bike_success(request):
    """Display success message after form submission"""
    return render(request, 'bike_success.html')


def get_trip_fuel_stops(request, pk):
    """
    API endpoint: Return pre-calculated fuel stop data from Redis.
    Responds instantly (<5ms) since data is pre-cached during trip creation.
    """
    trip = get_object_or_404(BikeTrip, pk=pk)
    fuel_data = get_fuel_stops(trip.pk)
    if not fuel_data:
        return JsonResponse({'error': 'No fuel stop data available'}, status=404)
    return JsonResponse(fuel_data)


# ─── Authentication Views ───────────────────────────────────────────────────────
# Authentication is now handled by django-allauth (see urls.py).



# ─── Customer Views ────────────────────────────────────────────────────────────

def customer_list(request):
    """Home page — user trips vs community trips vs group trips"""
    if not request.user.is_authenticated:
        return redirect('account_login')

    tab = request.GET.get('tab', 'my')  # 'my' = logged-in user trips, 'all' = community trips, 'group' = group trips

    my_count = BikeTrip.objects.filter(user=request.user).count()
    all_count = BikeTrip.objects.count()

    # Accepted group connections involving current user
    accepted_conns = ConnectionRequest.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user),
        status=ConnectionRequest.STATUS_ACCEPTED
    ).select_related('sender', 'receiver', 'bike_trip', 'bike_trip__user')

    group_count = accepted_conns.count()

    pending_invitations_count = ConnectionRequest.objects.filter(
        receiver=request.user,
        status=ConnectionRequest.STATUS_PENDING
    ).count()

    active_sessions = {
        s.bike_trip.pk: s
        for s in TripSession.objects.filter(status=TripSession.STATUS_ACTIVE).select_related('bike_trip')
    }

    if tab == 'group':
        trips = []
        for conn in accepted_conns:
            trip = conn.bike_trip
            trip.group_conn = conn
            trip.is_group = True
            trip.rider_leader = conn.sender
            trip.rider_partner = conn.receiver
            trip.active_session = active_sessions.get(trip.pk)
            specs = get_bike_specs(trip.pk)
            trip.redis_capacity = specs.get('capacity', '—')
            trip.redis_mileage  = specs.get('mileage',  '—')
            trips.append(trip)
    elif tab == 'all':
        trips_qs = BikeTrip.objects.all().select_related('user')
        trips = list(trips_qs)
        for trip in trips:
            trip.active_session = active_sessions.get(trip.pk)
            specs = get_bike_specs(trip.pk)
            trip.redis_capacity = specs.get('capacity', '—')
            trip.redis_mileage  = specs.get('mileage',  '—')
    else:
        trips_qs = BikeTrip.objects.filter(user=request.user).select_related('user')
        trips = list(trips_qs)
        for trip in trips:
            trip.active_session = active_sessions.get(trip.pk)
            specs = get_bike_specs(trip.pk)
            trip.redis_capacity = specs.get('capacity', '—')
            trip.redis_mileage  = specs.get('mileage',  '—')

    return render(request, 'customer_list.html', {
        'trips': trips,
        'tab': tab,
        'my_count': my_count,
        'all_count': all_count,
        'group_count': group_count,
        'pending_invitations_count': pending_invitations_count,
        'active_count': len(active_sessions),
    })


def customer_detail(request, pk):
    """Full details of a single bike trip record with destination co-traveler radar & group connection"""
    trip = get_object_or_404(BikeTrip, pk=pk)

    # Check if this trip has an accepted group ride connection
    group_conn = ConnectionRequest.objects.filter(
        bike_trip=trip,
        status=ConnectionRequest.STATUS_ACCEPTED
    ).select_related('sender', 'receiver').first()

    # Map connection statuses with co-travelers for the logged-in user
    user_conn_status = {}
    if request.user.is_authenticated:
        existing_reqs = ConnectionRequest.objects.filter(
            Q(sender=request.user) | Q(receiver=request.user)
        )
        for cr in existing_reqs:
            other_id = cr.receiver_id if cr.sender_id == request.user.id else cr.sender_id
            user_conn_status[other_id] = cr.status

    # Auto-heal missing coordinates if names exist
    if not trip.destination_point and trip.destination_name:
        pt = _geocode(trip.destination_name)
        if pt:
            trip.destination_point = pt
            trip.save(update_fields=['destination_point'])
    if not trip.starting_point and trip.starting_name:
        pt = _geocode(trip.starting_name)
        if pt:
            trip.starting_point = pt
            trip.save(update_fields=['starting_point'])

    # Fetch bike specs from Redis
    bike_specs = get_bike_specs(trip.pk)
    try:
        capacity = float(bike_specs.get('capacity', 0))
    except (ValueError, TypeError):
        capacity = 0.0
    try:
        mileage = float(bike_specs.get('mileage', 0))
    except (ValueError, TypeError):
        mileage = 0.0
    estimated_range = capacity * mileage if capacity and mileage else 0

    active_session = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_ACTIVE).first()
    past_sessions  = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_COMPLETED)

    # ── Destination Co-Travelers Query (Same Destination or within radius km) ──
    try:
        radius_km = float(request.GET.get('radius', 5.0))
        if radius_km <= 0 or radius_km > 100:
            radius_km = 5.0
    except (ValueError, TypeError):
        radius_km = 5.0

    co_query = BikeTrip.objects.exclude(pk=trip.pk).select_related('user')
    dest_clean = (trip.destination_name or '').strip()
    dest_city = dest_clean.split(',')[0].strip()

    co_travelers = []
    if trip.destination_point:
        try:
            filter_q = Q(
                destination_point__isnull=False,
                destination_point__distance_lte=(trip.destination_point, D(km=radius_km))
            )
            if dest_city:
                filter_q |= Q(destination_name__icontains=dest_city)
            elif dest_clean:
                filter_q |= Q(destination_name__iexact=dest_clean)

            co_travelers = list(
                co_query.filter(filter_q)
                .annotate(dest_distance=Distance('destination_point', trip.destination_point))
                .order_by('dest_distance')
            )
        except Exception as e:
            print(f"PostGIS destination query failed: {e}")
            if dest_city:
                co_travelers = list(co_query.filter(destination_name__icontains=dest_city))
            elif dest_clean:
                co_travelers = list(co_query.filter(destination_name__iexact=dest_clean))
    else:
        if dest_city:
            co_travelers = list(co_query.filter(destination_name__icontains=dest_city))
        elif dest_clean:
            co_travelers = list(co_query.filter(destination_name__iexact=dest_clean))

    # Attach live active session & Redis specs for each co-traveler
    active_co_sessions = {}
    if co_travelers:
        active_co_sessions = {
            s.bike_trip_id: s
            for s in TripSession.objects.filter(
                bike_trip__in=co_travelers, status=TripSession.STATUS_ACTIVE
            ).select_related('bike_trip')
        }

    co_travelers_json = []
    for rider in co_travelers:
        rider.active_session = active_co_sessions.get(rider.pk)
        specs = get_bike_specs(rider.pk)
        rider.redis_capacity = specs.get('capacity', '—')
        rider.redis_mileage  = specs.get('mileage',  '—')
        try:
            rc = float(rider.redis_capacity)
            rm = float(rider.redis_mileage)
            rider.estimated_range = round(rc * rm, 1)
        except (ValueError, TypeError):
            rider.estimated_range = None

        dist_km = None
        if hasattr(rider, 'dest_distance') and rider.dest_distance is not None:
            dist_km = round(rider.dest_distance.km, 2)
        elif trip.destination_point and rider.destination_point:
            dist_km = round(_haversine_km(trip.destination_point.y, trip.destination_point.x,
                                          rider.destination_point.y, rider.destination_point.x), 2)

        rider.dist_km = dist_km
        if dist_km is not None:
            if dist_km == 0:
                rider.formatted_dist = "Same Destination (0.0 km)"
                rider.match_type = "Exact Match"
            elif dist_km < 1.0:
                rider.formatted_dist = f"{dist_km * 1000:.0f} m from destination"
                rider.match_type = "< 1 km"
            else:
                rider.formatted_dist = f"{dist_km:.2f} km from destination"
                rider.match_type = f"{dist_km:.1f} km"
        else:
            rider.formatted_dist = "Same Destination"
            rider.match_type = "Destination Match"

        # Attach connection status with this rider
        rider_user_id = rider.user.id if rider.user else None
        rider.conn_status = user_conn_status.get(rider_user_id)

        dest_lat = rider.destination_point.y if rider.destination_point else None
        dest_lng = rider.destination_point.x if rider.destination_point else None
        start_lat = rider.starting_point.y if rider.starting_point else None
        start_lng = rider.starting_point.x if rider.starting_point else None

        co_travelers_json.append({
            'id': rider.pk,
            'bikename': rider.bikename,
            'user_id': rider_user_id,
            'username': rider.user.username if rider.user else 'anonymous',
            'conn_status': rider.conn_status,
            'starting_name': rider.starting_name,
            'destination_name': rider.destination_name,
            'dest_lat': dest_lat,
            'dest_lng': dest_lng,
            'start_lat': start_lat,
            'start_lng': start_lng,
            'dist_km': dist_km,
            'formatted_dist': rider.formatted_dist,
            'match_type': rider.match_type,
            'is_live': bool(rider.active_session),
            'live_session_id': rider.active_session.pk if rider.active_session else None,
            'capacity': rider.redis_capacity,
            'mileage': rider.redis_mileage,
            'estimated_range': rider.estimated_range,
            'created_at': rider.created_at.strftime('%d %b %Y') if rider.created_at else '',
        })

    dest_lat = trip.destination_point.y if trip.destination_point else None
    dest_lng = trip.destination_point.x if trip.destination_point else None

    return render(request, 'customer_detail.html', {
        'trip':              trip,
        'group_conn':        group_conn,
        'bike_specs':        bike_specs,
        'estimated_range':   estimated_range,
        'active_session':    active_session,
        'past_sessions':     past_sessions,
        'co_travelers':      co_travelers,
        'co_travelers_json': json.dumps(co_travelers_json),
        'radius_km':         int(radius_km) if radius_km.is_integer() else radius_km,
        'carto_api_key':     os.environ.get('CARTO_API_KEY', ''),
        'dest_lat':          dest_lat,
        'dest_lng':          dest_lng,
    })


# ─── Live Trip Session Views ───────────────────────────────────────────────────

def view_route(request, pk):
    """View-only route map for a BikeTrip (no GPS tracking)"""
    trip = get_object_or_404(BikeTrip, pk=pk)
    group_conn = ConnectionRequest.objects.filter(
        bike_trip=trip,
        status=ConnectionRequest.STATUS_ACCEPTED
    ).select_related('sender', 'receiver').first()
    return render(request, 'trip_map.html', {
        'trip': trip,
        'session': None,
        'view_only': True,
        'group_conn': group_conn,
        'carto_api_key': os.environ.get('CARTO_API_KEY', ''),
    })


def start_trip(request, pk):
    """Start or resume a live trip session for a BikeTrip"""
    trip = get_object_or_404(BikeTrip, pk=pk)
    session = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_ACTIVE).first()
    if not session:
        session = TripSession.objects.create(bike_trip=trip)
    return redirect('trip_map', session_pk=session.pk)


def trip_map(request, session_pk):
    """Live map page for a trip session"""
    session = get_object_or_404(TripSession, pk=session_pk)
    group_conn = ConnectionRequest.objects.filter(
        bike_trip=session.bike_trip,
        status=ConnectionRequest.STATUS_ACCEPTED
    ).select_related('sender', 'receiver').first()
    return render(request, 'trip_map.html', {
        'session': session,
        'group_conn': group_conn,
        'carto_api_key': os.environ.get('CARTO_API_KEY', ''),
    })


@csrf_exempt
def update_location(request, session_pk):
    """API: receive lat/lng from browser and update PostGIS PointField"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    session = get_object_or_404(TripSession, pk=session_pk)
    if not session.is_active:
        return JsonResponse({'error': 'Session is not active'}, status=400)
    try:
        data = json.loads(request.body)
        lat  = float(data['lat'])
        lng  = float(data['lng'])
        session.current_location = Point(lng, lat, srid=4326)
        session.save(update_fields=['current_location', 'updated_at'])
        return JsonResponse({'status': 'ok', 'lat': lat, 'lng': lng})
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return JsonResponse({'error': str(e)}, status=400)


def session_data(request, session_pk):
    """API: return current session state as JSON (for polling / resume)"""
    session = get_object_or_404(TripSession, pk=session_pk)
    return JsonResponse({
        'status':      session.status,
        'is_active':   session.is_active,
        'current_lat': session.current_lat,
        'current_lng': session.current_lng,
        'updated_at':  session.updated_at.isoformat() if session.updated_at else None,
        'bike':        session.bike_trip.bikename,
        'from':        session.bike_trip.starting_name,
        'to':          session.bike_trip.destination_name,
    })


def end_trip(request, session_pk):
    """Mark a session as completed"""
    session = get_object_or_404(TripSession, pk=session_pk)
    session.status = TripSession.STATUS_COMPLETED
    session.save(update_fields=['status'])
    return redirect('customer_detail', pk=session.bike_trip.pk)


def delete_trip(request, pk):
    """Delete a BikeTrip, its sessions, and its Redis specs"""
    trip = get_object_or_404(BikeTrip, pk=pk)
    if request.method == 'POST':
        delete_bike_specs(trip.pk)   # clean up Redis
        trip.delete()
        return redirect('customer_list')
    return redirect('customer_detail', pk=pk)


# ─── AI Views ─────────────────────────────────────────────────────────────────

@csrf_exempt
def generate_ai_tips(request, pk):
    """API: Generate AI tips for the live map (uses Redis specs)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    trip       = get_object_or_404(BikeTrip, pk=pk)
    bike_specs = get_bike_specs(trip.pk)
    capacity   = float(bike_specs.get('capacity', 15))
    mileage    = float(bike_specs.get('mileage',  35))
    max_range  = capacity * mileage

    try:
        data              = json.loads(request.body)
        distance          = data.get('distance', 0)
        duration_mins     = data.get('duration', 0)
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
        import markdown  # pyrefly: ignore [missing-import]
        response_text = generate_content(prompt)
        html = markdown.markdown(response_text)
        return JsonResponse({'status': 'ok', 'html': html})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def generate_customer_summary(request, pk):
    """
    API: Generate AI summary for the customer detail page.
    - Reads bike specs from Redis
    - Reads/writes weather to PostGIS RouteWeather
    - Caches computed fuel/time insights back to Redis
    """
    trip       = get_object_or_404(BikeTrip, pk=pk)
    bike_specs = get_bike_specs(trip.pk)
    capacity   = float(bike_specs.get('capacity', 15))
    mileage    = float(bike_specs.get('mileage',  35))

    try:
        # --- Weather: check PostGIS cache first ---
        cached_weather = RouteWeather.objects.filter(bike_trip=trip)
        if cached_weather.exists():
            weather_text = ' | '.join(w.description for w in cached_weather)
        else:
            # Sample weather at start, midpoint, and destination using Open-Meteo
            weather_text = _fetch_and_store_weather(trip)

        # --- Ask Gemini for full summary ---
        prompt = f"""
You are an intelligent trip analyzer for a motorcycle app.
Bike: {trip.bikename} | From: {trip.starting_name} → {trip.destination_name}
Tank: {capacity}L | Mileage: {mileage} km/l
Weather along route: {weather_text}

Return a concise HTML snippet (use <b>, <br>, <ul>, <li> only — no markdown, no html/body tags):

<b>⛽ Fuel Efficiency & Cost:</b> [mileage] km/l. Consumed: [liters with 10% detour buffer]L ≈ ₹[cost at ₹113/L]<br><br>
<b>🌤️ Route Weather:</b> [1-sentence summary of {weather_text}]<br><br>
<b>⏱️ Total Time:</b> [driving time estimate] driving + [break time], total ≈ [grand total]
"""
        response_text = generate_content(prompt)
        html = response_text.replace('```html', '').replace('```', '').strip()

        # --- Cache AI-derived numbers back to Redis ---
        save_bike_specs(trip.pk, {
            'ai_weather':   weather_text[:200],  # truncated summary
        })

        return JsonResponse({'status': 'ok', 'html': html})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


def _fetch_and_store_weather(trip: BikeTrip) -> str:
    """
    Fetch weather at up to 3 points along the route from Open-Meteo
    and persist each observation as a RouteWeather (PostGIS) record.
    Returns a combined weather description string.
    """
    points = []
    if trip.starting_point:
        points.append(('Start', trip.starting_point))
    if trip.starting_point and trip.destination_point:
        mid_lng = (trip.starting_point.x + trip.destination_point.x) / 2
        mid_lat = (trip.starting_point.y + trip.destination_point.y) / 2
        points.append(('Midpoint', Point(mid_lng, mid_lat, srid=4326)))
    if trip.destination_point:
        points.append(('Destination', trip.destination_point))

    descriptions = []
    wmo_map = {
        0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
        45: 'Foggy', 51: 'Light drizzle', 61: 'Light rain', 63: 'Moderate rain',
        71: 'Light snow', 80: 'Rain showers', 95: 'Thunderstorm',
    }

    for label, pt in points:
        try:
            resp = http_requests.get(
                'https://api.open-meteo.com/v1/forecast',
                params={
                    'latitude': pt.y, 'longitude': pt.x,
                    'current_weather': 'true', 'timezone': 'Asia/Kolkata'
                },
                timeout=5
            )
            cw   = resp.json().get('current_weather', {})
            code = cw.get('weathercode', 0)
            temp = cw.get('temperature', '?')
            desc = wmo_map.get(code, f'Code {code}')
            text = f"{label}: {desc}, {temp}°C"
            descriptions.append(text)
            # Save to PostGIS RouteWeather
            RouteWeather.objects.create(
                bike_trip=trip, location=pt, description=text
            )
        except Exception as e:
            print(f"Weather fetch failed for {label}:", e)

    return ' | '.join(descriptions) if descriptions else 'Weather unavailable'



# Make sure to import the new model at the top of views.py!
# from .models import ConnectionRequest

@login_required
@require_http_methods(["POST"])
def send_connection_request(request):
    """API: Send a connection request to another rider."""
    try:
        data = json.loads(request.body)
        receiver_id = data.get('receiver_id')
        trip_id = data.get('trip_id')

        # Get the target user and trip, return 404 if they don't exist
        receiver = get_object_or_404(User, pk=receiver_id)
        bike_trip = get_object_or_404(BikeTrip, pk=trip_id)

        # Prevent sending a request to yourself
        if request.user == receiver:
            return JsonResponse({'error': 'You cannot connect with yourself.'}, status=400)

        # get_or_create safely handles the unique_together constraint
        conn_req, created = ConnectionRequest.objects.get_or_create(
            sender=request.user,
            receiver=receiver,
            bike_trip=bike_trip,
            defaults={'status': ConnectionRequest.STATUS_PENDING}
        )

        if not created:
            return JsonResponse({'error': 'Request already exists.'}, status=400)

        return JsonResponse({'status': 'ok', 'message': 'Request sent successfully!'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def respond_connection_request(request, req_id):
    """API: Accept or reject an incoming request."""
    conn_req = get_object_or_404(ConnectionRequest, pk=req_id)

    # SECURITY CHECK: Ensure only the intended receiver can accept/reject
    if request.user != conn_req.receiver:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        action = data.get('action')  # Expected to be 'accept' or 'reject'

        if action == 'accept':
            conn_req.status = ConnectionRequest.STATUS_ACCEPTED
            conn_req.save(update_fields=['status', 'updated_at'])
            return JsonResponse({'status': 'ok', 'message': 'Connection accepted!'})
        
        elif action == 'reject':
            conn_req.status = ConnectionRequest.STATUS_REJECTED
            conn_req.save(update_fields=['status', 'updated_at'])
            return JsonResponse({'status': 'ok', 'message': 'Connection rejected.'})
        
        else:
            return JsonResponse({'error': 'Invalid action. Use accept or reject.'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def my_invitations(request):
    """Render an HTML page listing all incoming, accepted, and sent requests for the user."""
    incoming_requests = ConnectionRequest.objects.filter(
        receiver=request.user, 
        status=ConnectionRequest.STATUS_PENDING
    ).select_related('sender', 'bike_trip')

    sent_requests = ConnectionRequest.objects.filter(
        sender=request.user
    ).select_related('receiver', 'bike_trip')

    accepted_requests = ConnectionRequest.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user),
        status=ConnectionRequest.STATUS_ACCEPTED
    ).select_related('sender', 'receiver', 'bike_trip')

    return render(request, 'invitations.html', {
        'invitations': incoming_requests,
        'sent_requests': sent_requests,
        'accepted_requests': accepted_requests,
        'pending_count': incoming_requests.count(),
        'accepted_count': accepted_requests.count(),
    })