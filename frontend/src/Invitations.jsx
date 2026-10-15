import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { SignedIn, SignedOut, SignInButton, UserButton } from '@clerk/clerk-react';
import api from './api';
import './App.css';

function Invitations({ isClerkConfigured }) {
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('incoming'); // 'incoming' | 'accepted' | 'sent'
  const [toastMsg, setToastMsg] = useState(null);
  const [actionLoading, setActionLoading] = useState({});

  useEffect(() => {
    fetchConnections();
  }, []);

  const fetchConnections = () => {
    setLoading(true);
    api.get('/connections/')
      .then((res) => {
        setConnections(res.data || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load connection requests:', err);
        setLoading(false);
      });
  };

  const showToast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3500);
  };

  const handleRespond = (connId, action) => {
    setActionLoading((prev) => ({ ...prev, [connId]: true }));
    api.post(`/connections/${connId}/respond/`, { action })
      .then(() => {
        showToast(action === 'accept' ? '🎉 Connection accepted! Group ride active.' : 'Connection request declined.');
        fetchConnections();
      })
      .catch((err) => {
        console.error('Failed to respond to connection:', err);
        showToast('Failed to update request.');
      })
      .finally(() => {
        setActionLoading((prev) => ({ ...prev, [connId]: false }));
      });
  };

  const handleSetWhatsAppLink = (tripId, currentLink = '') => {
    const newLink = window.prompt(
      'Paste WhatsApp Group Invite Link (e.g. https://chat.whatsapp.com/...) so all convoy companions share this single group chat:',
      currentLink
    );
    if (newLink === null) return;
    api.post(`/trips/${tripId}/set_whatsapp_link/`, { whatsapp_group_link: newLink.trim() })
      .then(() => {
        showToast('✅ WhatsApp group link saved! All convoy companions now share this link.');
        fetchConnections();
      })
      .catch((err) => {
        console.error(err);
        showToast('Failed to update WhatsApp link.');
      });
  };

  // Group connections into categories
  // Note: incoming are requests where status === 'pending'
  const incoming = connections.filter((c) => c.status === 'pending');
  const accepted = connections.filter((c) => c.status === 'accepted');
  const sent = connections.filter((c) => c.status !== 'accepted' && c.status !== 'pending' || c.sender_username);

  return (
    <div className="invitations-page">
      {/* ── TOPBAR ── */}
      <nav className="topbar">
        <Link to="/" className="brand">
          <div className="brand-mark">⚡</div>
          <span className="brand-name">MOTOTRACK</span>
        </Link>
        <div className="topbar-divider"></div>
        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          <Link to="/" className="nav-item">Logbook</Link>
          <span className="nav-item active">Invitations</span>
        </div>
        <div className="topbar-right">
          {isClerkConfigured ? (
            <>
              <SignedIn>
                <UserButton />
              </SignedIn>
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="btn btn-sm btn-primary">Sign In</button>
                </SignInButton>
              </SignedOut>
            </>
          ) : (
            <Link to="/" className="btn btn-sm btn-ghost">← All Trips</Link>
          )}
        </div>
      </nav>

      {/* ── MAIN CONTENT ── */}
      <main className="container" style={{ maxWidth: '960px', margin: '36px auto', padding: '0 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '28px', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em', margin: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span>🤝</span> Ride Invitations & Group Convoys
            </h1>
            <p style={{ color: 'var(--text-2)', fontSize: '0.9rem', marginTop: '6px' }}>
              Connect with fellow riders on matching corridors and coordinate convoy journeys
            </p>
          </div>
          <Link to="/" className="btn btn-sm btn-ghost">
            ← Back to Logbook
          </Link>
        </div>

        {/* ── TAB BAR ── */}
        <div style={{ display: 'flex', gap: '10px', borderBottom: '1px solid var(--border)', paddingBottom: '12px', marginBottom: '24px' }}>
          <button
            onClick={() => setActiveTab('incoming')}
            className={`btn btn-sm ${activeTab === 'incoming' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '20px' }}
          >
            Incoming Requests
            {incoming.length > 0 && (
              <span style={{ marginLeft: '8px', background: 'var(--amber)', color: '#000', padding: '1px 7px', borderRadius: '10px', fontSize: '0.72rem', fontWeight: 700 }}>
                {incoming.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('accepted')}
            className={`btn btn-sm ${activeTab === 'accepted' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '20px' }}
          >
            Active Convoys
            {accepted.length > 0 && (
              <span style={{ marginLeft: '8px', background: 'var(--jade)', color: '#000', padding: '1px 7px', borderRadius: '10px', fontSize: '0.72rem', fontWeight: 700 }}>
                {accepted.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('sent')}
            className={`btn btn-sm ${activeTab === 'sent' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '20px' }}
          >
            All Invitations ({connections.length})
          </button>
        </div>

        {/* ── INCOMING REQUESTS ── */}
        {activeTab === 'incoming' && (
          <div>
            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)' }}>Loading invitations…</div>
            ) : incoming.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {incoming.map((req) => (
                  <div key={req.id} className="block" style={{ padding: '20px', borderRadius: '12px', border: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                          <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.85rem' }}>
                            {(req.sender_username || 'R')[0].toUpperCase()}
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>@{req.sender_username || 'anonymous'}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>Invited you to ride in convoy</div>
                          </div>
                        </div>

                        <div style={{ background: 'var(--asphalt-3)', padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--border)', display: 'inline-flex', alignItems: 'center', gap: '12px', marginTop: '6px' }}>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{req.starting_name || 'Start'}</span>
                          <span style={{ color: 'var(--accent)' }}>➔</span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{req.destination_name || 'Destination'}</span>
                          {req.bikename && (
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-2)', background: 'var(--asphalt-4)', padding: '2px 8px', borderRadius: '4px', border: '1px solid var(--border)' }}>
                              🏍️ {req.bikename}
                            </span>
                          )}
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', alignSelf: 'center' }}>
                        <button
                          disabled={actionLoading[req.id]}
                          onClick={() => handleRespond(req.id, 'accept')}
                          className="btn btn-sm"
                          style={{ background: 'var(--jade)', color: '#000', fontWeight: 600 }}
                        >
                          ✓ Accept & Join
                        </button>
                        <button
                          disabled={actionLoading[req.id]}
                          onClick={() => handleRespond(req.id, 'reject')}
                          className="btn btn-sm btn-ghost"
                          style={{ color: 'var(--signal)' }}
                        >
                          ✕ Decline
                        </button>
                        {req.bike_trip && (
                          <Link to={`/trips/${req.bike_trip}`} className="btn btn-sm btn-ghost">
                            View Trip
                          </Link>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '60px 20px', background: 'var(--asphalt-2)', borderRadius: '12px', border: '1px dashed var(--border)' }}>
                <div style={{ fontSize: '2rem', marginBottom: '12px' }}>📫</div>
                <div style={{ fontWeight: 600, fontSize: '1.05rem', marginBottom: '4px' }}>No pending invitations</div>
                <div style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>
                  When other riders on matching route corridors invite you, their requests will appear here.
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── ACCEPTED PARTNERS / CONVOYS ── */}
        {activeTab === 'accepted' && (
          <div>
            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)' }}>Loading convoys…</div>
            ) : accepted.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {accepted.map((conn) => (
                  <div key={conn.id} className="block" style={{ padding: '20px', borderRadius: '12px', border: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                          <span style={{ color: 'var(--jade)', fontSize: '0.9rem', fontWeight: 700 }}>✓ GROUP CONVOY ACTIVE</span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>• Confirmed Partner</span>
                        </div>
                        <div style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '8px' }}>
                          Riding with @{conn.sender_username || conn.receiver_username || 'partner'}
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-2)' }}>
                          Destination: <strong style={{ color: 'var(--text)' }}>{conn.destination_name}</strong>
                          {conn.starting_name ? ` (from ${conn.starting_name})` : ''}
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                        {conn.whatsapp_group_link ? (
                          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            <a
                              href={conn.whatsapp_group_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn btn-sm"
                              style={{
                                background: '#25D366',
                                color: '#0b0c0e',
                                fontWeight: 700,
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '5px',
                                textDecoration: 'none',
                              }}
                              title="Open WhatsApp Group Chat & Voice Intercom"
                            >
                              <span>💬</span> WhatsApp Group
                            </a>
                            <button
                              onClick={() => handleSetWhatsAppLink(conn.bike_trip, conn.whatsapp_group_link)}
                              className="btn btn-sm btn-ghost"
                              style={{ fontSize: '0.7rem', padding: '3px 6px', color: 'var(--text-2)' }}
                              title="Update WhatsApp link for all members"
                            >
                              ✏️
                            </button>
                          </div>
                        ) : conn.bike_trip ? (
                          <button
                            onClick={() => handleSetWhatsAppLink(conn.bike_trip, '')}
                            className="btn btn-sm btn-ghost"
                            style={{ color: '#25D366', borderColor: 'rgba(37,211,102,0.4)', fontSize: '0.78rem' }}
                            title="Add WhatsApp group link so all convoy members share the same chat"
                          >
                            💬 + Group Link
                          </button>
                        ) : null}
                        {conn.bike_trip && (
                          <>
                            <Link to={`/trips/${conn.bike_trip}`} className="btn btn-sm btn-primary">
                              Open Group Expedition →
                            </Link>
                            <Link to={`/trips/${conn.bike_trip}/route`} className="btn btn-sm btn-ghost">
                              View Route Map
                            </Link>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '60px 20px', background: 'var(--asphalt-2)', borderRadius: '12px', border: '1px dashed var(--border)' }}>
                <div style={{ fontSize: '2rem', marginBottom: '12px' }}>👥</div>
                <div style={{ fontWeight: 600, fontSize: '1.05rem', marginBottom: '4px' }}>No active convoys yet</div>
                <div style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>
                  Accept incoming requests or invite matching co-travelers from the expedition radar to form group rides.
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── ALL / SENT INVITATIONS ── */}
        {activeTab === 'sent' && (
          <div>
            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)' }}>Loading…</div>
            ) : connections.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {connections.map((req) => (
                  <div key={req.id} className="block" style={{ padding: '16px 20px', borderRadius: '10px', border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontWeight: 600 }}>@{req.sender_username} ➔ @{req.receiver_username || 'rider'}</span>
                        <span style={{
                          fontSize: '0.72rem',
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: '4px',
                          background: req.status === 'accepted' ? 'rgba(34,197,94,0.15)' : req.status === 'rejected' ? 'rgba(244,63,94,0.15)' : 'rgba(245,158,11,0.15)',
                          color: req.status === 'accepted' ? 'var(--jade)' : req.status === 'rejected' ? 'var(--signal)' : 'var(--amber)',
                          border: `1px solid ${req.status === 'accepted' ? 'rgba(34,197,94,0.3)' : req.status === 'rejected' ? 'rgba(244,63,94,0.3)' : 'rgba(245,158,11,0.3)'}`
                        }}>
                          {req.status.toUpperCase()}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-3)', marginTop: '4px' }}>
                        Route: {req.starting_name} ➔ {req.destination_name}
                      </div>
                    </div>

                    {req.bike_trip && (
                      <Link to={`/trips/${req.bike_trip}`} className="btn btn-sm btn-ghost">
                        View Trip
                      </Link>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '60px 20px', background: 'var(--asphalt-2)', borderRadius: '12px', border: '1px dashed var(--border)' }}>
                <div style={{ fontSize: '2rem', marginBottom: '12px' }}>⚡</div>
                <div style={{ fontWeight: 600, fontSize: '1.05rem', marginBottom: '4px' }}>No invitations recorded</div>
                <div style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>
                  Explore expeditions in your logbook to find and invite co-travelers.
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── TOAST NOTIFICATION ── */}
        {toastMsg && (
          <div style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            background: 'var(--asphalt-2)',
            border: '1px solid var(--border-hi)',
            borderRadius: '8px',
            padding: '12px 20px',
            fontSize: '0.88rem',
            color: 'var(--text)',
            boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
            zIndex: 1000,
          }}>
            {toastMsg}
          </div>
        )}
      </main>
    </div>
  );
}

export default Invitations;
