import React from 'react';

export default function Header({ onOpenJsonModal, isLive = false, cdseStatus = 'UNKNOWN' }) {
  return (
    <header className="app-header">
      <div className="brand-wrapper">
        <div className="brand-radar">
          <div className="radar-core-dot"></div>
        </div>
        <div className="brand-title-group">
          <span className="brand-name">Rakhshak</span>
          <span className="brand-subtitle">Rapid Disaster Change Intelligence & Copernicus Sentinel-1 Platform</span>
        </div>
      </div>

      <div className="header-status">
        <div
          className="status-badge"
          id="system-status-indicator"
          style={{
            borderColor: isLive ? 'rgba(74, 222, 128, 0.3)' : 'rgba(234, 179, 8, 0.3)',
            background: isLive ? 'rgba(74, 222, 128, 0.08)' : 'rgba(234, 179, 8, 0.08)',
          }}
        >
          <span
            className="status-dot"
            style={{ background: isLive ? '#4ade80' : '#eab308' }}
          ></span>
          <span style={{ color: isLive ? '#4ade80' : '#facc15' }}>
            {isLive ? `LIVE API (${cdseStatus === 'healthy' ? 'CDSE READY' : 'ONLINE'})` : 'OFFLINE BASELINE'}
          </span>
        </div>
        <button
          id="btn-view-json"
          className="btn-secondary"
          onClick={onOpenJsonModal}
          title="Inspect Unified Incident Report JSON"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="16 18 22 12 16 6"></polyline>
            <polyline points="8 6 2 12 8 18"></polyline>
          </svg>
          <span>Unified JSON</span>
        </button>
      </div>
    </header>
  );
}
