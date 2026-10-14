import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import api from './api';

function TripDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // AI Summary state
  const [aiSummary, setAiSummary] = useState(null);
  const [generatingAi, setGeneratingAi] = useState(false);

  // Fuel Stops (Redis) state
  const [fuelData, setFuelData] = useState(null);

  // Co-Travelers state
  const [coTravelers, setCoTravelers] = useState([]);
  const [loadingCoTravelers, setLoadingCoTravelers] = useState(true);

  // Session starting state
  const [startingSession, setStartingSession] = useState(false);

  useEffect(() => {
    // 1. Fetch trip details
    api.get(`/trips/${id}/`)
      .then((res) => {
        setTrip(res.data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError('Failed to load trip details.');
        setLoading(false);
      });

    // 2. Fetch pre-calculated fuel stops from Redis
    api.get(`/trips/${id}/fuel_stops/`)
      .then((res) => setFuelData(res.data))
      .catch((err) => console.log('No fuel data:', err));

    // 3. Fetch matching co-travelers
    api.get(`/trips/${id}/co_travelers/`)
      .then((res) => {
        setCoTravelers(res.data);
        setLoadingCoTravelers(false);
      })
      .catch((err) => {
        console.error('Co-travelers error:', err);
        setLoadingCoTravelers(false);
      });
  }, [id]);

  // Start Live Tracking Session
  const handleStartTrip = () => {
    setStartingSession(true);
    api.post(`/trips/${id}/start_session/`)
      .then((res) => {
        navigate(`/tracking/${res.data.id}`);
      })
      .catch((err) => {
        console.error(err);
        alert('Could not start live session.');
        setStartingSession(false);
      });
  };

  // Generate AI Summary with Gemini + Weather
  const handleGenerateSummary = () => {
    setGeneratingAi(true);
    api.post(`/trips/${id}/generate_summary/`)
      .then((res) => {
        setAiSummary(res.data.html);
        setGeneratingAi(false);
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to generate AI summary.');
        setGeneratingAi(false);
      });
  };

  // Send group connection request to another rider
  const handleConnect = (receiverId) => {
    api.post('/connections/', {
      receiver: receiverId,
      bike_trip: parseInt(id),
    })
      .then(() => {
        alert('Ride invitation sent!');
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to send connection request or already sent.');
      });
  };

  if (loading) return <div style={{ padding: '30px' }}>Loading trip details...</div>;
  if (error) return <div style={{ padding: '30px', color: 'red' }}>{error}</div>;
  if (!trip) return null;

  return (
    <div style={{ maxWidth: '750px', margin: '30px auto', fontFamily: 'system-ui, sans-serif' }}>
      <Link to="/" style={{ color: '#007bff', textDecoration: 'none', fontWeight: 'bold' }}>
        ← Back to All Trips
      </Link>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '14px' }}>
        <h1 style={{ margin: 0 }}>🏍️ {trip.bikename}</h1>
        <button
          onClick={handleStartTrip}
          disabled={startingSession}
          style={{
            background: '#28a745',
            color: 'white',
            border: 'none',
            padding: '10px 18px',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: '1rem'
          }}
        >
          {startingSession ? 'Launching...' : '🚀 Start Live Trip'}
        </button>
      </div>

      {/* ─── 1. ROUTE INFO ─────────────────────────────────────────── */}
      <div style={{ background: '#f8f9fa', padding: '18px', borderRadius: '8px', border: '1px solid #e9ecef', marginTop: '20px' }}>
        <h3 style={{ margin: '0 0 10px 0' }}>📍 Route</h3>
        <p style={{ margin: '4px 0' }}><strong>Starting Point:</strong> {trip.starting_name}</p>
        {trip.starting_coords && (
          <p style={{ color: '#666', fontSize: '0.85em', margin: '0 0 8px 16px' }}>
            GPS: {trip.starting_coords.lat.toFixed(4)}, {trip.starting_coords.lng.toFixed(4)}
          </p>
        )}

        <p style={{ margin: '4px 0' }}><strong>Destination:</strong> {trip.destination_name}</p>
        {trip.destination_coords && (
          <p style={{ color: '#666', fontSize: '0.85em', margin: '0 0 8px 16px' }}>
            GPS: {trip.destination_coords.lat.toFixed(4)}, {trip.destination_coords.lng.toFixed(4)}
          </p>
        )}
      </div>

      {/* ─── 2. REDIS BIKE SPECS & REFUEL ──────────────────────────── */}
      <div style={{ background: '#eef9f1', padding: '18px', borderRadius: '8px', border: '1px solid #ccebd4', marginTop: '16px' }}>
        <h3 style={{ color: '#1b5e20', margin: '0 0 10px 0' }}>⚡ Bike Specs & Fuel Stop (Redis)</h3>
        {trip.specs ? (
          <div>
            <p style={{ margin: '4px 0' }}><strong>Fuel Tank Capacity:</strong> {trip.specs.capacity || 15} L</p>
            <p style={{ margin: '4px 0' }}><strong>Average Mileage:</strong> {trip.specs.mileage || 35} km/l</p>
            <p style={{ margin: '4px 0' }}>
              <strong>Estimated Max Range:</strong> {((trip.specs.capacity || 15) * (trip.specs.mileage || 35)).toFixed(0)} km
            </p>

            {fuelData && fuelData.needed && (
              <div style={{ marginTop: '12px', padding: '10px', background: '#ffffff', borderRadius: '6px' }}>
                <h4 style={{ margin: '0 0 6px 0', color: '#e65100' }}>⛽ Suggested Refuel Stop</h4>
                <p style={{ margin: '2px 0', fontSize: '0.9em' }}>
                  Target Refuel Distance: <strong>{fuelData.refuel_distance_km} km</strong> (Search radius: {fuelData.search_radius_km} km)
                </p>
                {fuelData.stations && fuelData.stations.length > 0 ? (
                  <ul style={{ margin: '6px 0 0 0', paddingLeft: '20px', fontSize: '0.9em' }}>
                    {fuelData.stations.slice(0, 3).map((station, i) => (
                      <li key={i}>{station.name} ({station.brand}) — ~{station.distance_km} km off-route</li>
                    ))}
                  </ul>
                ) : (
                  <p style={{ fontSize: '0.85em', color: '#666', margin: '4px 0 0 0' }}>Scanning route for petrol pumps...</p>
                )}
              </div>
            )}
          </div>
        ) : (
          <p style={{ color: '#666', margin: 0 }}>No specs cached in Redis yet.</p>
        )}
      </div>

      {/* ─── 3. AI ADVISOR & WEATHER ───────────────────────────────── */}
      <div style={{ background: '#f3e5f5', padding: '18px', borderRadius: '8px', border: '1px solid #e1bee7', marginTop: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ color: '#4a148c', margin: 0 }}>✨ AI Touring Advisor & Weather</h3>
          <button
            onClick={handleGenerateSummary}
            disabled={generatingAi}
            style={{
              background: '#6a1b9a',
              color: 'white',
              border: 'none',
              padding: '6px 12px',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: 'bold',
            }}
          >
            {generatingAi ? 'Analyzing Route...' : 'Generate AI Summary'}
          </button>
        </div>

        {aiSummary ? (
          <div
            style={{ marginTop: '14px', background: 'white', padding: '14px', borderRadius: '6px', lineHeight: '1.6' }}
            dangerouslySetInnerHTML={{ __html: aiSummary }}
          />
        ) : (
          <p style={{ color: '#555', fontSize: '0.9em', marginTop: '10px', marginBottom: 0 }}>
            Click above to have Gemini AI analyze weather, compute estimated fuel cost at ₹113/L, and plan break schedules.
          </p>
        )}
      </div>

      {/* ─── 4. CO-TRAVELERS & GROUP RIDES ─────────────────────────── */}
      <div style={{ background: '#fff3e0', padding: '18px', borderRadius: '8px', border: '1px solid #ffe0b2', marginTop: '16px' }}>
        <h3 style={{ color: '#e65100', margin: '0 0 10px 0' }}>👥 Co-Travelers & Shared Routes</h3>

        {loadingCoTravelers && <p style={{ margin: 0, color: '#666' }}>Finding nearby riders...</p>}

        {!loadingCoTravelers && coTravelers.length === 0 && (
          <p style={{ margin: 0, color: '#666' }}>No other riders heading on this route right now.</p>
        )}

        <div style={{ display: 'grid', gap: '10px', marginTop: '10px' }}>
          {coTravelers.map((rider) => (
            <div
              key={rider.id}
              style={{
                background: 'white',
                padding: '12px',
                borderRadius: '6px',
                border: '1px solid #ffd180',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <div>
                <strong style={{ fontSize: '1rem' }}>{rider.bikename}</strong>
                <div style={{ fontSize: '0.85em', color: '#555', marginTop: '2px' }}>
                  To: {rider.destination_name} • {rider.dist_km !== null ? `${rider.dist_km} km away` : 'Matching area'}
                </div>
                {rider.shared_route_km > 0 && (
                  <div style={{ fontSize: '0.8em', color: '#2e7d32', fontWeight: 'bold' }}>
                    🛣️ {rider.shared_route_km} km shared route ({rider.overlap_pct}%)
                  </div>
                )}
                {rider.is_live && (
                  <span style={{ fontSize: '0.75em', background: '#28a745', color: 'white', padding: '2px 6px', borderRadius: '4px' }}>
                    🟢 LIVE RIDING NOW
                  </span>
                )}
              </div>

              <button
                onClick={() => handleConnect(rider.id)}
                style={{
                  background: '#ff9800',
                  color: 'white',
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                  fontSize: '0.85em'
                }}
              >
                Connect
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default TripDetail;
