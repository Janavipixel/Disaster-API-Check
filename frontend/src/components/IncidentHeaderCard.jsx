import React, { useState, useMemo, useEffect } from 'react';

// Tokenize text into plain text chunks, source citation chips, and raw URLs
function tokenizeFormatted(text) {
  if (!text) return [];
  const parts = [];
  const regex = /\[Source:\s*([^\]\(\)]+?)(?:\s*\((https?:\/\/[^\s\)]+)\))?\]|((?:https?:\/\/)[^\s\)]+)/gi;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: text.substring(lastIndex, match.index) });
    }
    if (match[1]) {
      const domain = match[1].trim();
      let url = match[2] ? match[2].trim() : (domain.startsWith('http') ? domain : `https://${domain}`);
      url = url.replace(/[.,;]+$/, '');
      parts.push({ type: 'source', domain, url });
    } else if (match[3]) {
      let url = match[3].trim().replace(/[.,;]+$/, '');
      try {
        const u = new URL(url);
        parts.push({ type: 'source', domain: u.hostname.replace(/^www\./, ''), url });
      } catch {
        parts.push({ type: 'url', url });
      }
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.substring(lastIndex) });
  }

  return parts;
}

// Inline Formatted Text component that renders text and clickable source chips
function FormattedText({ text, chipClass = '' }) {
  if (!text) return null;
  const parts = tokenizeFormatted(text);

  return (
    <span>
      {parts.map((p, idx) => {
        if (p.type === 'source') {
          return (
            <a
              key={idx}
              href={p.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`citation-source-chip ${chipClass}`}
              title={`Open verified source: ${p.url}`}
              onClick={(e) => e.stopPropagation()}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
              <span>{p.domain}</span>
            </a>
          );
        }
        if (p.type === 'url') {
          return (
            <a
              key={idx}
              href={p.url}
              target="_blank"
              rel="noopener noreferrer"
              className="citation-source-chip inline-url"
              title={p.url}
              onClick={(e) => e.stopPropagation()}
            >
              {p.url}
            </a>
          );
        }
        return <span key={idx}>{p.value}</span>;
      })}
    </span>
  );
}

// Category metadata helper (icons, theme badges)
function getCategoryMeta(label) {
  const l = (label || '').toLowerCase();
  if (l.includes('timeline') || l.includes('trigger') || l.includes('date')) {
    return {
      name: 'Trigger Timeline',
      icon: '🕒',
      theme: 'cyan',
      badgeColor: '#38bdf8',
      badgeBg: 'rgba(56, 189, 248, 0.12)',
      badgeBorder: 'rgba(56, 189, 248, 0.3)',
    };
  }
  if (l.includes('meteorological') || l.includes('rainfall') || l.includes('weather') || l.includes('wind') || l.includes('intensity')) {
    return {
      name: 'Meteorological Intensity',
      icon: '🌧',
      theme: 'amber',
      badgeColor: '#fbbf24',
      badgeBg: 'rgba(251, 191, 36, 0.12)',
      badgeBorder: 'rgba(251, 191, 36, 0.3)',
    };
  }
  if (l.includes('casualty') || l.includes('fatal') || l.includes('dead') || l.includes('killed') || l.includes('injury')) {
    return {
      name: 'Casualty Reports',
      icon: '⚠️',
      theme: 'rose',
      badgeColor: '#f43f5e',
      badgeBg: 'rgba(244, 63, 94, 0.12)',
      badgeBorder: 'rgba(244, 63, 94, 0.3)',
    };
  }
  if (l.includes('displacement') || l.includes('evacuat') || l.includes('civilian') || l.includes('shelter')) {
    return {
      name: 'Civilian Displacement',
      icon: '👥',
      theme: 'purple',
      badgeColor: '#c084fc',
      badgeBg: 'rgba(192, 132, 252, 0.12)',
      badgeBorder: 'rgba(192, 132, 252, 0.3)',
    };
  }
  if (l.includes('economic') || l.includes('loss') || l.includes('damage') || l.includes('cost') || l.includes('billion') || l.includes('financial')) {
    return {
      name: 'Economic Loss Assessment',
      icon: '💰',
      theme: 'emerald',
      badgeColor: '#34d399',
      badgeBg: 'rgba(52, 211, 153, 0.12)',
      badgeBorder: 'rgba(52, 211, 153, 0.3)',
    };
  }
  if (l.includes('geographic') || l.includes('inundat') || l.includes('area') || l.includes('scope')) {
    return {
      name: 'Geographic Impact Scope',
      icon: '🗺',
      theme: 'indigo',
      badgeColor: '#818cf8',
      badgeBg: 'rgba(129, 140, 248, 0.12)',
      badgeBorder: 'rgba(129, 140, 248, 0.3)',
    };
  }
  return {
    name: label,
    icon: '📋',
    theme: 'blue',
    badgeColor: '#60a5fa',
    badgeBg: 'rgba(96, 165, 250, 0.12)',
    badgeBorder: 'rgba(96, 165, 250, 0.3)',
  };
}

// Parses raw synthesized summary into overview, structured category items, and unique sources
function parseSynthesizedSummary(rawText) {
  if (!rawText) return { overview: '', items: [], allSources: [] };

  // Split by line breaks or ' - ' preceding a capitalized category name
  const rawParts = rawText
    .split(/(?:\r?\n\s*-\s*|\r?\n+|\s+-\s+)(?=[A-Z][a-zA-Z\s]{2,30}:)/)
    .map((p) => p.trim())
    .filter(Boolean);

  let overview = '';
  const items = [];
  const sourcesMap = new Map();

  // Helper to extract unique sources
  const srcRegex = /\[Source:\s*([^\]\(\)]+?)(?:\s*\((https?:\/\/[^\s\)]+)\))?\]/gi;
  let m;
  while ((m = srcRegex.exec(rawText)) !== null) {
    const domain = m[1].trim();
    const url = m[2] ? m[2].trim() : (domain.startsWith('http') ? domain : `https://${domain}`);
    if (!sourcesMap.has(url)) {
      sourcesMap.set(url, { domain, url });
    }
  }

  for (const part of rawParts) {
    const colonIdx = part.indexOf(':');
    if (colonIdx > 0 && colonIdx < 35) {
      const label = part.slice(0, colonIdx).replace(/^-\s*/, '').trim();
      const body = part.slice(colonIdx + 1).trim();

      if (label.toLowerCase() === 'incident summary' && !overview) {
        overview = body;
        continue;
      }

      // Check for sub-excerpts: * Excerpt: "..." [Source: ...]
      const excerptParts = body.split(/\s*\*\s*Excerpt:\s*/);
      const mainText = excerptParts[0].trim();
      const excerpts = excerptParts.slice(1).map((e) => e.trim());

      items.push({
        label,
        mainText,
        excerpts,
        meta: getCategoryMeta(label),
        raw: part,
      });
    } else {
      if (!overview) {
        overview = part;
      } else {
        items.push({
          label: 'Intelligence Finding',
          mainText: part,
          excerpts: [],
          meta: getCategoryMeta('Intelligence Finding'),
          raw: part,
        });
      }
    }
  }

  const allSources = Array.from(sourcesMap.values());
  return { overview, items, allSources };
}

export default function IncidentHeaderCard({ incident, onRecenter }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (!isModalOpen) return;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setIsModalOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isModalOpen]);

  const rawSummary = incident?.tavily?.synthesized_summary || incident?.description || '';
  const { overview, items, allSources } = useMemo(
    () => parseSynthesizedSummary(rawSummary),
    [rawSummary]
  );

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
      {/* Top Header Row */}
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

      {/* Structured Multi-Source Intelligence Section */}
      <div className="intelligence-overview-block">
        <div className="intelligence-header-row">
          <div className="intelligence-badge-row">
            <span className="intelligence-lead-tag">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
              Multi-Source Intelligence
            </span>
            {allSources.length > 0 && (
              <span className="intelligence-sources-count">
                {allSources.length} verified {allSources.length === 1 ? 'source' : 'sources'}
              </span>
            )}
            {items.length > 0 && (
              <span className="intelligence-items-count">
                {items.length} findings
              </span>
            )}
          </div>

          <div className="intelligence-action-buttons">
            {items.length > 0 && (
              <button
                type="button"
                className={`btn-intelligence-toggle ${isExpanded ? 'active' : ''}`}
                onClick={() => setIsExpanded(!isExpanded)}
                id="btn-toggle-intel-breakdown"
                title={isExpanded ? 'Hide detailed findings breakdown' : 'Read more structured findings'}
              >
                <span>{isExpanded ? 'Hide Details' : 'Read More Details'}</span>
                <span className="toggle-chevron">{isExpanded ? '▲' : '▼'}</span>
              </button>
            )}
            <button
              type="button"
              className="btn-intelligence-modal"
              onClick={() => setIsModalOpen(true)}
              id="btn-open-intel-dossier"
              title="Expand into full-size multi-source dossier card (like raster inspection)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <polyline points="15 3 21 3 21 9"></polyline>
                <polyline points="9 21 3 21 3 15"></polyline>
                <line x1="21" y1="3" x2="14" y2="10"></line>
                <line x1="3" y1="21" x2="10" y2="14"></line>
              </svg>
              <span>Expand to Big Card</span>
            </button>
          </div>
        </div>

        {/* Lead Executive Synthesis text */}
        <div className="intelligence-lead-text">
          <FormattedText text={overview || rawSummary || 'Incident data parsed and cross-correlated across global feeds.'} />
        </div>

        {/* Inline Structured Breakdown */}
        {items.length > 0 && isExpanded && (
          <div className="intelligence-breakdown-container">
            <div className="intelligence-items-list">
              {items.map((item, idx) => (
                <div key={idx} className={`intelligence-item-card theme-${item.meta.theme}`}>
                  <div className="intelligence-item-header">
                    <span
                      className="item-category-pill"
                      style={{
                        color: item.meta.badgeColor,
                        background: item.meta.badgeBg,
                        borderColor: item.meta.badgeBorder,
                      }}
                    >
                      <span className="category-icon">{item.meta.icon}</span>
                      <span className="category-name">{item.meta.name}</span>
                    </span>
                  </div>
                  <div className="intelligence-item-body">
                    <FormattedText text={item.mainText} />
                  </div>
                  {item.excerpts && item.excerpts.length > 0 && (
                    <div className="intelligence-excerpts-box">
                      {item.excerpts.map((ex, exIdx) => (
                        <blockquote key={exIdx} className="item-excerpt-quote">
                          <span className="quote-mark">“</span>
                          <div className="quote-content">
                            <FormattedText text={ex} />
                          </div>
                        </blockquote>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="intelligence-inline-footer">
              <button
                type="button"
                className="btn-open-bigcard-link"
                onClick={() => setIsModalOpen(true)}
              >
                <span>View Full Multi-Source Intelligence Dossier (Big Card View) ⛶</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Meta Stats Row */}
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

      {/* Coordinates Panel */}
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

      {/* High-Resolution Big Card Modal (Matching Raster Modal Lightbox) */}
      {isModalOpen && (
        <div
          className="modal-overlay open"
          style={{ zIndex: 3000 }}
          onClick={() => setIsModalOpen(false)}
        >
          <div
            className="modal-box intelligence-modal-box"
            style={{
              maxWidth: '1060px',
              width: '95vw',
              maxHeight: '92vh',
              display: 'flex',
              flexDirection: 'column',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <span className="modal-title">Comprehensive Multi-Source Disaster Intelligence Dossier</span>
                <span className={`severity-pill ${isRed ? 'pill-red' : 'pill-orange'}`}>
                  {isRed ? 'Red Alert' : 'Orange Alert'}
                </span>
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
                  }}
                >
                  {incident.is_live ? '● Live API' : '○ Baseline Fallback'}
                </span>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setIsModalOpen(false)}
                title="Close (Esc)"
              >
                ✕
              </button>
            </div>

            <div className="modal-body intelligence-modal-body" style={{ overflowY: 'auto', padding: '22px' }}>
              {/* Executive Callout */}
              <div className="modal-overview-callout">
                <div className="modal-overview-tag">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="16" x2="12" y2="12"></line>
                    <line x1="12" y1="8" x2="12.01" y2="8"></line>
                  </svg>
                  <span>Executive Incident Synthesis</span>
                </div>
                <h2 className="modal-overview-heading">{incident.original_query}</h2>
                <div className="modal-overview-paragraph">
                  <FormattedText text={overview || rawSummary || 'Incident data parsed and cross-correlated across global feeds.'} />
                </div>

                <div className="modal-intel-meta-row">
                  <div className="modal-meta-chip">
                    <span className="modal-meta-label">Hazard:</span>
                    <span className="modal-meta-val">{hazardType}</span>
                  </div>
                  <div className="modal-meta-chip">
                    <span className="modal-meta-label">Event Window:</span>
                    <span className="modal-meta-val">{windowStr}</span>
                  </div>
                  <div className="modal-meta-chip">
                    <span className="modal-meta-label">GLIDE Code:</span>
                    <span className="modal-meta-val">{incident.glide || 'Pending'}</span>
                  </div>
                  <div className="modal-meta-chip">
                    <span className="modal-meta-label">Coordinates:</span>
                    <span className="modal-meta-val">Lat {latStr}, Lon {lonStr}{depthStr}</span>
                  </div>
                  <div className="modal-meta-chip">
                    <span className="modal-meta-label">Severity Score:</span>
                    <span className="modal-meta-val">{scoreStr}</span>
                  </div>
                </div>
              </div>

              {/* Categorized Findings */}
              {items.length > 0 && (
                <div style={{ marginTop: '24px' }}>
                  <div className="modal-section-title-bar">
                    <h3 className="modal-section-title">
                      Verified Operational Claims & Findings ({items.length})
                    </h3>
                    <span className="modal-section-sub">
                      Cross-referenced facts extracted from authenticated operational dispatches and retrospective reporting
                    </span>
                  </div>

                  <div className="modal-intelligence-grid">
                    {items.map((item, idx) => (
                      <div key={idx} className={`modal-intelligence-card theme-${item.meta.theme}`}>
                        <div className="modal-item-header">
                          <span
                            className="item-category-pill"
                            style={{
                              color: item.meta.badgeColor,
                              background: item.meta.badgeBg,
                              borderColor: item.meta.badgeBorder,
                            }}
                          >
                            <span className="category-icon">{item.meta.icon}</span>
                            <span className="category-name">{item.meta.name}</span>
                          </span>
                        </div>
                        <div className="modal-item-text">
                          <FormattedText text={item.mainText} />
                        </div>

                        {item.excerpts && item.excerpts.length > 0 && (
                          <div className="modal-item-excerpts">
                            <div className="modal-excerpt-label">Primary Source Excerpts & Dispatches:</div>
                            {item.excerpts.map((ex, exIdx) => (
                              <blockquote key={exIdx} className="item-excerpt-quote">
                                <span className="quote-mark">“</span>
                                <div className="quote-content">
                                  <FormattedText text={ex} />
                                </div>
                              </blockquote>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Verified Sources & Web Citations Directory */}
              {allSources.length > 0 && (
                <div className="modal-sources-section">
                  <div className="modal-section-title-bar" style={{ marginTop: '26px' }}>
                    <h3 className="modal-section-title">
                      Verified Reporting Outlets & Primary Sources ({allSources.length})
                    </h3>
                    <span className="modal-section-sub">
                      Click any source to inspect original coverage and full verification documents
                    </span>
                  </div>
                  <div className="modal-sources-grid">
                    {allSources.map((src, idx) => (
                      <a
                        key={idx}
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="modal-source-card"
                        title={`Open source: ${src.url}`}
                      >
                        <div className="source-card-icon">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                          </svg>
                        </div>
                        <div className="source-card-info">
                          <span className="source-domain">{src.domain}</span>
                          <span className="source-full-url">{src.url}</span>
                        </div>
                        <div className="source-open-arrow">↗</div>
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer" style={{ padding: '14px 22px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)' }}>
                Multi-source synthesis verified via Tavily Search & Bhūmi RAG Cross-Verification Engine
              </span>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setIsModalOpen(false)}
                style={{ height: '32px', fontSize: '0.78rem' }}
              >
                Close Dossier
              </button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
