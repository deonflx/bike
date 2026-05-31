import json
import os
import requests as http_requests

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib.gis.geos import Point
from dotenv import load_dotenv

load_dotenv()

# pyrefly: ignore [missing-import]
from .models import BikeTrip, TripSession, RouteWeather
from .redis_client import save_bike_specs, get_bike_specs, delete_bike_specs


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
            headers={'User-Agent': 'BikeApp/1.0'},
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


def _gemini_client():
    from google import genai  # pyrefly: ignore [missing-import]
    return genai.Client()


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

    # 1. Geocode locations (PostGIS)
    starting_point    = _geocode(starting_name)
    destination_point = _geocode(destination_name)

    # 2. Fetch bike specs via Gemini (will go to Redis)
    try:
        client = _gemini_client()
        prompt = (
            f"Return the average fuel tank capacity (liters) and average mileage (km/l) "
            f"for the motorcycle model '{bikename}'. "
            f"Return ONLY a JSON object with keys 'capacity' and 'mileage'. "
            f"Example: {{\"capacity\": 15, \"mileage\": 35}}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw_text = response.text.replace('```json', '').replace('```', '').strip()
        specs    = json.loads(raw_text)
        capacity = float(specs.get('capacity', 15))
        mileage  = float(specs.get('mileage', 35))
    except Exception as e:
        print("Gemini spec lookup failed:", e)
        capacity = 15.0
        mileage  = 35.0

    # 3. Save slim trip to PostGIS (location only)
    trip = BikeTrip.objects.create(
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

    return redirect('customer_list')


def bike_success(request):
    """Display success message after form submission"""
    return render(request, 'bike_success.html')


# ─── Customer Views ────────────────────────────────────────────────────────────

def customer_list(request):
    """Home page — all bike trip records"""
    trips = BikeTrip.objects.all()
    active_sessions = {
        s.bike_trip.pk: s
        for s in TripSession.objects.filter(status=TripSession.STATUS_ACTIVE).select_related('bike_trip')
    }
    for trip in trips:
        trip.active_session = active_sessions.get(trip.pk)  # type: ignore[attr-defined]
        # Attach Redis specs for table display
        specs = get_bike_specs(trip.pk)
        trip.redis_capacity = specs.get('capacity', '—')   # type: ignore[attr-defined]
        trip.redis_mileage  = specs.get('mileage',  '—')   # type: ignore[attr-defined]
    return render(request, 'customer_list.html', {
        'trips': trips,
        'active_count': len(active_sessions),
    })


def customer_detail(request, pk):
    """Full details of a single bike trip record"""
    trip = get_object_or_404(BikeTrip, pk=pk)

    # Fetch bike specs from Redis
    bike_specs = get_bike_specs(trip.pk)
    capacity   = float(bike_specs.get('capacity', 0))
    mileage    = float(bike_specs.get('mileage',  0))
    estimated_range = capacity * mileage if capacity and mileage else 0

    active_session = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_ACTIVE).first()
    past_sessions  = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_COMPLETED)

    return render(request, 'customer_detail.html', {
        'trip':            trip,
        'bike_specs':      bike_specs,
        'estimated_range': estimated_range,
        'active_session':  active_session,
        'past_sessions':   past_sessions,
    })


# ─── Live Trip Session Views ───────────────────────────────────────────────────

def view_route(request, pk):
    """View-only route map for a BikeTrip (no GPS tracking)"""
    trip = get_object_or_404(BikeTrip, pk=pk)
    return render(request, 'trip_map.html', {
        'trip': trip,
        'session': None,
        'view_only': True,
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
    return render(request, 'trip_map.html', {'session': session})


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
1. Total estimated fuel cost (₹100/L assumed)
2. Total trip time with a break schedule
3. Route & safety advice given the weather
"""
        import markdown  # pyrefly: ignore [missing-import]
        client   = _gemini_client()
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        html     = markdown.markdown(response.text)
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

<b>⛽ Fuel Efficiency & Cost:</b> [mileage] km/l. Consumed: [liters with 10% detour buffer]L ≈ ₹[cost at ₹100/L]<br><br>
<b>🌤️ Route Weather:</b> [1-sentence summary of {weather_text}]<br><br>
<b>⏱️ Total Time:</b> [driving time estimate] driving + [break time], total ≈ [grand total]
"""
        client   = _gemini_client()
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        html     = response.text.replace('```html', '').replace('```', '').strip()

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
