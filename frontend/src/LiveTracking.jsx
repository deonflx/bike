import { useEffect, useState, useRef, useMemo } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './App.css';
import api from './api';

const CARTO_API_KEY = import.meta.env.VITE_CARTO_API_KEY || '';
const CARTO_KEY_PARAM = CARTO_API_KEY ? `?key=${CARTO_API_KEY}` : '';

// ── Custom Leaflet Icons ──────────────────────────────────────────────────────
const startIcon = L.divIcon({
  html: '<div class="start-pin"><span>○</span></div>',
  className: '',
  iconSize: [28, 28],
  iconAnchor: [14, 28],
  popupAnchor: [0, -32],
});

const endIcon = L.divIcon({
  html: '<div class="end-pin"><span>◉</span></div>',
  className: '',
  iconSize: [28, 28],
  iconAnchor: [14, 28],
  popupAnchor: [0, -32],
});

const riderIcon = L.divIcon({
  html: '<div class="pulse-ring"></div>',
  className: '',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
  popupAnchor: [0, -10],
});

const refuelIcon = L.divIcon({
  html: '<div class="fuel-point"></div>',
  className: '',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
  popupAnchor: [0, -10],
});

const createStationIcon = (name, dist) =>
  L.divIcon({
    html: `<div class="station-pip"><div class="station-pip-name">⛽ ${name}</div><div class="station-pip-dist">${dist} km</div></div>`,
    className: '',
    iconAnchor: [50, 40],
    popupAnchor: [0, -30],
  });

const createWxIcon = (city, emoji, temp, wind) =>
  L.divIcon({
    html: `<div class="wx-pip"><div class="wx-city">${city}</div><div class="wx-data">${emoji} ${temp}°C <span style="color:var(--text-3);font-size:10px;">💨${wind}</span></div></div>`,
    className: '',
    iconAnchor: [40, 50],
    popupAnchor: [0, -40],
  });

// ── Weather Code Interpreter ──────────────────────────────────────────────────
const WX_CODE = (c) =>
  c === 0 ? '☀' : c <= 3 ? '⛅' : c <= 48 ? '🌫' : c <= 67 ? '🌧' : c <= 77 ? '❄' : c >= 95 ? '⛈' : '🌤';

// ── Haversine Distance in KM ──────────────────────────────────────────────────
function haversine([lat1, lon1], [lat2, lon2]) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ── Nominatim Geocode Fallback ─────────────────────────────────────────────────
async function geocode(q) {
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1&countrycodes=in`,
      { headers: { 'Accept-Language': 'en' } }
    );
    const d = await r.json();
    if (d && d.length) return [parseFloat(d[0].lat), parseFloat(d[0].lon)];
  } catch (e) {
    console.warn('Geocode error:', e);
  }
  return null;
}

// ── Map Controller (Fit Bounds & Pan) ─────────────────────────────────────────
function MapController({ startCoords, endCoords, panTarget }) {
  const map = useMap();
  const fittedRef = useRef(false);

  useEffect(() => {
    if (panTarget) {
      map.panTo(panTarget, { animate: true });
    }
  }, [panTarget, map]);

  useEffect(() => {
    if (!fittedRef.current && startCoords && endCoords) {
      const bounds = L.latLngBounds([startCoords, endCoords]);
      map.fitBounds(bounds, { padding: [80, 80] });
      fittedRef.current = true;
    }
  }, [startCoords, endCoords, map]);

  return null;
}

// ── Main LiveTracking & Route Preview Component ────────────────────────────────
function LiveTracking({ viewOnly = false }) {
  const { id, sessionId } = useParams();
  const navigate = useNavigate();

  // Core Data
  const [trip, setTrip] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toastMsg, setToastMsg] = useState('Loading route telemetries…');

  // Coordinates & Route
  const [startCoords, setStartCoords] = useState(null);
  const [endCoords, setEndCoords] = useState(null);
  const [currentCoords, setCurrentCoords] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [routeCoords, setRouteCoords] = useState([]);
  const [routeDistKm, setRouteDistKm] = useState(0);
  const [routeDurMins, setRouteDurMins] = useState(0);

  // Weather along route (rendered as pips on map)
  const [weatherMarkers, setWeatherMarkers] = useState([]);
  const [currentWx, setCurrentWx] = useState([]);
  const [weatherLoading, setWeatherLoading] = useState(false);

  // Side Panels (Trip Advice & Fuel)
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiHtml, setAiHtml] = useState(null);
  const [aiLoaded, setAiLoaded] = useState(false);

  const [fuelPanelOpen, setFuelPanelOpen] = useState(false);
  const [fuelLoading, setFuelLoading] = useState(false);
  const [fuelData, setFuelData] = useState(null);
  const [fuelLoaded, setFuelLoaded] = useState(false);

  const [panTarget, setPanTarget] = useState(null);
  const [tracking, setTracking] = useState(false);
  const [startingSession, setStartingSession] = useState(false);

  const watchIdRef = useRef(null);

  // Auto-hide toast helper
  const showToast = (msg, duration = 3000) => {
    setToastMsg(msg);
    if (duration > 0) {
      setTimeout(() => setToastMsg(null), duration);
    }
  };

  // Determine active trip ID
  const tripId = useMemo(() => {
    if (viewOnly) return id;
    return session?.bike_trip;
  }, [viewOnly, id, session]);

  // 1. Initial Data Fetch (Trip or Session)
  useEffect(() => {
    setLoading(true);
    if (viewOnly) {
      api.get(`/trips/${id}/`)
        .then((res) => {
          setTrip(res.data);
          resolveCoords(res.data);
          setLoading(false);
        })
        .catch((err) => {
          console.error(err);
          setError('Failed to load expedition route preview.');
          setLoading(false);
        });
    } else {
      api.get(`/sessions/${sessionId}/`)
        .then((res) => {
          setSession(res.data);
          if (res.data.current_lat && res.data.current_lng) {
            setCurrentCoords([res.data.current_lat, res.data.current_lng]);
          }
          resolveSessionCoords(res.data);
          setLoading(false);
        })
        .catch((err) => {
          console.error(err);
          setError('Failed to load active tracking session.');
          setLoading(false);
        });
    }
  }, [viewOnly, id, sessionId]);

  // Resolve start/end coords for Route Preview
  const resolveCoords = async (tripData) => {
    let sCoords = null;
    let eCoords = null;

    if (tripData.starting_coords?.lat && tripData.starting_coords?.lng) {
      sCoords = [tripData.starting_coords.lat, tripData.starting_coords.lng];
    } else if (tripData.starting_name) {
      sCoords = await geocode(tripData.starting_name);
    }

    if (tripData.destination_coords?.lat && tripData.destination_coords?.lng) {
      eCoords = [tripData.destination_coords.lat, tripData.destination_coords.lng];
    } else if (tripData.destination_name) {
      eCoords = await geocode(tripData.destination_name);
    }

    setStartCoords(sCoords);
    setEndCoords(eCoords);

    if (sCoords && eCoords) {
      fetchOSRMRoute(sCoords, eCoords);
    }
  };

  // Resolve coords for Live Session
  const resolveSessionCoords = async (sessionData) => {
    let sCoords = null;
    let eCoords = null;

    if (sessionData.start_coords?.lat && sessionData.start_coords?.lng) {
      sCoords = [sessionData.start_coords.lat, sessionData.start_coords.lng];
    } else if (sessionData.starting_name) {
      sCoords = await geocode(sessionData.starting_name);
    }

    if (sessionData.dest_coords?.lat && sessionData.dest_coords?.lng) {
      eCoords = [sessionData.dest_coords.lat, sessionData.dest_coords.lng];
    } else if (sessionData.destination_name) {
      eCoords = await geocode(sessionData.destination_name);
    }

    setStartCoords(sCoords);
    setEndCoords(eCoords);

    if (sCoords && eCoords) {
      fetchOSRMRoute(sCoords, eCoords);
    }
  };

  // 2. Fetch OSRM Route & Trigger Weather Pipeline
  const fetchOSRMRoute = async (sCoords, eCoords) => {
    showToast('Calculating optimal route…', 2000);
    const coordStr = `${sCoords[1]},${sCoords[0]};${eCoords[1]},${eCoords[0]}`;
    try {
      const res = await fetch(
        `https://router.project-osrm.org/route/v1/driving/${coordStr}?overview=full&geometries=geojson`
      );
      const data = await res.json();
      if (data.routes && data.routes.length > 0) {
        const route = data.routes[0];
        const pts = route.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
        setRouteCoords(pts);
        setRouteDistKm(parseFloat((route.distance / 1000).toFixed(1)));
        setRouteDurMins(Math.round(route.duration / 60));
        showToast('Route corridor established', 2500);

        // Fetch weather along the route points
        fetchRouteWeather(pts);
        return;
      }
    } catch (e) {
      console.warn('OSRM error, using direct line fallback:', e);
    }
    // Fallback: straight line
    setRouteCoords([sCoords, eCoords]);
    const fallbackDist = haversine(sCoords, eCoords);
    setRouteDistKm(parseFloat(fallbackDist.toFixed(1)));
    fetchRouteWeather([sCoords, eCoords]);
  };

  // 3. Weather Fetcher (Samples 5 points along route: Open-Meteo + Reverse Geocoding)
  const fetchRouteWeather = async (coords) => {
    if (!coords || coords.length === 0) return;
    setWeatherLoading(true);
    const fractions = [0, 0.25, 0.5, 0.75, 1];
    const samplePoints = fractions.map((f) => coords[Math.floor(f * (coords.length - 1))]);

    const newWxMarkers = [];
    const newWxStrings = [];

    for (let i = 0; i < samplePoints.length; i++) {
      const [lat, lng] = samplePoints[i];
      try {
        const [wxRes, geoRes] = await Promise.all([
          fetch(
            `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}&current=temperature_2m,weather_code,wind_speed_10m&timezone=auto`
          ).then((r) => r.json()),
          fetch(
            `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lng}&localityLanguage=en`
          ).then((r) => r.json()),
        ]);

        const wx = wxRes.current;
        if (wx) {
          const city = geoRes.city || geoRes.locality || (i === 0 ? 'Start' : i === 4 ? 'Destination' : 'Route');
          const emoji = WX_CODE(wx.weather_code);
          const temp = Math.round(wx.temperature_2m);
          const wind = Math.round(wx.wind_speed_10m);

          newWxStrings.push(`${city}: ${emoji} ${temp}°C, ${wind}km/h`);
          newWxMarkers.push({
            id: `wx-${i}`,
            lat,
            lng,
            city,
            emoji,
            temp,
            wind,
          });
        }
      } catch (err) {
        console.warn('Weather fetch warning for point:', err);
      }
    }

    setWeatherMarkers(newWxMarkers);
    setCurrentWx(newWxStrings);
    setWeatherLoading(false);
    if (newWxMarkers.length > 0) {
      showToast(`Weather live on map (${newWxMarkers.length} stations)`, 3000);
    }
  };

  // 4. AI Trip Advice Side Panel
  const openAI = () => {
    setFuelPanelOpen(false);
    setAiPanelOpen(true);
    if (!aiLoaded) {
      fetchAiAdvice(false);
    }
  };

  const closeAI = () => setAiPanelOpen(false);

  const fetchAiAdvice = (forceRefresh = false) => {
    const targetTripId = tripId || trip?.id || session?.bike_trip;
    if (!targetTripId) return;

    setAiLoading(true);
    api.post(`/trips/${targetTripId}/ai_tips/`, {
      distance: routeDistKm,
      duration: routeDurMins,
      weather: currentWx,
      refresh: forceRefresh,
    })
      .then((res) => {
        setAiHtml(res.data.html);
        setAiLoaded(true);
        setAiLoading(false);
      })
      .catch((err) => {
        console.error('AI Tips DRF failed, trying django direct:', err);
        // Fallback to customer ai-tips endpoint
        fetch(`/customers/${targetTripId}/ai-tips/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            distance: routeDistKm,
            duration: routeDurMins,
            weather: currentWx,
            refresh: forceRefresh,
          }),
        })
          .then((r) => r.json())
          .then((data) => {
            setAiHtml(data.html || data.error);
            setAiLoaded(true);
            setAiLoading(false);
          })
          .catch((e) => {
            setAiHtml(`<div style="color:var(--signal);">Failed to load Trip Advice: ${e.message}</div>`);
            setAiLoading(false);
          });
      });
  };

  // 5. Fuel Stops Side Panel
  const toggleFuel = () => {
    if (fuelPanelOpen) {
      setFuelPanelOpen(false);
      return;
    }
    setAiPanelOpen(false);
    setFuelPanelOpen(true);
    if (!fuelLoaded) {
      fetchFuelStops();
    }
  };

  const closeFuel = () => setFuelPanelOpen(false);

  const fetchFuelStops = () => {
    const targetTripId = tripId || trip?.id || session?.bike_trip;
    if (!targetTripId) return;

    setFuelLoading(true);
    api.get(`/trips/${targetTripId}/fuel_stops/`)
      .then((res) => {
        setFuelData(res.data);
        setFuelLoaded(true);
        setFuelLoading(false);
        if (res.data.refuel_point?.lat && res.data.refuel_point?.lng) {
          setPanTarget([res.data.refuel_point.lat, res.data.refuel_point.lng]);
        }
      })
      .catch((err) => {
        console.error(err);
        setFuelLoading(false);
      });
  };

  // 6. Live GPS Watch & Location Push
  const toggleTracking = () => {
    if (tracking) {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
      setTracking(false);
      showToast('GPS tracking paused', 2000);
    } else {
      if (!navigator.geolocation) {
        alert('Geolocation is not supported by your browser.');
        return;
      }
      setTracking(true);
      showToast('Acquiring high-accuracy GPS signal…', 3000);

      watchIdRef.current = navigator.geolocation.watchPosition(
        (position) => {
          const lat = position.coords.latitude;
          const lng = position.coords.longitude;
          const acc = position.coords.accuracy;
          setCurrentCoords([lat, lng]);
          setAccuracy(Math.round(acc));

          if (sessionId) {
            api.patch(`/sessions/${sessionId}/`, { lat, lng })
              .then((res) => {
                setSession((prev) => ({ ...prev, ...res.data }));
              })
              .catch((err) => console.error('GPS telemetry sync error:', err));
          }
        },
        (err) => {
          console.warn('Geolocation error:', err.message);
          showToast(`GPS error: ${err.message}`, 4000);
        },
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 2500 }
      );
    }
  };

  // Cleanup GPS watcher on unmount
  useEffect(() => {
    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, []);

  // 7. Start Trip (Convert Preview to Live Session)
  const handleStartTripFromPreview = () => {
    setStartingSession(true);
    api.post(`/trips/${id}/start_session/`)
      .then((res) => {
        navigate(`/tracking/${res.data.id}`);
      })
      .catch((err) => {
        console.error(err);
        alert('Could not initialize live tracking session.');
        setStartingSession(false);
      });
  };

  // 8. End Trip Action
  const handleEndTrip = () => {
    if (!window.confirm('Conclude active live expedition?')) return;
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current);
    }
    api.post(`/sessions/${sessionId}/end_session/`)
      .then((res) => {
        alert('Expedition marked as COMPLETED.');
        navigate(`/trips/${res.data.bike_trip}`);
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to end session.');
      });
  };

  // Calculate live covered and remaining distance
  const distTravelled = useMemo(() => {
    if (startCoords && currentCoords) {
      return haversine(startCoords, currentCoords).toFixed(1);
    }
    return '0.0';
  }, [startCoords, currentCoords]);

  const distRemaining = useMemo(() => {
    if (endCoords && currentCoords) {
      return haversine(currentCoords, endCoords).toFixed(1);
    }
    if (startCoords && endCoords && !currentCoords) {
      return routeDistKm > 0 ? routeDistKm.toFixed(1) : haversine(startCoords, endCoords).toFixed(1);
    }
    return '—';
  }, [endCoords, currentCoords, startCoords, routeDistKm]);

  if (loading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh', color: 'var(--text-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div className="ai-spinner"></div> Loading route telemetries & live weather…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--signal)' }}>{error}</div>
    );
  }

  const bikename = viewOnly ? trip?.bikename : session?.bikename;
  const startName = viewOnly ? trip?.starting_name : session?.starting_name;
  const destName = viewOnly ? trip?.destination_name : session?.destination_name;
  const detailLink = viewOnly ? `/trips/${id}` : `/trips/${session?.bike_trip}`;

  const defaultCenter = currentCoords || startCoords || [12.9716, 77.5946];

  return (
    <div>
      {/* ── TOPBAR (Matching trip_map.html exactly) ── */}
      <div className="topbar">
        <Link to="/" className="brand" style={{ textDecoration: 'none' }}>
          <div className="brand-mark">⬡</div>
        </Link>
        <div className="topbar-divider"></div>
        <div>
          <div className="trip-name">{bikename || 'Expedition'}</div>
          <div className="trip-sub">{viewOnly ? 'Route Preview' : 'Live Tracking'}</div>
        </div>

        {viewOnly ? (
          <div className="mode-badge mode-route">ROUTE</div>
        ) : (
          <div className="mode-badge mode-live">
            <div className="live-dot"></div>LIVE
          </div>
        )}

        <div className="topbar-right">
          <Link to={detailLink} className="btn btn-sm btn-ghost">
            ← Details
          </Link>

          {/* TRIP ADVICE BUTTON (AI Co-Pilot) */}
          <button
            onClick={openAI}
            className={`btn btn-sm ${aiPanelOpen ? 'btn-accent' : 'btn-ghost'}`}
            id="ai-btn"
            title="Open AI Trip Advice & Route Weather Analysis"
          >
            ⚡ Trip Advice
          </button>

          {/* FUEL STOPS BUTTON */}
          <button
            onClick={toggleFuel}
            className={`btn btn-sm ${fuelLoaded ? 'btn-amber loaded' : 'btn-amber'}`}
            id="fuel-btn"
            title="Calculate fuel stop & petrol pumps along route"
          >
            ⛽ Fuel
          </button>

          {viewOnly ? (
            <button
              onClick={handleStartTripFromPreview}
              disabled={startingSession}
              className="btn btn-sm btn-jade"
            >
              {startingSession ? 'Launching…' : '▶ Start Trip'}
            </button>
          ) : (
            <>
              <button
                onClick={toggleTracking}
                className={`btn btn-sm ${tracking ? 'btn-ghost' : 'btn-jade'}`}
              >
                {tracking ? '⏸ Pause GPS' : '📡 Start Live GPS'}
              </button>
              {session?.status === 'active' && (
                <button onClick={handleEndTrip} className="btn btn-sm btn-danger">
                  ⏹ End
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* ── MAP CANVAS (Full screen dark CARTO basemap) ── */}
      <div className="map-container-wrap">
        <MapContainer
          center={defaultCenter}
          zoom={10}
          style={{ height: '100%', width: '100%', background: '#111214' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            url={`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png${CARTO_KEY_PARAM}`}
            subdomains="abcd"
            maxZoom={20}
          />

          <MapController
            startCoords={startCoords}
            endCoords={endCoords}
            panTarget={panTarget}
          />

          {/* OSRM Route Polyline */}
          {routeCoords && routeCoords.length > 0 && (
            <Polyline
              positions={routeCoords}
              pathOptions={{
                color: '#e8631a',
                weight: 4,
                opacity: 0.9,
                lineCap: 'round',
                lineJoin: 'round',
              }}
            />
          )}

          {/* Start Point Marker */}
          {startCoords && (
            <Marker position={startCoords} icon={startIcon}>
              <Popup>
                <strong>Start Point</strong><br />
                {startName}
              </Popup>
            </Marker>
          )}

          {/* Destination Point Marker */}
          {endCoords && (
            <Marker position={endCoords} icon={endIcon}>
              <Popup>
                <strong>Destination</strong><br />
                {destName}
              </Popup>
            </Marker>
          )}

          {/* Live Rider Marker (if GPS position available) */}
          {currentCoords && (
            <Marker position={currentCoords} icon={riderIcon}>
              <Popup>
                <strong>{bikename}</strong><br />
                Live Telemetry Position
              </Popup>
            </Marker>
          )}

          {/* 🌤️ WEATHER MARKERS DISPLAYED DIRECTLY ON MAP 🌤️ */}
          {weatherMarkers.map((m) => (
            <Marker
              key={m.id}
              position={[m.lat, m.lng]}
              icon={createWxIcon(m.city, m.emoji, m.temp, m.wind)}
              interactive={true}
            >
              <Popup>
                <div style={{ textAlign: 'center' }}>
                  <strong style={{ color: 'var(--accent)' }}>{m.city} Weather</strong><br />
                  <span style={{ fontSize: '1.2rem' }}>{m.emoji}</span> {m.temp}°C<br />
                  <span style={{ color: 'var(--text-3)', fontSize: '11px' }}>Wind: 💨 {m.wind} km/h</span>
                </div>
              </Popup>
            </Marker>
          ))}

          {/* ⛽ FUEL STOP & STATION MARKERS ON MAP */}
          {fuelData?.refuel_point && (
            <Marker
              position={[fuelData.refuel_point.lat, fuelData.refuel_point.lng]}
              icon={refuelIcon}
            >
              <Popup>
                <strong style={{ color: 'var(--amber)' }}>⛽ Refuel Point</strong><br />
                At approx {fuelData.refuel_distance_km} km along route
              </Popup>
            </Marker>
          )}

          {fuelData?.stations?.map((s, idx) => (
            <Marker
              key={`st-${idx}`}
              position={[s.lat, s.lng]}
              icon={createStationIcon(s.name, s.distance_km)}
            >
              <Popup>
                <strong>{s.name}</strong><br />
                {s.brand}<br />
                <span style={{ color: 'var(--jade)' }}>{s.distance_km} km from refuel corridor</span>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>

      {/* ── STATUS TOAST ── */}
      {toastMsg && (
        <div className="toast" id="toast">
          {toastMsg}
        </div>
      )}

      {/* ── INSTRUMENT PANEL (HUD bar at bottom center) ── */}
      <div className="instrument">
        <div className="instrument-route">
          <div className="inst-endpoint">
            <div className="inst-label">From</div>
            <div className="inst-val" title={startName}>
              {startName || '—'}
            </div>
          </div>
          <div className="inst-line">
            <span className="inst-arrow">▶</span>
          </div>
          <div className="inst-endpoint" style={{ textAlign: 'right' }}>
            <div className="inst-label">To</div>
            <div className="inst-val" title={destName}>
              {destName || '—'}
            </div>
          </div>
        </div>

        {viewOnly ? (
          <div className="instrument-stats">
            <div className="inst-stat">
              <div className="inst-stat-val accent">{routeDistKm || '—'}</div>
              <div className="inst-stat-lbl">Route Dist (km)</div>
            </div>
            <div className="inst-stat">
              <div className="inst-stat-val amber">{routeDurMins || '—'}</div>
              <div className="inst-stat-lbl">Est Duration (mins)</div>
            </div>
            <div className="inst-stat">
              <div className="inst-stat-val jade">
                {weatherLoading ? '…' : `${weatherMarkers.length} pts`}
              </div>
              <div className="inst-stat-lbl">Live Weather</div>
            </div>
          </div>
        ) : (
          <div className="instrument-stats">
            <div className="inst-stat">
              <div className="inst-stat-val jade" id="distTravelled">
                {distTravelled}
              </div>
              <div className="inst-stat-lbl">km covered</div>
            </div>
            <div className="inst-stat">
              <div className="inst-stat-val amber" id="distRemaining">
                {distRemaining}
              </div>
              <div className="inst-stat-lbl">km remaining</div>
            </div>
            <div className="inst-stat">
              <div className="inst-stat-val accent" id="accuracy">
                {accuracy !== null ? accuracy : '—'}
              </div>
              <div className="inst-stat-lbl">GPS accuracy (m)</div>
            </div>
          </div>
        )}
      </div>

      {/* ── AI TRIP ADVICE SIDE PANEL ── */}
      <div className={`side-panel ${aiPanelOpen ? 'open' : ''}`} id="ai-panel">
        <div className="panel-head">
          <span className="panel-title">⚡ Trip Advice // AI Co-Pilot</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={() => fetchAiAdvice(true)}
              className="btn btn-sm btn-ghost"
              style={{ fontSize: '0.66rem', padding: '2px 8px' }}
              title="Refresh AI Advice"
              disabled={aiLoading}
            >
              🔄 Refresh
            </button>
            <button className="panel-close" onClick={closeAI}>
              ✕
            </button>
          </div>
        </div>
        <div className="panel-body">
          {aiLoading ? (
            <div className="ai-loader">
              <div className="ai-spinner"></div>
              Analyzing route corridor, weather telemetry, and motorcycle specs…
            </div>
          ) : aiHtml ? (
            <div
              className="ai-content"
              dangerouslySetInnerHTML={{ __html: aiHtml }}
            />
          ) : (
            <div style={{ color: 'var(--text-3)', fontSize: '0.8rem' }}>
              Click Refresh to compute AI touring advice.
            </div>
          )}
        </div>
      </div>

      {/* ── FUEL STOPS SIDE PANEL ── */}
      <div className={`side-panel ${fuelPanelOpen ? 'open' : ''}`} id="fuel-panel">
        <div className="panel-head">
          <span className="panel-title">⛽ Fuel Stops</span>
          <button className="panel-close" onClick={closeFuel}>
            ✕
          </button>
        </div>
        <div className="panel-body" id="fuel-panel-body">
          {fuelLoading ? (
            <div className="ai-loader">
              <div className="ai-spinner" style={{ borderTopColor: 'var(--amber)' }}></div>
              Locating refuel point & verified petrol pumps…
            </div>
          ) : fuelData ? (
            <div>
              {fuelData.needed === false ? (
                <div className="fp-no-refuel">
                  ✓ No refueling needed — {fuelData.reason || 'Trip is within single tank range'}
                </div>
              ) : (
                <>
                  <div className="fp-row">
                    <span className="fp-key">Route distance</span>
                    <span className="fp-val">{fuelData.total_distance_km} km</span>
                  </div>
                  <div className="fp-row">
                    <span className="fp-key">Tank range</span>
                    <span className="fp-val">{fuelData.max_range_km} km</span>
                  </div>
                  <div className="fp-row">
                    <span className="fp-key">Refuel at</span>
                    <span className="fp-val amber">{fuelData.refuel_distance_km} km</span>
                  </div>

                  {fuelData.stations?.length > 0 ? (
                    <>
                      <div
                        style={{
                          fontFamily: "'JetBrains Mono', monospace",
                          fontSize: '0.58rem',
                          color: 'var(--text-3)',
                          letterSpacing: '0.1em',
                          textTransform: 'uppercase',
                          margin: '14px 0 6px',
                        }}
                      >
                        {fuelData.stations.length} STATIONS DISCOVERED
                      </div>
                      {fuelData.stations.map((s, idx) => (
                        <div
                          className="fp-station"
                          key={`s-card-${idx}`}
                          onClick={() => setPanTarget([s.lat, s.lng])}
                          style={{ cursor: 'pointer' }}
                        >
                          <div>
                            <div className="fp-station-name">{s.name}</div>
                            <div className="fp-station-brand">{s.brand}</div>
                          </div>
                          <span className="fp-dist">{s.distance_km} km</span>
                        </div>
                      ))}
                    </>
                  ) : (
                    <div style={{ color: 'var(--amber)', fontSize: '0.78rem', marginTop: '12px' }}>
                      No pumps located within 2 km of calculated refuel point.
                    </div>
                  )}
                </>
              )}
            </div>
          ) : (
            <div style={{ color: 'var(--text-3)', fontSize: '0.8rem' }}>
              Calculating refueling stations along path…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default LiveTracking;
