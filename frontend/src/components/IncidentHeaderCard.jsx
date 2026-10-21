import React from 'react';

export default function IncidentHeaderCard({ incident, onRecenter }) {
  if (!incident) return null;

  const isRed = incident.severity_level === 'Red';
  const hazardType = (incident.disaster_type || 'Unknown').replace(/^\w/, (c) => c.toUpperCase());
  const windowStr = `${incident.query_window_start || '--'} to ${incident.query_window_end || '--'}`;
  const scoreStr = incident.severity_score != null ? `${incident.severity_score.toFixed(1)} / 3.0` : 'N/A';

  const coords = incident.primary_coordinates;
  const latStr = coords?.latitude != null ? coords.latitude.toFixed(4) : '--';
  const lonStr = coords?.longitude != null ? coords.longitude.toFixed(4) : '--';
  const depthStr = coords?.depth_km ? ` (Depth: ${coords.depth_km} km)` : '';

  return (
    <article className="surface-card" id="incident-header-card">
      <div className="incident-header-top">
        <h1 className="incident-title">{incident.original_query}</h1>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span
            style={{
              fontSize: '0.68rem',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '12px',
              border: incident.is_live ? '1px solid rgba(74, 222, 128, 0.4)' : '1px solid rgba(234, 179, 8, 0.3)',
              background: incident.is_live ? 'rgba(74, 222, 128, 0.1)' : 'rgba(234, 179, 8, 0.1)',
              color: incident.is_live ? '#4ade80' : '#facc15',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            {incident.is_live ? '● Live API' : '○ Baseline Fallback'}
          </span>
          <span className={`severity-pill ${isRed ? 'pill-red' : 'pill-orange'}`}>
            {isRed ? 'Red Alert' : 'Orange Alert'}
          </span>
        </div>
      </div>

      <p className="incident-description">
        {incident.tavily?.synthesized_summary || 'Incident data parsed and cross-correlated across global feeds.'}
      </p>

      <div className="meta-stats-grid">
        <div className="meta-stat-box">
          <div className="meta-stat-label">Hazard</div>
          <div className="meta-stat-value">{hazardType}</div>
        </div>
        <div className="meta-stat-box">
          <div className="meta-stat-label">Event Window</div>
          <div className="meta-stat-value">{windowStr}</div>
        </div>
        <div className="meta-stat-box">
          <div className="meta-stat-label">GLIDE ID</div>
          <div className="meta-stat-value">{incident.glide || 'Pending GLIDE'}</div>
        </div>
        <div className="meta-stat-box">
          <div className="meta-stat-label">Severity Score</div>
          <div className="meta-stat-value">{scoreStr}</div>
        </div>
      </div>

      <div className="coords-panel">
        <div>
          <div className="coords-label">{coords?.coordinate_label || 'Primary Centroid'}</div>
          <div className="coords-value">
            Lat {latStr}, Lon {lonStr}
            {depthStr}
          </div>
          <div className="coords-source">Source: {coords?.source || 'Global Sensor Feed'}</div>
        </div>
        <button
          type="button"
          id="btn-recenter-map"
          className="btn-secondary"
          onClick={onRecenter}
          style={{ height: '32px', fontSize: '0.78rem' }}
          title="Zoom tightly into incident perimeter"
        >
          <span>Recenter Map</span>
        </button>
      </div>
    </article>
  );
}
