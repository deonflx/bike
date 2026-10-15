import math
import time
import requests as http_requests
from django.contrib.gis.geos import Point, LineString

from .models import BikeTrip, RouteWeather


def _attach_spec_display(trip):
    """Template-friendly capacity/mileage from Postgres (legacy redis_* names)."""
    trip.redis_capacity = trip.capacity if trip.capacity is not None else '—'
    trip.redis_mileage = trip.mileage if trip.mileage is not None else '—'
    return trip


def _trip_capacity_mileage(trip, default_capacity=15.0, default_mileage=35.0):
    capacity = trip.capacity if trip.capacity is not None else default_capacity
    mileage = trip.mileage if trip.mileage is not None else default_mileage
    return float(capacity), float(mileage)


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


def _get_or_create_route_path(trip: BikeTrip):
    """
    Ensures trip has a valid LineString route_path.
    If missing, fetches driving route from OSRM and saves it to PostGIS.
    """
    if trip.route_path:
        return trip.route_path
    if not (trip.starting_point and trip.destination_point):
        return None
    try:
        start_lng, start_lat = trip.starting_point.x, trip.starting_point.y
        dest_lng, dest_lat = trip.destination_point.x, trip.destination_point.y
        osrm_url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{start_lng},{start_lat};{dest_lng},{dest_lat}"
            f"?overview=full&geometries=geojson"
        )
        r = http_requests.get(osrm_url, timeout=4.0)
        data = r.json()
        if data.get('code') == 'Ok' and data.get('routes'):
            coords = data['routes'][0]['geometry']['coordinates']
            if len(coords) >= 2:
                trip.route_path = LineString(coords, srid=4326)
                trip.save(update_fields=['route_path'])
                print(f"[Auto-Heal Route] Saved route_path for Trip #{trip.pk} ({len(coords)} points)")
                return trip.route_path
    except Exception as e:
        print(f"Failed to fetch route geometry for Trip #{trip.pk}: {e}")

    # Fallback: straight-line geometry
    try:
        trip.route_path = LineString([
            [trip.starting_point.x, trip.starting_point.y],
            [trip.destination_point.x, trip.destination_point.y]
        ], srid=4326)
        trip.save(update_fields=['route_path'])
        return trip.route_path
    except Exception:
        return None


def _calculate_route_overlap(trip_a: BikeTrip, trip_b: BikeTrip):
    """
    Calculates the spatial overlap between two routes using a ~1.5km corridor buffer.
    Returns a dict with:
      - shared_km: float (distance in km of shared route)
      - overlap_pct: float (% of trip_a's route that overlaps with trip_b)
      - is_same_direction: bool (True if both travel in generally the same direction)
      - is_match: bool (True if shared_km >= 5 km or overlap >= 20%)
    """
    path_a = trip_a.route_path or _get_or_create_route_path(trip_a)
    path_b = trip_b.route_path or _get_or_create_route_path(trip_b)

    if not path_a or not path_b:
        return {'shared_km': 0.0, 'overlap_pct': 0.0, 'is_same_direction': False, 'is_match': False}

    try:
        # 1. Travel direction check (Dot product of start -> end vector)
        coords_a = list(path_a.coords)
        coords_b = list(path_b.coords)
        start_a, dest_a = coords_a[0], coords_a[-1]
        start_b, dest_b = coords_b[0], coords_b[-1]

        vec_a_x, vec_a_y = dest_a[0] - start_a[0], dest_a[1] - start_a[1]
        vec_b_x, vec_b_y = dest_b[0] - start_b[0], dest_b[1] - start_b[1]

        mag_a = math.sqrt(vec_a_x**2 + vec_a_y**2)
        mag_b = math.sqrt(vec_b_x**2 + vec_b_y**2)

        is_same_direction = True
        if mag_a > 0 and mag_b > 0:
            cos_sim = (vec_a_x * vec_b_x + vec_a_y * vec_b_y) / (mag_a * mag_b)
            # >= 0 means angle <= 90 deg (same general travel direction)
            is_same_direction = cos_sim >= 0.0

        # 2. Corridor buffer intersection in GEOS (0.015 degrees ~= 1.6 km road corridor)
        corridor_a = path_a.buffer(0.015)
        intersection = corridor_a.intersection(path_b)

        shared_km = 0.0
        if not intersection.empty:
            geom_type = intersection.geom_type
            if geom_type == 'LineString':
                icoords = list(intersection.coords)
                for i in range(len(icoords) - 1):
                    shared_km += _haversine_km(icoords[i][1], icoords[i][0], icoords[i+1][1], icoords[i+1][0])
            elif geom_type == 'MultiLineString':
                for line in intersection:
                    icoords = list(line.coords)
                    for i in range(len(icoords) - 1):
                        shared_km += _haversine_km(icoords[i][1], icoords[i][0], icoords[i+1][1], icoords[i+1][0])
            elif geom_type == 'GeometryCollection':
                for geom in intersection:
                    if geom.geom_type in ('LineString', 'MultiLineString'):
                        lines = [geom] if geom.geom_type == 'LineString' else list(geom)
                        for line in lines:
                            icoords = list(line.coords)
                            for i in range(len(icoords) - 1):
                                shared_km += _haversine_km(icoords[i][1], icoords[i][0], icoords[i+1][1], icoords[i+1][0])

        shared_km = round(shared_km, 1)

        # Total distance of path_a
        total_a_km = 0.0
        for i in range(len(coords_a) - 1):
            total_a_km += _haversine_km(coords_a[i][1], coords_a[i][0], coords_a[i+1][1], coords_a[i+1][0])

        overlap_pct = round((shared_km / total_a_km * 100), 1) if total_a_km > 0 else 0.0
        overlap_pct = min(100.0, overlap_pct)

        # Significant match if shared route is >= 5km OR overlap >= 20% (with at least 2km)
        is_match = (shared_km >= 5.0) or (overlap_pct >= 20.0 and shared_km >= 2.0)

        return {
            'shared_km': shared_km,
            'overlap_pct': overlap_pct,
            'is_same_direction': is_same_direction,
            'is_match': is_match,
        }
    except Exception as e:
        print(f"Error computing route overlap: {e}")
        return {'shared_km': 0.0, 'overlap_pct': 0.0, 'is_same_direction': False, 'is_match': False}


def _compute_refuel_point_and_pumps(starting_point, destination_point, capacity, mileage):
    """
    1. Query OSRM for the actual driving route geometry & distance.
    2. Walk along road coordinates until accumulated distance = 70% of max fuel range.
    3. Query Overpass API for amenity=fuel within 2 km of that highway point.
    Returns a dict with refuel_point, total_distance_km, and stations list.
    Falls back to straight-line interpolation if OSRM fails.
    """
    max_range_km = capacity * mileage
    refuel_target_km = max_range_km * 0.70

    start_lng, start_lat = starting_point.x, starting_point.y
    dest_lng, dest_lat = destination_point.x, destination_point.y

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
            'coords': coords,
        }

    # ── Step 3: Find refuel point along route using GeoDjango GEOS ───────
    route_line = LineString(coords)
    fraction = min(refuel_target_km / total_distance_km, 1.0) if total_distance_km > 0 else 0.0
    refuel_point = route_line.interpolate_normalized(fraction)
    refuel_lng, refuel_lat = refuel_point.x, refuel_point.y

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
        'coords': coords,
    }


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
            cw = resp.json().get('current_weather', {})
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
