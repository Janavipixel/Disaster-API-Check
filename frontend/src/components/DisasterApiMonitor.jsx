import React, { useState, useEffect } from 'react';
import {
  checkHealth,
  queryDisaster,
  searchCopernicusCatalog,
  listCopernicusRuns,
} from '../services/api.js';

export default function DisasterApiMonitor({ onSwitchToDashboard, onApplyIncidentToDashboard }) {
  // Subsystem health state
  const [healthData, setHealthData] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState(null);
  const [healthLatency, setHealthLatency] = useState(null);

  // Live Query test state
  const [testQuery, setTestQuery] = useState('Kerala floods August 2018');
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryResult, setQueryResult] = useState(null);
  const [queryError, setQueryError] = useState(null);
  const [queryLatency, setQueryLatency] = useState(null);
  const [activeResultTab, setActiveResultTab] = useState('overview');

  // Feed selection options
  const [feedOptions, setFeedOptions] = useState({
    enable_tavily: true,
    enable_usgs: true,
    enable_gdacs: true,
    enable_reliefweb: true,
    enable_firms: true,
    limit: 10,
  });

  // Copernicus CDSE Catalog test state
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogResult, setCatalogResult] = useState(null);
  const [catalogError, setCatalogError] = useState(null);

  // Copy JSON indicator
  const [copiedJson, setCopiedJson] = useState(false);

  // Fetch health on mount
  useEffect(() => {
    fetchSystemHealth();
  }, []);

  const fetchSystemHealth = async () => {
    setHealthLoading(true);
    setHealthError(null);
    const start = performance.now();
    try {
      const data = await checkHealth();
      const end = performance.now();
      setHealthLatency(Math.round(end - start));
      setHealthData(data);
      if (data.status === 'offline') {
        setHealthError('FastAPI backend server is currently offline or unreachable.');
      }
    } catch (err) {
      setHealthError(`Health check failed: ${err.message}`);
    } finally {
      setHealthLoading(false);
    }
  };

  const handleExecuteLiveQuery = async (customQueryText, customFeeds) => {
    const q = (customQueryText || testQuery || '').trim();
    if (!q) return;

    setIsQuerying(true);
    setQueryError(null);
    setQueryResult(null);
    const start = performance.now();

    const options = customFeeds || feedOptions;

    try {
      const res = await queryDisaster(q, options);
      const end = performance.now();
      setQueryLatency(Math.round(end - start));
      setQueryResult(res);
      setActiveResultTab('overview');
    } catch (err) {
      setQueryError(err.message || 'Error executing disaster API query.');
    } finally {
      setIsQuerying(false);
    }
  };

  const handleQuickSingleFeed = (feedKey) => {
    const singleOptions = {
      enable_tavily: feedKey === 'tavily',
      enable_usgs: feedKey === 'usgs',
      enable_gdacs: feedKey === 'gdacs',
      enable_reliefweb: feedKey === 'reliefweb',
      enable_firms: feedKey === 'firms',
      limit: 10,
    };
    setFeedOptions(singleOptions);
    let sampleQ = testQuery;
    if (feedKey === 'firms') sampleQ = 'California wildfire August 2020';
    if (feedKey === 'usgs') sampleQ = 'Japan earthquake January 2024';
    if (feedKey === 'reliefweb') sampleQ = 'Nepal Trishuli landslide August 2026';
    setTestQuery(sampleQ);
    handleExecuteLiveQuery(sampleQ, singleOptions);
  };

  const handleResetFeeds = () => {
    const all = {
      enable_tavily: true,
      enable_usgs: true,
      enable_gdacs: true,
      enable_reliefweb: true,
      enable_firms: true,
      limit: 10,
    };
    setFeedOptions(all);
    handleExecuteLiveQuery(testQuery, all);
  };

  const handleTestCdseCatalog = async () => {
    setCatalogLoading(true);
    setCatalogError(null);
    setCatalogResult(null);

    // Default to Kerala bbox or queryResult bbox
    const bbox = queryResult?.bbox || [76.2, 9.8, 76.6, 10.2];
    const eventDate = queryResult?.incident_date_str || '2018-08-10';

    try {
      const res = await searchCopernicusCatalog({
        bbox,
        event_date: eventDate.split('T')[0],
        pre_window_days: 15,
        post_window_days: 15,
      });
      setCatalogResult(res);
    } catch (err) {
      setCatalogError(err.message || 'CDSE STAC catalog search failed.');
    } finally {
      setCatalogLoading(false);
    }
  };

  const handleCopyJson = () => {
    if (!queryResult) return;
    navigator.clipboard.writeText(JSON.stringify(queryResult, null, 2));
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  const handleSendToDashboard = () => {
    if (queryResult && onApplyIncidentToDashboard) {
      onApplyIncidentToDashboard(queryResult);
    }
    if (onSwitchToDashboard) {
      onSwitchToDashboard();
    }
  };

  const isServerHealthy = healthData?.status === 'healthy';
  const subsystems = healthData?.subsystems || {};

  return (
    <div className="api-monitor-container">
      {/* SECTION 1: HEADER & TELEMETRY BANNER */}
      <div className="api-monitor-header-card">
        <div className="api-header-left">
          <div className="api-status-badge-large">
            <span className={`pulse-ring-dot ${isServerHealthy ? 'online' : 'offline'}`}></span>
            <div>
              <div className="api-title-main">Disaster API Diagnostics & Live Feed Monitor</div>
              <div className="api-subtitle-meta">
                Real-time validation of multi-source intelligence ingestion (Tavily, ReliefWeb, NASA FIRMS, USGS, GDACS, CDSE)
              </div>
            </div>
          </div>
        </div>

        <div className="api-header-actions">
          <div className="api-telemetry-pill">
            <span className="telemetry-label">Status:</span>
            <span className={`telemetry-value ${isServerHealthy ? 'text-green' : 'text-red'}`}>
              {isServerHealthy ? 'ONLINE // READY' : 'OFFLINE'}
            </span>
            {healthLatency !== null && (
              <span className="telemetry-latency">({healthLatency}ms)</span>
            )}
          </div>
          <button
            type="button"
            className="btn-refresh-health"
            onClick={fetchSystemHealth}
            disabled={healthLoading}
            title="Ping /api/health to re-verify all upstream credentials"
          >
            <svg
              className={`refresh-svg ${healthLoading ? 'spinning' : ''}`}
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <polyline points="23 4 23 10 17 10"></polyline>
              <polyline points="1 20 1 14 7 14"></polyline>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            <span>{healthLoading ? 'Pinging...' : 'Refresh Health'}</span>
          </button>
        </div>
      </div>

      {/* HEALTH ERROR NOTICE IF ANY */}
      {healthError && (
        <div className="api-error-alert">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <div>
            <strong>Backend Connection Warning:</strong> {healthError}
            <div className="error-tip">
              Ensure <code>run_server.py</code> is started on port 8000 and <code>.env</code> contains all required keys.
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: SUBSYSTEM & CREDENTIAL HEALTH MATRIX */}
      <div className="api-subsystems-grid">
        {/* Tavily */}
        <div className="subsystem-card">
          <div className="subsystem-card-top">
            <div className="subsystem-icon-box tavily-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth="2">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
            </div>
            <div className="subsystem-title-wrap">
              <div className="subsystem-name">Tavily Web Intelligence</div>
              <div className="subsystem-key-meta">TAVILY_API_KEY</div>
            </div>
            <span className={`status-pill ${subsystems.tavily_web_intelligence?.configured ? 'success' : 'warning'}`}>
              {subsystems.tavily_web_intelligence?.configured ? 'CONFIGURED' : 'UNCONFIGURED'}
            </span>
          </div>
          <div className="subsystem-details">
            <div className="detail-line">
              <span>Feed Type:</span>
              <strong className="text-slate">Live News & Claims Search</strong>
            </div>
            <div className="detail-line">
              <span>Status Msg:</span>
              <span className="text-secondary">{subsystems.tavily_web_intelligence?.message || 'Ready'}</span>
            </div>
          </div>
          <button
            type="button"
            className="btn-feed-test"
            onClick={() => handleQuickSingleFeed('tavily')}
            disabled={isQuerying}
          >
            ⚡ Test Tavily Feed
          </button>
        </div>

        {/* ReliefWeb */}
        <div className="subsystem-card">
          <div className="subsystem-card-top">
            <div className="subsystem-icon-box reliefweb-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
              </svg>
            </div>
            <div className="subsystem-title-wrap">
              <div className="subsystem-name">UN ReliefWeb Reports</div>
              <div className="subsystem-key-meta">RELIEFWEB_APPNAME</div>
            </div>
            <span className={`status-pill ${subsystems.reliefweb_humanitarian?.configured ? 'success' : 'warning'}`}>
              {subsystems.reliefweb_humanitarian?.configured ? 'ACTIVE (APP APPROVED)' : 'UNCONFIGURED'}
            </span>
          </div>
          <div className="subsystem-details">
            <div className="detail-line">
              <span>Global Archive:</span>
              <strong className="text-slate">{subsystems.reliefweb_humanitarian?.total_reports?.toLocaleString() || '1,147,000+'} SitReps</strong>
            </div>
            <div className="detail-line">
              <span>App Registration:</span>
              <span className="text-secondary">TerraByte-Disaster-tss8d</span>
            </div>
          </div>
          <button
            type="button"
            className="btn-feed-test"
            onClick={() => handleQuickSingleFeed('reliefweb')}
            disabled={isQuerying}
          >
            ⚡ Test ReliefWeb Feed
          </button>
        </div>

        {/* NASA FIRMS */}
        <div className="subsystem-card">
          <div className="subsystem-card-top">
            <div className="subsystem-icon-box firms-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f97316" strokeWidth="2">
                <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path>
              </svg>
            </div>
            <div className="subsystem-title-wrap">
              <div className="subsystem-name">NASA FIRMS Active Fire</div>
              <div className="subsystem-key-meta">FIRMS_MAP_KEY</div>
            </div>
            <span className={`status-pill ${subsystems.nasa_firms_active_fire?.configured ? 'success' : 'warning'}`}>
              {subsystems.nasa_firms_active_fire?.configured ? 'KEY CONFIGURED' : 'UNCONFIGURED'}
            </span>
          </div>
          <div className="subsystem-details">
            <div className="detail-line">
              <span>Sensors:</span>
              <strong className="text-slate">MODIS & VIIRS SNPP/NOAA</strong>
            </div>
            <div className="detail-line">
              <span>Mode:</span>
              <span className="text-secondary">Thermal Anomaly CSV Ingestion</span>
            </div>
          </div>
          <button
            type="button"
            className="btn-feed-test"
            onClick={() => handleQuickSingleFeed('firms')}
            disabled={isQuerying}
          >
            ⚡ Test NASA FIRMS Feed
          </button>
        </div>

        {/* GDACS */}
        <div className="subsystem-card">
          <div className="subsystem-card-top">
            <div className="subsystem-icon-box gdacs-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#eab308" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
            </div>
            <div className="subsystem-title-wrap">
              <div className="subsystem-name">GDACS Multi-Hazard Alerts</div>
              <div className="subsystem-key-meta">UN OCHA / EC JRC</div>
            </div>
            <span className="status-pill success">PUBLIC REST API</span>
          </div>
          <div className="subsystem-details">
            <div className="detail-line">
              <span>Hazards:</span>
              <strong className="text-slate">Floods, Cyclones, EQ, Fires</strong>
            </div>
            <div className="detail-line">
              <span>Protocol:</span>
              <span className="text-secondary">GeoJSON Alert Feeds (Zero Auth)</span>
            </div>
          </div>
          <button
            type="button"
            className="btn-feed-test"
            onClick={() => handleQuickSingleFeed('gdacs')}
            disabled={isQuerying}
          >
            ⚡ Test GDACS Feed
          </button>
        </div>

        {/* USGS */}
        <div className="subsystem-card">
          <div className="subsystem-card-top">
            <div className="subsystem-icon-box usgs-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
              </svg>
            </div>
            <div className="subsystem-title-wrap">
              <div className="subsystem-name">USGS Earthquake Catalog</div>
              <div className="subsystem-key-meta">USGS GeoJSON API</div>
            </div>
            <span className="status-pill success">PUBLIC DOMAIN</span>
          </div>
          <div className="subsystem-details">
            <div className="detail-line">
              <span>Coverage:</span>
              <strong className="text-slate">Global Seismic Ruptures</strong>
            </div>
            <div className="detail-line">
              <span>Metrics:</span>
              <span className="text-secondary">Epicenter, Magnitude, PAGER</span>
            </div>
          </div>
          <button
            type="button"
            className="btn-feed-test"
            onClick={() => handleQuickSingleFeed('usgs')}
            disabled={isQuerying}
          >
            ⚡ Test USGS Feed
          </button>
        </div>

        {/* Copernicus CDSE */}
        <div className="subsystem-card">
          <div className="subsystem-card-top">
            <div className="subsystem-icon-box copernicus-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path>
                <path d="M2 12h20"></path>
              </svg>
            </div>
            <div className="subsystem-title-wrap">
              <div className="subsystem-name">Copernicus CDSE Sentinel-1</div>
              <div className="subsystem-key-meta">CDSE_CLIENT_ID / SECRET</div>
            </div>
            <span className={`status-pill ${subsystems.copernicus_cdse?.token_valid ? 'success' : 'warning'}`}>
              {subsystems.copernicus_cdse?.token_valid ? 'TOKEN ACQUIRED' : 'UNAUTHENTICATED'}
            </span>
          </div>
          <div className="subsystem-details">
            <div className="detail-line">
              <span>Catalog Runs:</span>
              <strong className="text-slate">{healthData?.runs_catalog?.total_runs ?? 0} Pre-computed on disk</strong>
            </div>
            <div className="detail-line">
              <span>OAuth2 Token:</span>
              <span className="text-secondary">{subsystems.copernicus_cdse?.message || 'Valid'}</span>
            </div>
          </div>
          <button
            type="button"
            className="btn-feed-test"
            onClick={handleTestCdseCatalog}
            disabled={catalogLoading}
          >
            {catalogLoading ? 'Searching...' : '⚡ Test CDSE STAC Search'}
          </button>
        </div>
      </div>

      {/* SECTION 3: INTERACTIVE LIVE QUERY TESTBED */}
      <div className="api-testbed-card">
        <div className="testbed-header">
          <div className="testbed-title-wrap">
            <div className="testbed-title">Disaster API Live Query Execution & Verification</div>
            <div className="testbed-subtitle">
              Send a live natural-language query to <code>POST /api/disaster/query</code> and verify cross-feed data extraction in real time.
            </div>
          </div>

          <div className="testbed-presets-bar">
            <span className="presets-label">Benchmark Presets:</span>
            <button
              type="button"
              className="preset-btn"
              onClick={() => {
                setTestQuery('Kerala floods August 2018');
                handleExecuteLiveQuery('Kerala floods August 2018');
              }}
            >
              🌊 Kerala Floods 2018
            </button>
            <button
              type="button"
              className="preset-btn"
              onClick={() => {
                setTestQuery('Nepal Trishuli landslide August 2026');
                handleExecuteLiveQuery('Nepal Trishuli landslide August 2026');
              }}
            >
              ⛰️ Nepal Landslide 2026
            </button>
            <button
              type="button"
              className="preset-btn"
              onClick={() => {
                setTestQuery('California wildfire August 2020');
                handleExecuteLiveQuery('California wildfire August 2020');
              }}
            >
              🔥 California Fire 2020
            </button>
            <button
              type="button"
              className="preset-btn"
              onClick={() => {
                setTestQuery('Lucknow Gomti floods October 2026');
                handleExecuteLiveQuery('Lucknow Gomti floods October 2026');
              }}
            >
              🛰️ Lucknow Gomti 2026
            </button>
          </div>
        </div>

        {/* Query Input Form */}
        <div className="testbed-input-row">
          <div className="testbed-input-wrap">
            <svg className="search-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              type="text"
              className="testbed-query-input"
              value={testQuery}
              onChange={(e) => setTestQuery(e.target.value)}
              placeholder="Enter natural language disaster query (e.g. 'Assam floods July 2020', 'Japan earthquake 2024')..."
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleExecuteLiveQuery();
              }}
            />
          </div>

          <button
            type="button"
            className="btn-execute-query"
            onClick={() => handleExecuteLiveQuery()}
            disabled={isQuerying}
          >
            {isQuerying ? (
              <>
                <svg className="spinner-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
                </svg>
                <span>Fetching Live Data...</span>
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                </svg>
                <span>Fetch Live Data Now</span>
              </>
            )}
          </button>
        </div>

        {/* Feed Toggle Controls */}
        <div className="feed-toggles-bar">
          <span className="toggles-label">Active Query Feeds:</span>
          <label className="toggle-checkbox-label">
            <input
              type="checkbox"
              checked={feedOptions.enable_tavily}
              onChange={(e) => setFeedOptions({ ...feedOptions, enable_tavily: e.target.checked })}
            />
            <span>Tavily AI</span>
          </label>
          <label className="toggle-checkbox-label">
            <input
              type="checkbox"
              checked={feedOptions.enable_reliefweb}
              onChange={(e) => setFeedOptions({ ...feedOptions, enable_reliefweb: e.target.checked })}
            />
            <span>ReliefWeb UN</span>
          </label>
          <label className="toggle-checkbox-label">
            <input
              type="checkbox"
              checked={feedOptions.enable_firms}
              onChange={(e) => setFeedOptions({ ...feedOptions, enable_firms: e.target.checked })}
            />
            <span>NASA FIRMS</span>
          </label>
          <label className="toggle-checkbox-label">
            <input
              type="checkbox"
              checked={feedOptions.enable_gdacs}
              onChange={(e) => setFeedOptions({ ...feedOptions, enable_gdacs: e.target.checked })}
            />
            <span>GDACS Alerts</span>
          </label>
          <label className="toggle-checkbox-label">
            <input
              type="checkbox"
              checked={feedOptions.enable_usgs}
              onChange={(e) => setFeedOptions({ ...feedOptions, enable_usgs: e.target.checked })}
            />
            <span>USGS Seismology</span>
          </label>

          <button type="button" className="btn-select-all-feeds" onClick={handleResetFeeds}>
            Select All Feeds
          </button>
        </div>
      </div>

      {/* SECTION 4: LIVE QUERY EXECUTION RESULTS */}
      {queryError && (
        <div className="query-error-card">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <div>
            <strong>Query Execution Failed:</strong> {queryError}
          </div>
        </div>
      )}

      {queryResult && (
        <div className="api-results-card">
          {/* SUCCESS BANNER */}
          <div className="results-success-banner">
            <div className="banner-left">
              <div className="success-icon-box">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </div>
              <div>
                <div className="banner-title">
                  Disaster API Successfully Fetched Live Data!
                </div>
                <div className="banner-subtitle">
                  Query: <code>"{queryResult.original_query}"</code> &bull; Response Time: <strong>{queryLatency} ms</strong> &bull; Provenance: <strong>{queryResult.provenance || 'LIVE_API'}</strong>
                </div>
              </div>
            </div>

            <div className="banner-actions">
              <button
                type="button"
                className="btn-copy-json"
                onClick={handleCopyJson}
                title="Copy full JSON report to clipboard"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
                <span>{copiedJson ? 'Copied!' : 'Copy Raw JSON'}</span>
              </button>

              <button
                type="button"
                className="btn-send-to-dashboard"
                onClick={handleSendToDashboard}
                title="View this incident on the Geospatial Satellite Map Dashboard"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon>
                  <line x1="8" y1="2" x2="8" y2="18"></line>
                  <line x1="16" y1="6" x2="16" y2="22"></line>
                </svg>
                <span>View on Geospatial Map</span>
              </button>
            </div>
          </div>

          {/* SOURCE PROVENANCE PILLS */}
          <div className="results-provenance-bar">
            <div className="provenance-group">
              <span className="provenance-label">Sources Queried ({queryResult.sources_queried?.length || 0}):</span>
              {queryResult.sources_queried?.map((src) => {
                const succeeded = queryResult.sources_succeeded?.includes(src);
                return (
                  <span
                    key={src}
                    className={`provenance-pill ${succeeded ? 'pill-succeeded' : 'pill-failed'}`}
                  >
                    {succeeded ? '✓ ' : '✕ '} {src}
                  </span>
                );
              })}
            </div>

            <div className="incident-meta-chips">
              {queryResult.location && (
                <span className="meta-chip">📍 {queryResult.location}</span>
              )}
              {queryResult.disaster_type && (
                <span className="meta-chip">⚠️ {queryResult.disaster_type}</span>
              )}
              {queryResult.incident_date_str && (
                <span className="meta-chip">📅 {queryResult.incident_date_str}</span>
              )}
              {queryResult.bbox && (
                <span className="meta-chip">🗺️ [{queryResult.bbox.map((b) => b.toFixed(2)).join(', ')}]</span>
              )}
            </div>
          </div>

          {/* RESULTS TABS */}
          <div className="results-nav-tabs">
            <button
              type="button"
              className={`results-tab-btn ${activeResultTab === 'overview' ? 'active' : ''}`}
              onClick={() => setActiveResultTab('overview')}
            >
              📊 Intelligence Summary
            </button>
            <button
              type="button"
              className={`results-tab-btn ${activeResultTab === 'tavily' ? 'active' : ''}`}
              onClick={() => setActiveResultTab('tavily')}
            >
              🌐 Tavily Web ({queryResult.tavily?.articles?.length || 0})
            </button>
            <button
              type="button"
              className={`results-tab-btn ${activeResultTab === 'reliefweb' ? 'active' : ''}`}
              onClick={() => setActiveResultTab('reliefweb')}
            >
              📄 ReliefWeb ({queryResult.reliefweb?.matched_reports?.length || queryResult.reliefweb?.total_reports_found || 0})
            </button>
            <button
              type="button"
              className={`results-tab-btn ${activeResultTab === 'firms' ? 'active' : ''}`}
              onClick={() => setActiveResultTab('firms')}
            >
              🔥 NASA FIRMS ({queryResult.firms?.matched_detections?.length || 0})
            </button>
            <button
              type="button"
              className={`results-tab-btn ${activeResultTab === 'gdacs' ? 'active' : ''}`}
              onClick={() => setActiveResultTab('gdacs')}
            >
              ⚠️ GDACS ({queryResult.gdacs?.matched_events?.length || 0})
            </button>
            <button
              type="button"
              className={`results-tab-btn ${activeResultTab === 'usgs' ? 'active' : ''}`}
              onClick={() => setActiveResultTab('usgs')}
            >
              📈 USGS ({queryResult.usgs?.matched_events?.length || 0})
            </button>
            <button
              type="button"
              className={`results-tab-btn ${activeResultTab === 'json' ? 'active' : ''}`}
              onClick={() => setActiveResultTab('json')}
            >
              {'{}'} Raw JSON Payload
            </button>
          </div>

          {/* TAB CONTENT */}
          <div className="results-tab-body">
            {/* OVERVIEW TAB */}
            {activeResultTab === 'overview' && (
              <div className="overview-pane">
                {queryResult.tavily?.synthesized_summary && (
                  <div className="summary-section">
                    <h4 className="section-title">Synthesized Multi-Source Incident Overview</h4>
                    <p className="summary-text">{queryResult.tavily.synthesized_summary}</p>
                  </div>
                )}

                <div className="feed-stats-grid">
                  <div className="stat-card">
                    <div className="stat-label">Tavily Web Sources</div>
                    <div className="stat-value">{queryResult.tavily?.articles?.length || 0}</div>
                    <div className="stat-meta">Status: {queryResult.tavily?.status || 'N/A'}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">ReliefWeb Reports</div>
                    <div className="stat-value">{queryResult.reliefweb?.matched_reports?.length || queryResult.reliefweb?.total_reports_found || 0}</div>
                    <div className="stat-meta">Status: {queryResult.reliefweb?.status || 'N/A'}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">GDACS Alert Level</div>
                    <div className="stat-value">
                      {queryResult.gdacs?.matched_events?.[0]?.alert_level || 'None'}
                    </div>
                    <div className="stat-meta">Alerts: {queryResult.gdacs?.matched_events?.length || 0}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">USGS Earthquakes</div>
                    <div className="stat-value">{queryResult.usgs?.matched_events?.length || 0}</div>
                    <div className="stat-meta">Status: {queryResult.usgs?.status || 'N/A'}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">NASA FIRMS Detections</div>
                    <div className="stat-value">{queryResult.firms?.matched_detections?.length || 0}</div>
                    <div className="stat-meta">Status: {queryResult.firms?.status || 'N/A'}</div>
                  </div>
                </div>

                {queryResult.tavily?.corroborated_facts?.length > 0 && (
                  <div className="corroborated-section">
                    <h4 className="section-title">Corroborated Multi-Source Facts</h4>
                    <ul className="corroborated-list">
                      {queryResult.tavily.corroborated_facts.map((fact, idx) => (
                        <li key={idx} className="corroborated-item">
                          <span className="check-bullet">✓</span>
                          <span>{fact}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* TAVILY TAB */}
            {activeResultTab === 'tavily' && (
              <div className="tavily-pane">
                <div className="pane-header">
                  <h4>Retrieved Web Intelligence Articles ({queryResult.tavily?.articles?.length || 0})</h4>
                  <span className="feed-status-tag">Status: {queryResult.tavily?.status || 'success'}</span>
                </div>

                <div className="articles-list">
                  {queryResult.tavily?.articles?.map((art, i) => (
                    <div key={i} className="article-item-card">
                      <div className="article-item-header">
                        <a
                          href={art.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="article-title-link"
                        >
                          {art.title || art.url}
                        </a>
                        <span className="article-domain-badge">{art.domain || 'web'}</span>
                      </div>
                      <p className="article-snippet">{art.content}</p>
                      <div className="article-footer">
                        {art.published_date && <span>Published: {art.published_date}</span>}
                        {art.score && <span>Relevance Score: {(art.score * 100).toFixed(0)}%</span>}
                        {art.source_credibility && (
                          <span className="credibility-badge">{art.source_credibility}</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {(!queryResult.tavily?.articles || queryResult.tavily.articles.length === 0) && (
                    <div className="empty-feed-msg">No Tavily articles returned for this query.</div>
                  )}
                </div>
              </div>
            )}

            {/* RELIEFWEB TAB */}
            {activeResultTab === 'reliefweb' && (
              <div className="reliefweb-pane">
                <div className="pane-header">
                  <h4>ReliefWeb UN OCHA Situation Reports ({queryResult.reliefweb?.matched_reports?.length || 0} matched)</h4>
                  <span className="feed-status-tag">Total Found: {queryResult.reliefweb?.total_reports_found || 0}</span>
                </div>

                <div className="reports-list">
                  {queryResult.reliefweb?.matched_reports?.map((rep, i) => (
                    <div key={i} className="report-item-card">
                      <div className="report-header">
                        <a
                          href={rep.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="report-title-link"
                        >
                          {rep.title}
                        </a>
                        <span className="report-source-badge">
                          {rep.sources?.join(', ') || 'UN Agency'}
                        </span>
                      </div>
                      {rep.headline && <p className="report-headline">{rep.headline}</p>}
                      <div className="report-footer">
                        {rep.publication_date && <span>Published: {rep.publication_date}</span>}
                        {rep.format && <span className="format-badge">{rep.format}</span>}
                        {rep.primary_country && <span>Focus: {rep.primary_country}</span>}
                      </div>
                    </div>
                  ))}
                  {(!queryResult.reliefweb?.matched_reports || queryResult.reliefweb.matched_reports.length === 0) && (
                    <div className="empty-feed-msg">
                      No matching ReliefWeb situation reports found for this specific event window.
                      {queryResult.reliefweb?.unmatched_reports_count > 0 && (
                        <span> ({queryResult.reliefweb.unmatched_reports_count} reports outside location boundary excluded)</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* NASA FIRMS TAB */}
            {activeResultTab === 'firms' && (
              <div className="firms-pane">
                <div className="pane-header">
                  <h4>NASA FIRMS Active Thermal Detections ({queryResult.firms?.matched_detections?.length || 0})</h4>
                  <span className="feed-status-tag">Sensor: {queryResult.firms?.satellite_source || 'VIIRS_SNPP_NRT'}</span>
                </div>

                {queryResult.firms?.matched_detections?.length > 0 ? (
                  <div className="table-responsive">
                    <table className="detections-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Time</th>
                          <th>Lat / Lon</th>
                          <th>Sensor</th>
                          <th>Brightness (K)</th>
                          <th>FRP (MW)</th>
                          <th>Confidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {queryResult.firms.matched_detections.map((det, i) => (
                          <tr key={i}>
                            <td>{det.acq_date}</td>
                            <td>{det.acq_time || 'N/A'}</td>
                            <td>{det.latitude.toFixed(3)}, {det.longitude.toFixed(3)}</td>
                            <td>{det.satellite || det.instrument || 'VIIRS'}</td>
                            <td>{det.brightness ? `${det.brightness} K` : 'N/A'}</td>
                            <td>{det.frp ? `${det.frp} MW` : 'N/A'}</td>
                            <td>
                              <span className="confidence-pill">{det.confidence || 'nominal'}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty-feed-msg">
                    No active satellite thermal anomalies detected in the target area for this event window.
                    (Status: {queryResult.firms?.status || 'no_detections'})
                  </div>
                )}
              </div>
            )}

            {/* GDACS TAB */}
            {activeResultTab === 'gdacs' && (
              <div className="gdacs-pane">
                <div className="pane-header">
                  <h4>GDACS Multi-Hazard Alerts ({queryResult.gdacs?.matched_events?.length || 0})</h4>
                  <span className="feed-status-tag">Status: {queryResult.gdacs?.status || 'success'}</span>
                </div>

                <div className="gdacs-list">
                  {queryResult.gdacs?.matched_events?.map((ev, i) => (
                    <div key={i} className="gdacs-item-card">
                      <div className="gdacs-header">
                        <span className={`alert-level-badge level-${(ev.alert_level || 'green').toLowerCase()}`}>
                          {ev.alert_level?.toUpperCase() || 'ALERT'}
                        </span>
                        <div className="gdacs-title">{ev.name || ev.event_id}</div>
                      </div>
                      <div className="gdacs-meta-row">
                        {ev.country && <span>Country: {ev.country}</span>}
                        {ev.from_date_str && <span>Date: {ev.from_date_str}</span>}
                        {ev.glide && <span>GLIDE: {ev.glide}</span>}
                        {ev.latitude && ev.longitude && (
                          <span>Coords: {ev.latitude.toFixed(2)}, {ev.longitude.toFixed(2)}</span>
                        )}
                      </div>
                      {ev.report_url && (
                        <div className="gdacs-link-row">
                          <a href={ev.report_url} target="_blank" rel="noopener noreferrer">
                            View Official GDACS Report &rarr;
                          </a>
                        </div>
                      )}
                    </div>
                  ))}
                  {(!queryResult.gdacs?.matched_events || queryResult.gdacs.matched_events.length === 0) && (
                    <div className="empty-feed-msg">No GDACS alerts matched this incident location & date.</div>
                  )}
                </div>
              </div>
            )}

            {/* USGS TAB */}
            {activeResultTab === 'usgs' && (
              <div className="usgs-pane">
                <div className="pane-header">
                  <h4>USGS Earthquake Catalog Events ({queryResult.usgs?.matched_events?.length || 0})</h4>
                  <span className="feed-status-tag">Status: {queryResult.usgs?.status || 'success'}</span>
                </div>

                <div className="usgs-list">
                  {queryResult.usgs?.matched_events?.map((eq, i) => (
                    <div key={i} className="usgs-item-card">
                      <div className="usgs-header">
                        <span className="magnitude-badge">M {eq.magnitude || 'N/A'}</span>
                        <div className="usgs-place">{eq.place}</div>
                      </div>
                      <div className="usgs-meta-row">
                        <span>Depth: {eq.depth_km} km</span>
                        <span>Time: {eq.origin_time_str || 'UTC'}</span>
                        <span>Coords: {eq.latitude?.toFixed(2)}, {eq.longitude?.toFixed(2)}</span>
                      </div>
                      {eq.url && (
                        <div className="usgs-link-row">
                          <a href={eq.url} target="_blank" rel="noopener noreferrer">
                            View USGS Event Page &rarr;
                          </a>
                        </div>
                      )}
                    </div>
                  ))}
                  {(!queryResult.usgs?.matched_events || queryResult.usgs.matched_events.length === 0) && (
                    <div className="empty-feed-msg">
                      No matching seismic events found in USGS catalog for this query (relevant for earthquake hazard types).
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* RAW JSON TAB */}
            {activeResultTab === 'json' && (
              <div className="json-pane">
                <div className="json-actions-bar">
                  <span className="json-label">Complete UnifiedIncidentReport JSON Schema</span>
                  <button type="button" className="btn-copy-json-small" onClick={handleCopyJson}>
                    {copiedJson ? '✓ Copied to Clipboard' : '📋 Copy JSON'}
                  </button>
                </div>
                <pre className="json-code-block">
                  <code>{JSON.stringify(queryResult, null, 2)}</code>
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* SECTION 5: COPERNICUS CDSE STAC CATALOG TEST RESULTS */}
      {catalogResult && (
        <div className="api-catalog-card">
          <div className="catalog-header">
            <h4>🛰️ Copernicus Data Space Ecosystem (CDSE) Sentinel-1 Catalog Results</h4>
            <span className="status-pill success">STAC API REACHABLE</span>
          </div>
          <div className="catalog-summary-line">
            Found <strong>{catalogResult.scenes?.length || 0}</strong> Sentinel-1 GRD scenes matching AOI window.
          </div>
          {catalogResult.scenes?.length > 0 && (
            <div className="catalog-scenes-list">
              {catalogResult.scenes.slice(0, 5).map((scene, i) => (
                <div key={i} className="scene-row">
                  <div className="scene-id">{scene.id || scene.title || `Scene #${i + 1}`}</div>
                  <div className="scene-meta">
                    <span>Date: {scene.sensing_date || scene.datetime || 'N/A'}</span>
                    <span>Orbit: {scene.orbit_direction || 'N/A'}</span>
                    <span>Rel. Orbit: {scene.relative_orbit || 'N/A'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {catalogError && (
        <div className="catalog-error-card">
          <strong>CDSE Catalog Query Error:</strong> {catalogError}
        </div>
      )}
    </div>
  );
}
