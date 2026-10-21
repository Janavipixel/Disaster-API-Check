import React from 'react';

export default function USGSPane({ incident }) {
  const usgs = incident?.usgs;

  if (!usgs || usgs.status === 'not_applicable' || !usgs.queried) {
    return (
      <div style={{ color: 'var(--text-tertiary)', fontSize: '0.86rem', padding: '16px 0', lineHeight: 1.6 }}>
        <p style={{ marginBottom: '8px' }}>
          <b>USGS Seismic Catalog:</b> Not applicable for non-seismic hazard types (e.g., floods or storms).
        </p>
        <span style={{ fontSize: '0.78rem' }}>
          {usgs?.error_message || 'The USGS Earthquake Catalog is automatically invoked for seismic, fault-slip, and tsunami alerts.'}
        </span>
      </div>
    );
  }

  const events = usgs.matched_events || [];

  if (events.length === 0) {
    return (
      <div style={{ color: 'var(--text-tertiary)', fontSize: '0.86rem', padding: '16px 0' }}>
        No seismic events matched within this spatial and temporal query window.
      </div>
    );
  }

  return (
    <div className="telemetry-stack">
      {events.map((evt, idx) => (
        <div key={idx} className="verification-entry">
          <div className="verification-entry-header">
            <span className="verification-topic" style={{ color: '#4ade80' }}>
              M {evt.magnitude?.toFixed(1) || 'N/A'} &mdash; {evt.place}
            </span>
            <span className="verification-status-pill status-corroborated">
              {evt.alert_level ? `${evt.alert_level.toUpperCase()} ALERT` : 'CONFIRMED'}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '8px', margin: '10px 0', fontSize: '0.78rem' }}>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Focal Depth:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{evt.depth_km} km</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Shake Intensity:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>MMI {evt.mmi || 'N/A'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Time (UTC):</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{evt.time_utc || 'N/A'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Tsunami Flag:</span>{' '}
              <b style={{ color: evt.tsunami ? '#ef4444' : 'var(--text-secondary)' }}>
                {evt.tsunami ? 'WARNING' : 'None'}
              </b>
            </div>
          </div>

          {evt.url && (
            <div style={{ fontSize: '0.76rem', marginTop: '6px' }}>
              <a
                href={evt.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#60a5fa', textDecoration: 'none' }}
              >
                View Official USGS Event Page &rarr;
              </a>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
