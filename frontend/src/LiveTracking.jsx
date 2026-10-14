import { useEffect, useState, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import api from './api';

// Fix for default Leaflet marker icons in Vite/React
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});
L.Marker.prototype.options.icon = DefaultIcon;

// Custom live rider icon (pulsing circle / bike pin)
const riderIcon = L.divIcon({
  className: 'live-rider-pin',
  html: `<div style="
    background: #007bff;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 3px solid white;
    box-shadow: 0 0 10px rgba(0,123,255,0.8);
  "></div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

// Component to smoothly re-center map when coordinates change
function RecenterMap({ coords }) {
  const map = useMap();
  useEffect(() => {
    if (coords && coords[0] && coords[1]) {
      map.setView(coords, map.getZoom());
    }
  }, [coords, map]);
  return null;
}

function LiveTracking() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [session, setSession] = useState(null);
  const [currentCoords, setCurrentCoords] = useState(null);
  const [tracking, setTracking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const watchIdRef = useRef(null);

  // 1. Fetch initial session data from DRF
  useEffect(() => {
    api.get(`/sessions/${sessionId}/`)
      .then((res) => {
        setSession(res.data);
        if (res.data.current_lat && res.data.current_lng) {
          setCurrentCoords([res.data.current_lat, res.data.current_lng]);
        } else if (res.data.start_coords) {
          setCurrentCoords([res.data.start_coords.lat, res.data.start_coords.lng]);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError('Failed to load tracking session.');
        setLoading(false);
      });
  }, [sessionId]);

  // 2. Start / Stop live browser GPS watch
  const toggleTracking = () => {
    if (tracking) {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
      setTracking(false);
    } else {
      if (!navigator.geolocation) {
        alert('Geolocation is not supported by your browser.');
        return;
      }

      setTracking(true);
      watchIdRef.current = navigator.geolocation.watchPosition(
        (position) => {
          const lat = position.coords.latitude;
          const lng = position.coords.longitude;
          setCurrentCoords([lat, lng]);

          // Send live coordinates to Django PostGIS PointField
          api.patch(`/sessions/${sessionId}/`, { lat, lng })
            .then((res) => {
              setSession((prev) => ({ ...prev, ...res.data }));
            })
            .catch((err) => console.error('GPS sync error:', err));
        },
        (err) => {
          console.warn('Geolocation error:', err.message);
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 2000 }
      );
    }
  };

  // Clean up watch on unmount
  useEffect(() => {
    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, []);

  // 3. End trip session
  const handleEndTrip = () => {
    if (!window.confirm('Mark this trip as completed?')) return;
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current);
    }

    api.post(`/sessions/${sessionId}/end_session/`)
      .then((res) => {
        alert('Trip marked as completed!');
        navigate(`/trips/${res.data.bike_trip}`);
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to end session.');
      });
  };

  if (loading) return <div style={{ padding: '30px' }}>Loading live tracking map...</div>;
  if (error) return <div style={{ padding: '30px', color: 'red' }}>{error}</div>;
  if (!session) return null;

  const defaultCenter = currentCoords || [12.9716, 77.5946];

  return (
    <div style={{ maxWidth: '850px', margin: '20px auto', fontFamily: 'system-ui, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <Link to={`/trips/${session.bike_trip}`} style={{ color: '#007bff', textDecoration: 'none', fontWeight: 'bold' }}>
          ← Back to Trip
        </Link>
        <div>
          <span style={{
            background: session.status === 'active' ? '#28a745' : '#6c757d',
            color: 'white',
            padding: '4px 10px',
            borderRadius: '12px',
            fontSize: '0.85em',
            fontWeight: 'bold',
            textTransform: 'uppercase'
          }}>
            {session.status}
          </span>
        </div>
      </div>

      <h2 style={{ margin: '0 0 6px 0' }}>🗺️ Live Ride: {session.bikename}</h2>
      <p style={{ margin: '0 0 16px 0', color: '#555' }}>
        {session.starting_name} ➔ {session.destination_name}
      </p>

      {/* TRACKING CONTROLS */}
      <div style={{
        background: '#f8f9fa',
        padding: '12px 18px',
        borderRadius: '8px',
        border: '1px solid #ddd',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '16px'
      }}>
        <div>
          <strong>Live GPS Status: </strong>
          <span style={{ color: tracking ? '#28a745' : '#666', fontWeight: 'bold' }}>
            {tracking ? '🟢 Broadcasting GPS Pings to Django' : '⚪ Paused'}
          </span>
          {currentCoords && (
            <div style={{ fontSize: '0.85em', color: '#666', marginTop: '4px' }}>
              Lat: {currentCoords[0].toFixed(5)}, Lng: {currentCoords[1].toFixed(5)}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          {session.status === 'active' && (
            <button
              onClick={toggleTracking}
              style={{
                background: tracking ? '#ffc107' : '#007bff',
                color: tracking ? '#212529' : 'white',
                border: 'none',
                padding: '8px 14px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              {tracking ? '⏸️ Pause GPS' : '📡 Start Live GPS'}
            </button>
          )}

          {session.status === 'active' && (
            <button
              onClick={handleEndTrip}
              style={{
                background: '#dc3545',
                color: 'white',
                border: 'none',
                padding: '8px 14px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              🏁 End Trip
            </button>
          )}
        </div>
      </div>

      {/* LEAFLET MAP CONTAINER */}
      <div style={{ height: '480px', borderRadius: '10px', overflow: 'hidden', border: '1px solid #ccc' }}>
        <MapContainer center={defaultCenter} zoom={13} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <RecenterMap coords={currentCoords} />

          {/* Route path polyline */}
          {session.route_coords && session.route_coords.length > 0 && (
            <Polyline positions={session.route_coords} color="#007bff" weight={5} opacity={0.7} />
          )}

          {/* Start Point Marker */}
          {session.start_coords && (
            <Marker position={[session.start_coords.lat, session.start_coords.lng]}>
              <Popup><strong>Start:</strong> {session.starting_name}</Popup>
            </Marker>
          )}

          {/* Destination Point Marker */}
          {session.dest_coords && (
            <Marker position={[session.dest_coords.lat, session.dest_coords.lng]}>
              <Popup><strong>Destination:</strong> {session.destination_name}</Popup>
            </Marker>
          )}

          {/* Current Live Rider Position */}
          {currentCoords && (
            <Marker position={currentCoords} icon={riderIcon}>
              <Popup>
                <strong>Current Position:</strong><br />
                {session.bikename}
              </Popup>
            </Marker>
          )}
        </MapContainer>
      </div>
    </div>
  );
}

export default LiveTracking;
