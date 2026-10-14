import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from './api';

function TripDetail() {
  const { id } = useParams();
  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Fetch single trip details from Django REST API: /api/trips/<id>/
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
  }, [id]);

  if (loading) return <div style={{ padding: '30px' }}>Loading trip details...</div>;
  if (error) return <div style={{ padding: '30px', color: 'red' }}>{error}</div>;
  if (!trip) return null;

  return (
    <div style={{ maxWidth: '650px', margin: '30px auto', fontFamily: 'system-ui, sans-serif' }}>
      <Link to="/" style={{ color: '#007bff', textDecoration: 'none', fontWeight: 'bold' }}>
        ← Back to All Trips
      </Link>

      <h1 style={{ marginTop: '16px' }}>🏍️ {trip.bikename}</h1>

      {/* ROUTE INFO */}
      <div style={{ background: '#f8f9fa', padding: '18px', borderRadius: '8px', border: '1px solid #e9ecef', marginBottom: '20px' }}>
        <h3>📍 Route Information</h3>
        <p><strong>Starting Point:</strong> {trip.starting_name}</p>
        {trip.starting_coords && (
          <p style={{ color: '#666', fontSize: '0.9em', marginLeft: '16px' }}>
            GPS: Lat {trip.starting_coords.lat}, Lng {trip.starting_coords.lng}
          </p>
        )}

        <p><strong>Destination:</strong> {trip.destination_name}</p>
        {trip.destination_coords && (
          <p style={{ color: '#666', fontSize: '0.9em', marginLeft: '16px' }}>
            GPS: Lat {trip.destination_coords.lat}, Lng {trip.destination_coords.lng}
          </p>
        )}
      </div>

      {/* REDIS BIKE SPECS */}
      <div style={{ background: '#eef9f1', padding: '18px', borderRadius: '8px', border: '1px solid #ccebd4' }}>
        <h3 style={{ color: '#1b5e20', marginTop: 0 }}>⚡ Bike Specs (from Redis)</h3>
        {trip.specs && Object.keys(trip.specs).length > 0 ? (
          <div>
            <p><strong>Fuel Tank Capacity:</strong> {trip.specs.fueltank_capacity || 'N/A'} Litres</p>
            <p><strong>Average Mileage:</strong> {trip.specs.average_mileage || 'N/A'} km/l</p>
          </div>
        ) : (
          <p style={{ color: '#666' }}>No specs cached in Redis for this trip yet.</p>
        )}
      </div>
    </div>
  );
}

export default TripDetail;