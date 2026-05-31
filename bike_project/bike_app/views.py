import json
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib.gis.geos import Point
# pyrefly: ignore [missing-import]

# pyrefly: ignore [missing-import]
from .models import BikeTrip, TripSession


# ─── Bike Trip Form ────────────────────────────────────────────────────────────

def bike_form(request):
    """Display the bike information form"""
    return render(request, 'bike_form.html')


@require_http_methods(["POST"])
def bike_submit(request):
    """Handle bike form submission"""
    bikename = request.POST.get('bikename')
    starting_location = request.POST.get('starting_location', '')
    destination_location = request.POST.get('destination_location')
    
    # Auto-fetch specs using Gemini
    try:
        from google import genai
        from dotenv import load_dotenv
        import json
        import os
        load_dotenv()
        client = genai.Client()
        prompt = f"Return the average fuel tank capacity (liters) and average mileage (km/l) for the motorcycle model '{bikename}'. Return strictly a JSON object with keys 'capacity' and 'mileage'. Example: {{\"capacity\": 15, \"mileage\": 35}}"
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw_text = response.text.replace('```json', '').replace('```', '').strip()
        specs = json.loads(raw_text)
        capacity = float(specs.get('capacity', 15))
        mileage = float(specs.get('mileage', 35))
    except Exception as e:
        print("Gemini auto-detect failed:", e)
        capacity = 15.0
        mileage = 35.0

    BikeTrip.objects.create(
        bikename=bikename,
        fueltank_capacity=capacity,
        average_mileage=mileage,
        starting_location=starting_location,
        destination_location=destination_location,
    )
    return redirect('customer_list')


def bike_success(request):
    """Display success message after form submission"""
    return render(request, 'bike_success.html')


# ─── Customer Views ────────────────────────────────────────────────────────────

def customer_list(request):
    """Home page — all bike trip records"""
    trips = BikeTrip.objects.all()
    # Annotate each trip with its active session (if any)
    active_sessions = {
        s.bike_trip.pk: s
        for s in TripSession.objects.filter(status=TripSession.STATUS_ACTIVE).select_related('bike_trip')
    }
    for trip in trips:
        trip.active_session = active_sessions.get(trip.pk)  # type: ignore[attr-defined]
    return render(request, 'customer_list.html', {
        'trips': trips,
        'active_count': len(active_sessions),
    })


def customer_detail(request, pk):
    """Full details of a single bike trip record"""
    trip = get_object_or_404(BikeTrip, pk=pk)
    estimated_range = trip.fueltank_capacity * trip.average_mileage
    active_session  = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_ACTIVE).first()
    past_sessions   = TripSession.objects.filter(bike_trip=trip, status=TripSession.STATUS_COMPLETED)
    return render(request, 'customer_detail.html', {
        'trip': trip,
        'estimated_range': estimated_range,
        'active_session': active_session,
        'past_sessions': past_sessions,
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
    # Reuse existing active session, or create a new one
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
        # starting_location is always kept as entered by the user in the form
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
        'from':        session.bike_trip.starting_location,
        'to':          session.bike_trip.destination_location,
    })


def pause_trip(request, session_pk):
    """Mark a session as paused (taking a break)"""
    session = get_object_or_404(TripSession, pk=session_pk)
    session.status = TripSession.STATUS_PAUSED  # type: ignore[attr-defined]
    session.save(update_fields=['status'])
    return redirect('customer_detail', pk=session.bike_trip.pk)


def end_trip(request, session_pk):
    """Mark a session as completed"""
    session = get_object_or_404(TripSession, pk=session_pk)
    session.status = TripSession.STATUS_COMPLETED
    session.save(update_fields=['status'])
    return redirect('customer_detail', pk=session.bike_trip.pk)


def delete_trip(request, pk):
    """Delete a BikeTrip and all its sessions"""
    trip = get_object_or_404(BikeTrip, pk=pk)
    if request.method == 'POST':
        trip.delete()
        return redirect('customer_list')
    return redirect('customer_detail', pk=pk)


@csrf_exempt
def generate_ai_tips(request, pk):
    """API: Generate AI tips using Google Gemini"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    trip = get_object_or_404(BikeTrip, pk=pk)
    
    try:
        data = json.loads(request.body)
        distance = data.get('distance', 0)
        duration_mins = data.get('duration', 0)
        weather_conditions = data.get('weather', [])
        
        # Calculate bike capabilities
        max_range = trip.fueltank_capacity * trip.average_mileage
        
        # Construct the prompt
        weather_text = ", ".join(weather_conditions) if weather_conditions else "Unknown weather"
        prompt = f"""
You are an expert motorcycle touring advisor. 
The user is planning a trip on their {trip.bikename} from {trip.starting_location} to {trip.destination_location}.
The total trip distance is {distance} km.
The estimated pure driving time is {duration_mins} minutes.
The bike has a maximum fuel range of {max_range} km (based on {trip.fueltank_capacity}L tank and {trip.average_mileage} km/l).
The weather forecast along the route is: {weather_text}.

Please provide a highly detailed but well-formatted advisory covering exactly these points:
1. **Total Estimated Fuel Cost:** Assume a rough average price of ₹100 per liter (or equivalent local currency). Calculate the total liters needed and the total cost.
2. **Total Trip Time & Break Schedule:** Calculate the total trip time including recommended breaks. Tell them exactly when/where to take breaks (e.g. "Take a 15-min break every X hours").
3. **Route & Safety Advice:** Give advice on navigating this route considering the provided weather forecast and distance. Keep it punchy!
"""
        import os
        # pyrefly: ignore [missing-import]
        from google import genai
        import markdown
        from dotenv import load_dotenv
        
        # Load environment variables from .env file
        load_dotenv()
        
        client = genai.Client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        # Convert markdown response to HTML for easy rendering
        html_response = markdown.markdown(response.text)
        
        return JsonResponse({'status': 'ok', 'html': html_response})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def generate_customer_summary(request, pk):
    """Generate AI summary for the customer detail page"""
    trip = get_object_or_404(BikeTrip, pk=pk)
    
    try:
        from google import genai
        import markdown
        from dotenv import load_dotenv
        
        load_dotenv()
        client = genai.Client()
        
        prompt = f"""
You are an intelligent trip analyzer.
The user is traveling on a {trip.bikename} from {trip.starting_location} to {trip.destination_location}.
The bike's fuel capacity is {trip.fueltank_capacity}L and its average mileage is {trip.average_mileage} km/l.

Calculate the details and provide a highly concise, visually clean HTML breakdown (using simple HTML tags like <b>, <br>, no markdown wrappers).
Format EXACTLY as follows with these exact bold headings:

<b>⛽ Fuel Efficiency & Cost:</b> Approx {trip.average_mileage} km/l. Fuel consumed: [calculate liters consumed including a 10% detour buffer]. Total cost: approx ₹[calculate cost assuming ₹100/L]<br><br>
<b>🌤️ Route Weather:</b> [give a brief expected weather summary for a trip between these locations]<br><br>
<b>⏱️ Total Time:</b> [estimate total driving time] plus [estimate break time], total: [calculate total time including periodic breaks based on the estimated distance].
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        html_response = response.text.replace('```html', '').replace('```', '').strip()
        
        return JsonResponse({'status': 'ok', 'html': html_response})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
