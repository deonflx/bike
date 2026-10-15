import { useEffect, useState, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';
import DOMPurify from 'dompurify';
import './App.css';
import api from './api';

function TripDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useUser();

  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // AI Co-Pilot Summary state
  const [aiSummary, setAiSummary] = useState(null);
  const [loadingAi, setLoadingAi] = useState(true);
  const [aiError, setAiError] = useState(null);

  // Fuel Stops state
  const [fuelData, setFuelData] = useState(null);
  const [loadingFuel, setLoadingFuel] = useState(false);
  const [fuelLoaded, setFuelLoaded] = useState(false);

  // Co-Travelers state
  const [coTravelers, setCoTravelers] = useState([]);
  const [activeTab, setActiveTab] = useState('all');

  // Session state
  const [startingSession, setStartingSession] = useState(false);
  const [invitedRiders, setInvitedRiders] = useState({});

  const fetchAiSummary = useCallback((forceRefresh = false, isIgnored = () => false) => {
    setLoadingAi(true);
    setAiError(null);
    const url = forceRefresh ? `/trips/${id}/generate_summary/?refresh=true` : `/trips/${id}/generate_summary/`;

    api.post(url)
      .then((res) => {
        if (!isIgnored()) {
          setAiSummary(res.data.html);
          setLoadingAi(false);
        }
      })
      .catch((err) => {
        if (!isIgnored()) {
          console.error('AI summary error:', err);
          setAiError('Failed to load AI summary.');
          setLoadingAi(false);
        }
      });
  }, [id]);

  useEffect(() => {
    let ignored = false;

    // Reset state for previous trip
    setTrip(null);
    setFuelData(null);
    setFuelLoaded(false);
    setInvitedRiders({});
    setCoTravelers([]);
    setAiSummary(null);
    setAiError(null);
    setError(null);
    setLoading(true);

    // 1. Fetch trip details
    api.get(`/trips/${id}/`)
      .then((res) => {
        if (!ignored) {
          setTrip(res.data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignored) {
          console.error(err);
          setError('Failed to load trip details.');
          setLoading(false);
        }
      });

    // 2. Auto-load AI summary
    fetchAiSummary(false, () => ignored);

    // 3. Check if pre-calculated fuel stops exist in Redis (don't auto-load)
    api.get(`/trips/${id}/fuel_stops/`)
      .then((res) => {
        if (!ignored && res.data && res.data.needed !== undefined) {
          setFuelData(res.data);
          setFuelLoaded(true);
        }
      })
      .catch((err) => console.log('Fuel stops check:', err));

    // 4. Fetch matching co-travelers
    api.get(`/trips/${id}/co_travelers/`)
      .then((res) => {
        if (!ignored) {
          setCoTravelers(res.data || []);
        }
      })
      .catch((err) => console.error('Co-travelers error:', err));

    return () => {
      ignored = true;
    };
  }, [id, fetchAiSummary]);

  const fetchFuelStops = () => {
    setLoadingFuel(true);
    api.get(`/trips/${id}/fuel_stops/`)
      .then((res) => {
        setFuelData(res.data);
        setFuelLoaded(true);
        setLoadingFuel(false);
      })
      .catch((err) => {
        console.error('Fuel stops error:', err);
        setLoadingFuel(false);
      });
  };

  const isOwner = Boolean(
    trip?.is_owner ||
    (user && trip?.owner_username && (trip.owner_username === user.id || trip.owner_username === user.username))
  );

  const handleStartTrip = () => {
    if (!isOwner) {
      alert('Only the creator of this expedition can start a live tracking session.');
      return;
    }
    setStartingSession(true);
    api.post(`/trips/${id}/start_session/`)
      .then((res) => {
        navigate(`/tracking/${res.data.id}`);
      })
      .catch((err) => {
        console.error(err);
        const errMsg = err.response?.data?.error || err.response?.data?.detail || 'Could not start live session.';
        alert(errMsg);
        setStartingSession(false);
      });
  };

  const handleDelete = () => {
    if (!isOwner) {
      alert('You can only delete your own expeditions.');
      return;
    }
    if (!window.confirm(`Delete expedition for ${trip.bikename}?`)) return;
    api.delete(`/trips/${id}/`)
      .then(() => {
        navigate('/');
      })
      .catch((err) => {
        console.error(err);
        const errMsg = err.response?.data?.detail || err.response?.data?.error || 'Failed to delete trip. You may only delete your own expeditions.';
        alert(errMsg);
      });
  };

  const handleSetWhatsAppLink = () => {
    const currentLink = trip?.whatsapp_group_link || '';
    const newLink = window.prompt(
      'Paste WhatsApp Group Invite Link (must start with https://chat.whatsapp.com/):',
      currentLink
    );
    if (newLink === null) return;
    const trimmed = newLink.trim();
    if (trimmed && !trimmed.startsWith('https://chat.whatsapp.com/')) {
      alert('Invalid link! WhatsApp group link must begin with https://chat.whatsapp.com/');
      return;
    }
    api.post(`/trips/${id}/set_whatsapp_link/`, { whatsapp_group_link: trimmed })
      .then((res) => {
        setTrip((prev) => ({ ...prev, whatsapp_group_link: res.data.whatsapp_group_link }));
        alert('✅ WhatsApp group link saved!');
      })
      .catch((err) => {
        console.error(err);
        alert(err.response?.data?.error || 'Failed to update WhatsApp link.');
      });
  };

  const handleConnect = (rider) => {
    api.post('/connections/', {
      receiver: rider.user_id,
      bike_trip: parseInt(id),
    })
      .then(() => {
        setInvitedRiders((prev) => ({ ...prev, [rider.id]: 'pending' }));
        alert(`⚡ Ride invitation dispatched to @${rider.username || 'rider'}!`);
      })
      .catch((err) => {
        const errorMsg = err.response?.data?.error || 'Connection request already sent or error occurred.';
        alert(errorMsg);
      });
  };

  if (loading) return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh', color: 'var(--text-3)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <div className="ai-spinner"></div> Loading expedition telemetries…
      </div>
    </div>
  );

  if (error) return (
    <div style={{ padding: '40px', textAlign: 'center', color: 'var(--signal)' }}>{error}</div>
  );

  if (!trip) return null;

  const capacity = trip.specs?.capacity || 15;
  const mileage = trip.specs?.mileage || 35;
  const estimatedRange = (capacity * mileage).toFixed(0);

  const filteredTravelers = coTravelers.filter((rider) => {
    if (activeTab === 'route') return rider.shared_route_km > 0;
    if (activeTab === 'dest') return rider.dist_km === 0 || (rider.dist_km !== null && rider.dist_km <= 50);
    return true;
  });

  return (
    <div>
      {/* ── TOPBAR ── */}
      <nav className="topbar">
        <Link to="/" className="brand">
          <div className="brand-mark">⚡</div>
          <span className="brand-name">MOTOTRACK</span>
        </Link>
        <div className="topbar-divider"></div>
        <div className="breadcrumb">
          <Link to="/">Logbook</Link>
          <span className="breadcrumb-sep">/</span>
          <span style={{ color: 'var(--text)' }}>{trip.bikename}</span>
        </div>
        <div className="topbar-right">
          {isOwner && (
            <button className="btn btn-sm btn-danger" onClick={handleDelete} title="Delete your expedition">
              Delete
            </button>
          )}
        </div>
      </nav>

      {/* ── 2-COLUMN PAGE LAYOUT (matching customer_detail.html) ── */}
      <div className="page">
        {/* MAIN COLUMN */}
        <div className="col-main">
          {/* TRIP HEADER */}
          <div className="trip-header">
            <div className="trip-meta-row">
              <span className="trip-id-tag">EXPEDITION #{trip.id}</span>
              <span className="rider-tag">OPERATOR: @{trip.owner_username || 'anonymous'}</span>
            </div>
            <h1 className="trip-title">{trip.bikename}</h1>
            <div className="trip-date">
              Logged on {new Date(trip.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
            </div>
          </div>

          {/* ROUTE STRIP */}
          <div className="route-strip">
            <div className="route-node">
              <div className="route-node-label">From</div>
              <div className="route-node-val">{trip.starting_name}</div>
            </div>
            <div className="route-connector">
              <div className="connector-line">
                <span className="connector-arrow">▶</span>
              </div>
            </div>
            <div className="route-node" style={{ textAlign: 'right' }}>
              <div className="route-node-label">To</div>
              <div className="route-node-val">{trip.destination_name}</div>
            </div>
          </div>

          {/* ACTION BUTTONS (Exact HTML classes: btn-jade, btn-ghost) */}
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
            {isOwner && (
              <button
                onClick={handleStartTrip}
                disabled={startingSession}
                className="btn btn-sm btn-jade"
              >
                {startingSession ? 'Launching Radar…' : '▶ Start Trip'}
              </button>
            )}

            <Link
              to={`/trips/${id}/route`}
              className="btn btn-sm btn-ghost"
            >
              View Route
            </Link>

            {trip.whatsapp_group_link && trip.whatsapp_group_link.startsWith('https://chat.whatsapp.com/') ? (
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                <a
                  href={trip.whatsapp_group_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-sm"
                  style={{
                    background: '#25D366',
                    color: '#0b0c0e',
                    fontWeight: 700,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    textDecoration: 'none',
                  }}
                  title="Open WhatsApp Group Chat & Voice Intercom"
                >
                  <span>💬</span> Convoy WhatsApp
                </a>
                {isOwner && (
                  <button
                    onClick={handleSetWhatsAppLink}
                    className="btn btn-sm btn-ghost"
                    style={{ fontSize: '0.72rem', padding: '3px 6px', color: 'var(--text-2)' }}
                    title="Update WhatsApp Group Link for all members"
                  >
                    ✏️
                  </button>
                )}
              </div>
            ) : isOwner ? (
              <button
                onClick={handleSetWhatsAppLink}
                className="btn btn-sm btn-ghost"
                style={{ color: '#25D366', borderColor: 'rgba(37, 211, 102, 0.4)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                title="Add a WhatsApp group link so all convoy members share the same chat"
              >
                <span>💬</span> + WhatsApp Group
              </button>
            ) : null}

            <button
              onClick={() => {
                const text = encodeURIComponent(
                  `🏍️ Mototrack Expedition: ${trip.bikename}\n` +
                  `📍 Route: ${trip.starting_name} ➔ ${trip.destination_name}\n` +
                  `⚡ Join Convoy & Live Telemetry: ${window.location.origin}/trips/${trip.id}`
                );
                window.open(`https://wa.me/?text=${text}`, '_blank');
              }}
              className="btn btn-sm btn-ghost"
              style={{ color: '#25D366', borderColor: 'rgba(37, 211, 102, 0.4)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
              title="Share expedition to WhatsApp friends or groups"
            >
              <span>📲</span> Share WhatsApp
            </button>
          </div>

          {/* AI CO-PILOT BLOCK (Exact HTML structure: .block.ai-block) */}
          <div className="block ai-block">
            <div className="block-head">
              <span className="block-title" style={{ color: 'var(--accent)' }}>AI Co-Pilot</span>
              <button
                className="btn btn-sm btn-ghost"
                style={{ fontSize: '0.68rem', padding: '3px 9px' }}
                onClick={() => fetchAiSummary(true)}
                disabled={loadingAi}
              >
                {loadingAi ? 'Analyzing…' : '🔄 Refresh AI'}
              </button>
            </div>
            <div className="ai-body">
              {loadingAi ? (
                <div className="ai-loader">
                  <div className="ai-spinner"></div>
                  Analyzing route conditions, live weather, and engine specs…
                </div>
              ) : aiError ? (
                <span style={{ color: 'var(--signal)' }}>{aiError}</span>
              ) : (
                <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(aiSummary || '') }} />
              )}
            </div>
          </div>

          {/* EXPEDITION RADAR / CO-TRAVELERS BLOCK (Exact HTML classes: .radar-block) */}
          <div className="radar-block">
            <div className="radar-head">
              <div className="radar-title-group">
                <div className="radar-title-tag">
                  <span className="live-dot" style={{ display: 'inline-block', marginRight: '6px' }}></span>
                  Expedition Radar // Same Destination
                </div>
                <div className="radar-sub">
                  Riders travelling to <strong>{trip.destination_name}</strong> or sharing route corridors
                </div>
              </div>
            </div>

            {/* RADAR FILTER TABS */}
            <div style={{ display: 'flex', gap: '12px', padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
              <button
                className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
                onClick={() => setActiveTab('all')}
              >
                All Matches ({coTravelers.length})
              </button>
              <button
                className={`tab-btn ${activeTab === 'route' ? 'active' : ''}`}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
                onClick={() => setActiveTab('route')}
              >
                🛣️ Shared Routes ({coTravelers.filter(r => r.shared_route_km > 0).length})
              </button>
              <button
                className={`tab-btn ${activeTab === 'dest' ? 'active' : ''}`}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
                onClick={() => setActiveTab('dest')}
              >
                🎯 Same Destination
              </button>
            </div>

            {/* CONVOY CARDS LIST */}
            <div className="radar-cards-list">
              {filteredTravelers.length > 0 ? (
                filteredTravelers.map((rider) => (
                  <div key={rider.id} className="convoy-card">
                    <div className="convoy-top">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="rider-tag">@{rider.username || 'anonymous'}</span>
                        <span className="trip-id-tag">TRIP #{rider.id}</span>
                      </div>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        {rider.is_live && <span className="live-tag">LIVE ON ROAD</span>}
                        {rider.shared_route_km > 0 && (
                          <span className="spec-tag" style={{ color: 'var(--jade)', borderColor: 'rgba(34,197,94,0.3)' }}>
                            🛣️ {rider.shared_route_km} km Shared
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="convoy-bike-title">{rider.bikename}</div>
                    <div className="convoy-route">
                      {rider.starting_name} ➔ {rider.destination_name}
                    </div>

                    <div className="convoy-meta">
                      {rider.dist_km !== null ? `${rider.dist_km} km from destination` : 'Matching area'}
                      {rider.overlap_pct ? ` • ${rider.overlap_pct}% corridor overlap` : ''}
                    </div>

                    <div className="convoy-actions">
                      <Link to={`/trips/${rider.id}`} className="btn btn-sm btn-ghost" style={{ fontSize: '0.72rem', padding: '4px 10px' }}>
                        View Trip
                      </Link>
                      <button
                        disabled={Boolean(rider.conn_status || invitedRiders[rider.id])}
                        onClick={() => handleConnect(rider)}
                        className={`btn btn-sm ${rider.conn_status === 'accepted' ? 'btn-jade' : 'btn-accent'}`}
                        style={{ fontSize: '0.72rem', padding: '4px 10px', cursor: (rider.conn_status || invitedRiders[rider.id]) ? 'default' : 'pointer' }}
                      >
                        {rider.conn_status === 'accepted' ? '✓ Group Active' :
                         (rider.conn_status === 'pending' || invitedRiders[rider.id]) ? '⏳ Invite Sent' :
                         '⚡ Invite to Ride'}
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="radar-empty">
                  No matching riders currently on this corridor. You are leading the pack!
                </div>
              )}
            </div>
          </div>
        </div>

        {/* SIDE COLUMN */}
        <div className="col-side">
          {/* RANGE READOUT (Exact HTML class: .range-readout) */}
          <div className="block">
            <div className="block-head">
              <span className="block-title">Estimated Range</span>
            </div>
            <div className="block-body">
              <div className="range-readout">
                <div className="range-num">{estimatedRange}</div>
                <div className="range-unit">km on full tank</div>
              </div>
            </div>
          </div>

          {/* SPECS BLOCK (Exact HTML classes: .spec-row, .spec-key, .spec-val) */}
          <div className="block">
            <div className="block-head">
              <span className="block-title">Machine Specs</span>
            </div>
            <div className="block-body" style={{ padding: '0 17px' }}>
              <div className="spec-row">
                <span className="spec-key">Tank Capacity</span>
                <span className="spec-val accent">{capacity} L</span>
              </div>
              <div className="spec-row">
                <span className="spec-key">Avg Mileage</span>
                <span className="spec-val jade">{mileage} km/L</span>
              </div>
              <div className="spec-row">
                <span className="spec-key">Max Range</span>
                <span className="spec-val">{estimatedRange} km</span>
              </div>
              <div className="spec-row">
                <span className="spec-key">Database Store</span>
                <span className="spec-val" style={{ color: 'var(--amber)' }}>PostGIS + Redis</span>
              </div>
              <div className="spec-row">
                <span className="spec-key">Record ID</span>
                <span className="spec-val">#{trip.id}</span>
              </div>
            </div>
          </div>

          {/* FUEL STOPS (matching template: .fuel-block with btn-find-fuel) */}
          <div className="block fuel-block">
            <div className="block-head">
              <span className="block-title">Fuel Stops</span>
              <button
                className="btn-find-fuel"
                onClick={fetchFuelStops}
                disabled={loadingFuel}
              >
                {loadingFuel ? '…' : fuelLoaded ? 'Refresh' : 'Find'}
              </button>
            </div>
            <div className="block-body" style={{ padding: '12px 20px' }}>
              {!fuelLoaded && !loadingFuel && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-3)', lineHeight: 1.5 }}>
                  Find the optimal refueling point at 70% of your tank range, with nearby stations from Overpass API.
                </div>
              )}
              {loadingFuel && (
                <div style={{ fontSize: '0.78rem', color: 'var(--text-3)' }}>Locating fuel stops…</div>
              )}
              {fuelLoaded && fuelData && (
                fuelData.needed === false ? (
                  <div style={{ fontSize: '0.75rem', color: 'var(--jade)' }}>
                    ✓ No refuel stop needed — your range covers the full route.
                  </div>
                ) : (
                  <div>
                    <div className="fuel-stat-row">
                      <span className="fuel-stat-key">Refuel at</span>
                      <span className="fuel-stat-val amber">{fuelData.refuel_distance_km} km</span>
                    </div>
                    <div className="fuel-stat-row">
                      <span className="fuel-stat-key">Search Radius</span>
                      <span className="fuel-stat-val">{fuelData.search_radius_km} km</span>
                    </div>
                    {fuelData.stations && fuelData.stations.length > 0 && (
                      <div className="fuel-result">
                        <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: '8px' }}>
                          Overpass Petrol Stations:
                        </div>
                        {fuelData.stations.slice(0, 3).map((st, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                            <div>
                              <div style={{ fontSize: '0.78rem', fontWeight: 600 }}>{st.name || 'Petrol Pump'}</div>
                              <div style={{ fontSize: '0.68rem', color: 'var(--text-3)' }}>{st.brand || 'Fuel Station'}</div>
                            </div>
                            <span className="spec-tag" style={{ color: 'var(--jade)' }}>{st.distance_km} km</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default TripDetail;
