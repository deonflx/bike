import { useEffect, useState } from 'react';
import { Routes, Route, Link, useNavigate } from 'react-router-dom';
import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
  useAuth,
  useUser,
} from '@clerk/clerk-react';
import './App.css';
import api, { setAuthTokenGetter } from './api';
import TripDetail from './TripDetail';
import LiveTracking from './LiveTracking';
import Invitations from './Invitations';

function ClerkAuthBridge() {
  const { getToken } = useAuth();
  useEffect(() => {
    setAuthTokenGetter(getToken);
  }, [getToken]);
  return null;
}

function AuthenticatedHeader({ onNewExpedition }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <SignedOut>
        <SignInButton mode="modal">
          <button className="btn btn-sm btn-ghost" style={{ cursor: 'pointer' }}>
            Sign In
          </button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className="btn btn-sm btn-primary" style={{ cursor: 'pointer' }}>
            Sign Up
          </button>
        </SignUpButton>
      </SignedOut>
      <SignedIn>
        <button className="btn btn-sm btn-primary" onClick={onNewExpedition}>
          + New Expedition
        </button>
        <UserButton />
      </SignedIn>
    </div>
  );
}

// ─── 1. Home / Expedition Logbook View (matching customer_list.html) ──────────
function TripList({ isClerkConfigured }) {
  const navigate = useNavigate();
  const { user } = useUser();
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState('all');

  // Slide-over modal state
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [bikename, setBikename] = useState('');
  const [startingName, setStartingName] = useState('');
  const [destinationName, setDestinationName] = useState('');
  const [whatsappLink, setWhatsappLink] = useState('');
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
    if (submitting) return;
    setSubmitting(true);

    api.post('/trips/', {
      bikename: bikename.trim(),
      starting_name: startingName.trim(),
      destination_name: destinationName.trim(),
      whatsapp_group_link: whatsappLink.trim(),
    })
      .then((res) => {
        setTrips((prev) => [res.data, ...prev]);
        setBikename('');
        setStartingName('');
        setDestinationName('');
        setWhatsappLink('');
        setSubmitting(false);
        setIsPanelOpen(false);
      })
      .catch((err) => {
        console.error(err);
        let errorMsg = 'Failed to register expedition.';
        if (err.response?.data) {
          if (typeof err.response.data === 'string') {
            errorMsg = err.response.data;
          } else if (err.response.data.detail) {
            errorMsg = err.response.data.detail;
          } else if (Array.isArray(err.response.data)) {
            errorMsg = err.response.data[0];
          } else if (typeof err.response.data === 'object') {
            const firstKey = Object.keys(err.response.data)[0];
            const val = err.response.data[firstKey];
            errorMsg = Array.isArray(val) ? val[0] : String(val);
          }
        }
        alert(errorMsg);
        setSubmitting(false);
      });
  };

  const canDeleteTrip = (trip) => {
    if (trip.is_owner) return true;
    if (!user) return false;
    return Boolean(
      trip.owner_username &&
      (trip.owner_username === user.id || trip.owner_username === user.username)
    );
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
        const errMsg = err.response?.data?.detail || err.response?.data?.error || 'Failed to delete trip. You may only delete your own expeditions.';
        alert(errMsg);
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
          <Link to="/invitations" className="nav-item" style={{ textDecoration: 'none' }}>
            🤝 Invitations
          </Link>
        </div>
        <div className="topbar-right">
          {isClerkConfigured ? (
            <AuthenticatedHeader onNewExpedition={() => setIsPanelOpen(true)} />
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <button
                className="btn btn-sm btn-primary"
                onClick={() => setIsPanelOpen(true)}
              >
                + New Expedition
              </button>
            </div>
          )}
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
                          {canDeleteTrip(trip) && (
                            <button
                              className="btn btn-sm btn-danger"
                              style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                              onClick={(e) => handleDelete(e, trip.id)}
                              title="Delete your expedition"
                            >
                              ✕
                            </button>
                          )}
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

            <div className="field-section">
              <div className="field-section-label">// CONVOY COMMUNICATION (OPTIONAL)</div>
              <div className="field">
                <label>WhatsApp Group Invite Link</label>
                <input
                  type="url"
                  placeholder="e.g. https://chat.whatsapp.com/L123abcXYZ"
                  value={whatsappLink}
                  onChange={(e) => setWhatsappLink(e.target.value)}
                />
                <div className="field-hint">Companions who join your convoy can tap this link to join your group chat & voice intercom.</div>
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
function App({ isClerkConfigured }) {
  return (
    <>
      {isClerkConfigured && <ClerkAuthBridge />}
      <Routes>
        <Route path="/" element={<TripList isClerkConfigured={isClerkConfigured} />} />
        <Route path="/invitations" element={<Invitations isClerkConfigured={isClerkConfigured} />} />
        <Route path="/trips/:id" element={<TripDetail />} />
        <Route path="/trips/:id/route" element={<LiveTracking viewOnly={true} />} />
        <Route path="/tracking/:sessionId" element={<LiveTracking viewOnly={false} />} />
      </Routes>
    </>
  );
}

export default App;
