import React from 'react';

export default function GDACSPane({ incident }) {
  const gdacs = incident?.gdacs;
  const events = gdacs?.matched_events || [];

  if (!gdacs || events.length === 0) {
    return (
      <div style={{ color: 'var(--text-tertiary)', fontSize: '0.86rem', padding: '16px 0' }}>
        No matching GDACS multi-hazard disaster alerts found for this query.
      </div>
    );
  }

  return (
    <div className="telemetry-stack">
      {events.map((evt, idx) => (
        <div key={idx} className="verification-entry">
          <div className="verification-entry-header">
            <span className="verification-topic" style={{ color: '#fbbf24' }}>
              {evt.name || 'GDACS Emergency Alert'}
            </span>
            <span className={`verification-status-pill ${evt.alert_level === 'Red' ? 'status-conflicting' : 'status-single_source'}`}>
              Score: {evt.alert_score != null ? evt.alert_score.toFixed(1) : 'N/A'} ({evt.alert_level || 'Alert'})
            </span>
          </div>

          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: '6px 0 10px', lineHeight: 1.5 }}>
            {evt.severity_text || 'Multi-hazard alert broadcast by United Nations & European Commission JRC.'}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '8px', fontSize: '0.78rem' }}>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Event ID:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{evt.event_id || '--'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Episode ID:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{evt.episode_id || '--'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Duration:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{evt.duration || '--'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Population Impact:</span>{' '}
              <b style={{ color: '#fdba74' }}>{evt.affected_population || 'N/A'}</b>
            </div>
          </div>

          {evt.report_url && (
            <div style={{ fontSize: '0.76rem', marginTop: '10px' }}>
              <a
                href={evt.report_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#60a5fa', textDecoration: 'none' }}
              >
                Access Official GDACS Situation Report &rarr;
              </a>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
