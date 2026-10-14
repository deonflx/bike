import { useEffect, useState } from 'react';
import { Routes, Route, Link, useNavigate } from 'react-router-dom';
import './App.css';
import api from './api';
import TripDetail from './TripDetail';
import LiveTracking from './LiveTracking';

// ─── 1. Home / Expedition Logbook View (matching customer_list.html) ──────────
function TripList() {
  const navigate = useNavigate();
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState('all');

  // Slide-over modal state
  const [isPanelOpen, setIsPanelOpen] = useState(false);
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
        setIsPanelOpen(false);
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to register expedition.');
        setSubmitting(false);
      });
  };

  const handleDelete = (e, tripId) => {
    e.stopPropagation();
    if (!window.confirm('Delete this expedition?')) return;

    api.delete(`/trips/${tripId}/`)
      .then(() => {
        setTrips(trips.filter((t) => t.id !== tripId));
      })
      .catch((err) => {
        console.error(err);
        alert('Failed to delete trip.');
      });
  };

  const filteredTrips = trips.filter((t) => {
    const term = searchTerm.toLowerCase();
    const matchesSearch =
      (t.bikename && t.bikename.toLowerCase().includes(term)) ||
      (t.starting_name && t.starting_name.toLowerCase().includes(term)) ||
      (t.destination_name && t.destination_name.toLowerCase().includes(term));
    return matchesSearch;
  });

  return (
    <div>
      {/* ── TOPBAR (matching customer_list.html) ── */}
      <nav className="topbar">
        <Link to="/" className="brand">
          <div className="brand-mark">⚡</div>
          <span className="brand-name">MOTOTRACK</span>
        </Link>
        <div className="topbar-divider"></div>
        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          <span className="nav-item active">Logbook</span>
          <span className="nav-item" style={{ color: 'var(--text-3)', cursor: 'default' }}>Radar</span>
          <span className="nav-item" style={{ color: 'var(--text-3)', cursor: 'default' }}>Invitations</span>
        </div>
        <div className="topbar-right">
          <button
            className="btn btn-sm btn-primary"
            onClick={() => setIsPanelOpen(true)}
          >
            + New Expedition
          </button>
        </div>
      </nav>

      {/* ── MAIN 2-COLUMN LAYOUT (matching customer_list.html) ── */}
      <div className="layout">
        {/* SIDEBAR */}
        <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-label">Expeditions</div>
            <a
              href="#all"
              className={`sidebar-link ${activeTab === 'all' ? 'active' : ''}`}
              onClick={(e) => { e.preventDefault(); setActiveTab('all'); }}
            >
              <span className="sidebar-icon">🏍️</span> All Expeditions
            </a>
            <a
              href="#my"
              className={`sidebar-link ${activeTab === 'my' ? 'active' : ''}`}
              onClick={(e) => { e.preventDefault(); setActiveTab('my'); }}
            >
              <span className="sidebar-icon">📁</span> My Logbook
            </a>
            <a
              href="#group"
              className={`sidebar-link ${activeTab === 'group' ? 'active' : ''}`}
              onClick={(e) => { e.preventDefault(); setActiveTab('group'); }}
            >
              <span className="sidebar-icon">👥</span> Group Convoys
            </a>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-label">Telemetry Engine</div>
            <div style={{ padding: '0 8px', fontSize: '0.72rem', color: 'var(--text-3)', lineHeight: 1.6 }}>
              <div>• PostGIS Spatial Points</div>
              <div>• Redis Specs Caching</div>
              <div>• Open-Meteo & Gemini AI</div>
            </div>
          </div>
        </aside>

        {/* CONTENT */}
        <main className="content">
          {/* STATS STRIP */}
          <div className="stats-strip">
            <div className="stat-cell">
              <div className="stat-number accent">{trips.length}</div>
              <div className="stat-label">Total Expeditions</div>
            </div>
            <div className="stat-cell">
              <div className="stat-number jade">ACTIVE</div>
              <div className="stat-label">PostGIS Spatial Store</div>
            </div>
            <div className="stat-cell">
              <div className="stat-number" style={{ color: 'var(--sand)' }}>REDIS 7D</div>
              <div className="stat-label">Specs Cache Engine</div>
            </div>
          </div>

          {/* TOOLBAR */}
          <div className="toolbar">
            <div className="tab-row">
              <span className="tab-btn active">Active Logs ({filteredTrips.length})</span>
            </div>

            <div className="search-wrap ml-auto">
              <span className="search-icon">🔍</span>
              <input
                type="text"
                placeholder="Search bike, city, destination…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
          </div>

          {/* TABLE SECTION (matching customer_list.html .data-table) */}
          <div className="table-section">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Machine / Operator</th>
                  <th>Route Corridor</th>
                  <th>Specs & Range</th>
                  <th>Date</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-3)' }}>
                      Connecting to telemetry database…
                    </td>
                  </tr>
                )}

                {!loading && filteredTrips.length === 0 && (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '50px 20px' }}>
                      <div className="empty-icon">🏍️</div>
                      <div className="empty-title">No expeditions found</div>
                      <div className="empty-sub">Register your first motorcycle trip to initiate spatial tracking.</div>
                      <button className="btn btn-sm btn-primary" onClick={() => setIsPanelOpen(true)}>
                        + New Expedition
                      </button>
                    </td>
                  </tr>
                )}

                {!loading && filteredTrips.map((trip) => {
                  const cap = trip.specs?.capacity || 15;
                  const mil = trip.specs?.mileage || 35;
                  const range = (cap * mil).toFixed(0);

                  return (
                    <tr
                      key={trip.id}
                      onClick={() => navigate(`/trips/${trip.id}`)}
                    >
                      <td>
                        <span className="trip-id">#{trip.id}</span>
                      </td>
                      <td>
                        <div className="bike-name">
                          {trip.bikename}
                          <span className="spec-tag" style={{ color: 'var(--amber)' }}>{cap}L</span>
                        </div>
                        <div className="rider-tag">@{trip.owner_username || 'anonymous'}</div>
                      </td>
                      <td>
                        <div className="route-cell">
                          <span className="route-from">{trip.starting_name}</span>
                          <span className="route-arrow">➔</span>
                          <span className="route-to">{trip.destination_name}</span>
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <span className="spec-tag">{mil} km/l</span>
                          <span className="spec-tag" style={{ color: 'var(--jade)' }}>~{range} km</span>
                        </div>
                      </td>
                      <td>
                        <span className="date-tag">
                          {new Date(trip.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '8px' }}>
                          <Link
                            to={`/trips/${trip.id}`}
                            className="action-link"
                            onClick={(e) => e.stopPropagation()}
                          >
                            View →
                          </Link>
                          <button
                            className="btn btn-sm btn-danger"
                            style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                            onClick={(e) => handleDelete(e, trip.id)}
                          >
                            ✕
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </main>
      </div>

      {/* ── SLIDE-OVER PANEL FOR NEW TRIP (matching bike_form.html) ── */}
      <div className={`overlay ${isPanelOpen ? 'open' : ''}`} onClick={() => setIsPanelOpen(false)}></div>
      <aside className={`trip-panel ${isPanelOpen ? 'open' : ''}`}>
        <div className="panel-head">
          <div>
            <div className="panel-title">New Expedition</div>
            <div className="panel-sub">Enter motorcycle specifications & coordinates</div>
          </div>
          <button className="close-btn" onClick={() => setIsPanelOpen(false)}>✕</button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
          <div className="panel-body">
            <div className="field-section">
              <div className="field-section-label">// MACHINE IDENTIFICATION</div>
              <div className="field">
                <label>Motorcycle Model</label>
                <input
                  type="text"
                  placeholder="e.g. Royal Enfield Himalayan, KTM 390"
                  value={bikename}
                  onChange={(e) => setBikename(e.target.value)}
                  required
                />
                <div className="field-hint">Gemini AI will automatically fetch tank capacity & mileage for this model.</div>
              </div>
            </div>

            <div className="field-section">
              <div className="field-section-label">// ROUTE CORRIDOR</div>
              <div className="field">
                <label>Starting Point</label>
                <input
                  type="text"
                  placeholder="e.g. Bangalore, Indiranagar"
                  value={startingName}
                  onChange={(e) => setStartingName(e.target.value)}
                  required
                />
              </div>

              <div className="field">
                <label>Destination</label>
                <input
                  type="text"
                  placeholder="e.g. Mysore, Ooty, Goa"
                  value={destinationName}
                  onChange={(e) => setDestinationName(e.target.value)}
                  required
                />
                <div className="field-hint">Locations will be geocoded into PostGIS spatial Points automatically.</div>
              </div>
            </div>
          </div>

          <div className="panel-footer">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setIsPanelOpen(false)}>
              Cancel
            </button>
            <button type="submit" disabled={submitting} className="btn btn-sm btn-primary">
              {submitting ? 'Registering Expedition…' : 'Register Expedition'}
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
}

// ─── 2. Main App Router ──────────────────────────────────────────────────────
function App() {
  return (
    <Routes>
      <Route path="/" element={<TripList />} />
      <Route path="/trips/:id" element={<TripDetail />} />
      <Route path="/trips/:id/route" element={<LiveTracking viewOnly={true} />} />
      <Route path="/tracking/:sessionId" element={<LiveTracking viewOnly={false} />} />
    </Routes>
  );
}

export default App;
