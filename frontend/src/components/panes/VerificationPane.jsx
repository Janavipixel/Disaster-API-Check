import React from 'react';

export default function VerificationPane({ incident }) {
  const claims = incident?.tavily?.verified_claims || [];

  if (claims.length === 0) {
    return (
      <div style={{ color: 'var(--text-tertiary)', fontSize: '0.86rem', padding: '16px 0' }}>
        No cross-verified intelligence claims recorded for this query window.
      </div>
    );
  }

  const getStatusBadge = (status) => {
    switch (status) {
      case 'corroborated':
        return <span className="verification-status-pill status-corroborated">Corroborated</span>;
      case 'single_source':
        return <span className="verification-status-pill status-single_source">Single Source</span>;
      case 'conflicting':
        return <span className="verification-status-pill status-conflicting">Conflicting</span>;
      default:
        return <span className="verification-status-pill status-single_source">{status}</span>;
    }
  };

  return (
    <div className="verification-list">
      {claims.map((claim, idx) => (
        <div key={idx} className="verification-entry">
          <div className="verification-entry-header">
            <span className="verification-topic">{claim.topic || claim.claim_topic}</span>
            {getStatusBadge(claim.verification_status)}
          </div>
          <div className="verification-text">{claim.statement || claim.claim_text}</div>
          <div className="verification-sources">
            <b style={{ color: 'var(--text-secondary)' }}>Sources:</b>{' '}
            {claim.corroborating_sources?.length > 0
              ? claim.corroborating_sources.join(', ')
              : claim.source || 'Aggregated telemetry dispatches'}
          </div>
          {claim.context_note && (
            <div style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)', marginTop: '4px' }}>
              {claim.context_note}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
