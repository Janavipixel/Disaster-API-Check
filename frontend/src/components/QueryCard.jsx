import React from 'react';

const PRESETS = [
  { key: 'kerala', label: 'Kerala Floods 2018' },
  { key: 'lucknow', label: 'Lucknow Gomti Basin 2026' },
  { key: 'nepal', label: 'Nepal Landslide 2026' },
  { key: 'california', label: 'Camp Fire California 2018' },
];

export default function QueryCard({
  query,
  onQueryChange,
  onAnalyze,
  currentIncidentId,
  onSelectPreset,
  isLoading = false,
}) {
  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onAnalyze(query);
    }
  };

  return (
    <section className="query-card">
      <form onSubmit={handleSubmit} className="query-input-row">
        <div className="query-input-wrapper">
          <svg
            className="query-search-icon"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            type="text"
            id="disaster-query-input"
            className="disaster-search-input"
            placeholder="Search or describe any disaster event (e.g. 'Kerala floods August 2018', 'Nepal Trishuli landslide August 2026')..."
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            disabled={isLoading}
          />
        </div>
        <button
          type="submit"
          id="btn-analyze-query"
          className="btn-primary-action"
          disabled={isLoading}
          style={{
            opacity: isLoading ? 0.75 : 1,
            cursor: isLoading ? 'not-allowed' : 'pointer',
          }}
        >
          <span>{isLoading ? 'Analyzing Feeds...' : 'Analyze Incident'}</span>
        </button>
      </form>

      <div className="query-presets-row">
        <span style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', fontWeight: 500, marginRight: '4px' }}>
          Verified Incidents:
        </span>
        {PRESETS.map((preset) => (
          <button
            key={preset.key}
            type="button"
            className={`preset-chip ${currentIncidentId === preset.key ? 'active' : ''}`}
            onClick={() => onSelectPreset(preset.key)}
            disabled={isLoading}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </section>
  );
}
