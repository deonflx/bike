import json
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib.gis.geos import Point
# pyrefly: ignore [missing-import]
from .models import BikeTrip, TripSession


# ─── Bike Trip Form ────────────────────────────────────────────────────────────

def bike_form(request):
    """Display the bike information form"""
    return render(request, 'bike_form.html')


@require_http_methods(["POST"])
def bike_submit(request):
    """Handle bike form submission"""
    BikeTrip.objects.create(
        bikename=request.POST.get('bikename'),
        fueltank_capacity=float(request.POST.get('fueltank_capacity')),
        average_mileage=float(request.POST.get('average_mileage')),
        starting_location=request.POST.get('starting_location', ''),
        destination_location=request.POST.get('destination_location'),
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
