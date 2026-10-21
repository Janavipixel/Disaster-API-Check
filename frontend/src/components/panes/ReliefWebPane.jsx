import React from 'react';

export default function ReliefWebPane({ incident }) {
  const reliefweb = incident?.reliefweb;
  const reports = reliefweb?.matched_reports || [];

  if (!reliefweb || reports.length === 0) {
    return (
      <div style={{ color: 'var(--text-tertiary)', fontSize: '0.86rem', padding: '16px 0' }}>
        No UN OCHA ReliefWeb humanitarian situation reports registered for this query window.
      </div>
    );
  }

  return (
    <div className="telemetry-stack">
      {reports.map((rep, idx) => (
        <div key={idx} className="verification-entry">
          <div className="verification-entry-header">
            <span className="verification-topic" style={{ color: '#38bdf8' }}>
              {rep.title}
            </span>
            <span className="verification-status-pill status-corroborated">UN OCHA Sitrep</span>
          </div>

          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)', margin: '4px 0 8px' }}>
            <span>Source: <b style={{ color: 'var(--text-secondary)' }}>
              {rep.source || (Array.isArray(rep.sources) && rep.sources.length > 0 ? rep.sources.join(', ') : 'ReliefWeb Dispatches')}
            </b></span>
            <span style={{ margin: '0 6px' }}>&bull;</span>
            <span>Date: {rep.date || (rep.publication_date ? rep.publication_date.split('T')[0] : rep.published_date || '--')}</span>
          </div>

          {rep.body_snippet && (
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '8px' }}>
              {rep.body_snippet}
            </p>
          )}

          {rep.url && (
            <div style={{ fontSize: '0.76rem' }}>
              <a
                href={rep.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#60a5fa', textDecoration: 'none' }}
              >
                Read Full ReliefWeb Humanitarian Report &rarr;
              </a>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
