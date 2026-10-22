import React from 'react';

export default function Header({
  activeTab = 'dashboard',
  onTabChange,
  onOpenJsonModal,
  onOpenColdStartModal,
  isLive = false,
  cdseStatus = 'UNKNOWN',
  isFetching = false,
}) {
  return (
    <header className="app-header">
      <div className="header-left">
        <div
          className="brand-wrapper"
          onClick={() => onTabChange && onTabChange('dashboard')}
          style={{ cursor: 'pointer' }}
          title="Back to Platform Dashboard"
        >
          <div className="brand-radar">
            <div className="radar-core-dot"></div>
          </div>
          <div className="brand-title-group">
            <span className="brand-name">Rakhshak</span>
            <span className="brand-subtitle" style={{ color: 'var(--text-secondary)' }}>Disaster Change Intelligence & Sentinel-1 Platform</span>
          </div>
        </div>

        {/* HOME BAR NAVIGATION TABS */}
        <nav className="header-nav-tabs" role="tablist" aria-label="Main Navigation">
          <button
            type="button"
            className={`header-tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => onTabChange && onTabChange('dashboard')}
            role="tab"
            aria-selected={activeTab === 'dashboard'}
            id="home-tab-dashboard"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon>
              <line x1="8" y1="2" x2="8" y2="18"></line>
              <line x1="16" y1="6" x2="16" y2="22"></line>
            </svg>
            <span>Disaster Intelligence</span>
          </button>

          <button
            type="button"
            className={`header-tab-btn ${activeTab === 'disaster_api' ? 'active' : ''}`}
            onClick={() => onTabChange && onTabChange('disaster_api')}
            role="tab"
            aria-selected={activeTab === 'disaster_api'}
            id="home-tab-disaster-api"
          >
            <div className="tab-api-icon-wrapper">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
              </svg>
              <span className={`tab-pulse-indicator ${isLive ? 'online' : 'offline'} ${isFetching ? 'fetching' : ''}`}></span>
            </div>
            <span>Disaster API Monitor</span>
            <span className="header-tab-pill-badge">
              {isFetching ? 'FETCHING' : (isLive ? 'LIVE FEED' : 'OFFLINE')}
            </span>
          </button>
        </nav>
      </div>

      <div className="header-status">
        <div
          className="status-badge"
          id="system-status-indicator"
          onClick={onOpenColdStartModal}
          style={{
            borderColor: isLive ? 'rgba(74, 222, 128, 0.3)' : 'rgba(234, 179, 8, 0.3)',
            background: isLive ? 'rgba(74, 222, 128, 0.08)' : 'rgba(234, 179, 8, 0.08)',
            cursor: 'pointer',
          }}
          title="Click to view Render Backend Deployment status & cold-start notice"
        >
          <span
            className="status-dot"
            style={{ background: isLive ? '#4ade80' : '#eab308' }}
          ></span>
          <span style={{ color: isLive ? '#4ade80' : '#facc15' }}>
            {isLive ? `API CONNECTED (${cdseStatus === 'healthy' ? 'CDSE READY' : 'ONLINE'})` : 'OFFLINE BASELINE (RENDER)'}
          </span>
        </div>
        <button
          id="btn-return-landing"
          type="button"
          className="btn-back-to-landing"
          onClick={() => {
            if (typeof window.returnToLanding === 'function') {
              window.returnToLanding();
            } else {
              window.location.hash = '';
              window.location.reload();
            }
          }}
          title="Return to Rakhshak Product Overview"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          <span>Product Overview</span>
        </button>
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
