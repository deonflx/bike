import { useEffect, useState } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import api from './api';
import TripDetail from './TripDetail';
import LiveTracking from './LiveTracking';

// ─── 1. Home / Trip List View ────────────────────────────────────────────────
function TripList() {
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);

  // Form input states
  const [bikename, setBikename] = useState('');
  const [startingName, setStartingName] = useState('');
  const [destinationName, setDestinationName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchTrips();
  }, []);

  const fetchTrips = () => {
    api.get('/trips/')
      .then((res) => {
        setTrips(res.data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setSubmitting(true);

    api.post('/trips/', {
      bikename: bikename,
      starting_name: startingName,
      destination_name: destinationName,
    })
      .then((res) => {
        setTrips([res.data, ...trips]);
        setBikename('');
        setStartingName('');
        setDestinationName('');
        setSubmitting(false);
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to save trip. Check Django console for details.');
        setSubmitting(false);
      });
  };

  const handleDelete = (tripId) => {
    if (!window.confirm('Are you sure you want to delete this trip?')) return;

    api.delete(`/trips/${tripId}/`)
      .then(() => {
        setTrips(trips.filter((t) => t.id !== tripId));
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to delete trip.');
      });
  };

  return (
    <div style={{ maxWidth: '680px', margin: '30px auto', fontFamily: 'system-ui, sans-serif' }}>
      <h1>🏍️ Bike Trips</h1>

      {/* CREATE TRIP FORM */}
      <form
        onSubmit={handleSubmit}
        style={{
          background: '#f8f9fa',
          padding: '20px',
          borderRadius: '8px',
          border: '1px solid #e9ecef',
          marginBottom: '30px',
        }}
      >
        <h3 style={{ marginTop: 0 }}>Add a New Trip</h3>

        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Bike Name:</label>
          <input
            type="text"
            placeholder="e.g. Royal Enfield Himalayan"
            value={bikename}
            onChange={(e) => setBikename(e.target.value)}
            required
            style={{ width: '100%', padding: '8px', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Starting Point:</label>
          <input
            type="text"
            placeholder="e.g. Bangalore"
            value={startingName}
            onChange={(e) => setStartingName(e.target.value)}
            required
            style={{ width: '100%', padding: '8px', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Destination:</label>
          <input
            type="text"
            placeholder="e.g. Mysore"
            value={destinationName}
            onChange={(e) => setDestinationName(e.target.value)}
            required
            style={{ width: '100%', padding: '8px', boxSizing: 'border-box' }}
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          style={{
            background: '#007bff',
            color: '#fff',
            border: 'none',
            padding: '10px 18px',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 'bold',
          }}
        >
          {submitting ? 'Saving...' : 'Create Trip'}
        </button>
      </form>

      {/* TRIP LIST */}
      <h2>Saved Trips</h2>
      {loading && <p>Loading trips...</p>}

      {!loading && trips.length === 0 && (
        <p>No trips found in database.</p>
      )}

      <div style={{ display: 'grid', gap: '12px' }}>
        {trips.map((trip) => (
          <div
            key={trip.id}
            style={{
              padding: '16px',
              border: '1px solid #ddd',
              borderRadius: '8px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              boxShadow: '0 2px 4px rgba(0,0,0,0.03)'
            }}
          >
            <div>
              <Link
                to={`/trips/${trip.id}`}
                style={{ textDecoration: 'none', color: '#007bff' }}
              >
                <h3 style={{ margin: '0 0 6px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {trip.bikename} <span style={{ fontSize: '0.8em' }}>➔</span>
                </h3>
              </Link>
              <p style={{ margin: '0 0 6px 0', color: '#555' }}>
                📍 {trip.starting_name} ➔ {trip.destination_name}
              </p>
              {trip.specs && (
                <div style={{ fontSize: '0.85em', color: '#2e7d32', fontWeight: 'bold' }}>
                  ⚡ {trip.specs.capacity || 15}L Tank • {trip.specs.mileage || 35} km/l
                </div>
              )}
            </div>

            {/* ACTIONS */}
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <Link
                to={`/trips/${trip.id}`}
                style={{
                  background: '#f8f9fa',
                  border: '1px solid #ccc',
                  padding: '6px 12px',
                  borderRadius: '4px',
                  textDecoration: 'none',
                  color: '#333',
                  fontSize: '0.85em',
                  fontWeight: 'bold'
                }}
              >
                View
              </Link>

              <button
                onClick={() => handleDelete(trip.id)}
                style={{
                  background: '#dc3545',
                  color: 'white',
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                  fontSize: '0.85em'
                }}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── 2. Main App Router ──────────────────────────────────────────────────────
function App() {
  return (
    <Routes>
      <Route path="/" element={<TripList />} />
      <Route path="/trips/:id" element={<TripDetail />} />
      <Route path="/tracking/:sessionId" element={<LiveTracking />} />
    </Routes>
  );
}

export default App;