import React, { useState, useEffect } from 'react';
import Header from './components/Header.jsx';
import QueryCard from './components/QueryCard.jsx';
import MapCard from './components/MapCard.jsx';
import IncidentHeaderCard from './components/IncidentHeaderCard.jsx';
import FeedsCard from './components/FeedsCard.jsx';
import SatelliteComparisonCard from './components/SatelliteComparisonCard.jsx';
import CopernicusStepperCard from './components/CopernicusStepperCard.jsx';
import GroundTruthNotice from './components/GroundTruthNotice.jsx';
import JsonModal from './components/JsonModal.jsx';
import DisasterApiMonitor from './components/DisasterApiMonitor.jsx';
import { MOCK_INCIDENTS } from './data/mockIncidents.js';
import {
  checkHealth,
  queryDisaster,
  getBenchmarkIncident,
  getCopernicusRunStatus,
} from './services/api.js';
import { mergeWithSampleBaseline } from './utils/mergeBaseline.js';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard' | 'disaster_api'
  const [currentIncidentKey, setCurrentIncidentKey] = useState('kerala');
  const [currentIncident, setCurrentIncident] = useState(MOCK_INCIDENTS['kerala']);
  const [copernicusRun, setCopernicusRun] = useState(null);
  const [query, setQuery] = useState('Kerala floods August 2018');
  const [isJsonModalOpen, setIsJsonModalOpen] = useState(false);
  const [recenterTrigger, setRecenterTrigger] = useState(0);
  const [isLive, setIsLive] = useState(false);
  const [cdseStatus, setCdseStatus] = useState('UNKNOWN');
  const [isLoading, setIsLoading] = useState(false);
  const [errorNotice, setErrorNotice] = useState(null);

  // Initialize and check backend connection on mount
  useEffect(() => {
    let isMounted = true;

    async function initializePlatform() {
      try {
        const health = await checkHealth();
        if (!isMounted) return;

        if (health.status === 'healthy') {
          setIsLive(true);
          const cdseState = health.subsystems?.copernicus_cdse?.status || 'healthy';
          setCdseStatus(cdseState);

          // Fetch initial live incident intelligence for Kerala
          try {
            const liveData = await queryDisaster('Kerala floods August 2018', { limit: 10 });
            if (isMounted && liveData) {
              const merged = mergeWithSampleBaseline(MOCK_INCIDENTS['kerala'], liveData);
              setCurrentIncident(merged);

              // Load active Copernicus run
              const runId = liveData.benchmark_run_id || 'kerala_2018-08-10';
              const runSt = await getCopernicusRunStatus(runId);
              if (isMounted && runSt) setCopernicusRun(runSt);
            }
          } catch (queryErr) {
            console.warn('Initial live query fallback to preset:', queryErr);
          }
        } else {
          setIsLive(false);
          setCdseStatus('offline');
        }
      } catch (err) {
        if (isMounted) {
          setIsLive(false);
          setCdseStatus('offline');
        }
      }
    }

    initializePlatform();
    return () => { isMounted = false; };
  }, []);

  const presetReqIdRef = useRef(0);

  // Preset Selection Handler
  const handleSelectPreset = async (key) => {
    setCurrentIncidentKey(key);
    setErrorNotice(null);

    const preset = MOCK_INCIDENTS[key];
    if (preset) {
      setQuery(preset.original_query);
      setCurrentIncident(preset);
      if (!preset.satellite_layers?.run_id) {
        setCopernicusRun(null);
      }
    }

    const currentReq = ++presetReqIdRef.current;

    // If backend is live, execute query through the real API
    if (isLive && preset) {
      setIsLoading(true);
      try {
        const liveData = await queryDisaster(preset.original_query, { limit: 10 });
        if (presetReqIdRef.current !== currentReq) return;

        const merged = mergeWithSampleBaseline(preset, liveData);
        setCurrentIncident(merged);

        const targetRunId = liveData.benchmark_run_id || preset.satellite_layers?.run_id;
        if (targetRunId) {
          const runSt = await getCopernicusRunStatus(targetRunId);
          if (presetReqIdRef.current === currentReq && runSt) setCopernicusRun(runSt);
        } else {
          setCopernicusRun(null);
        }
      } catch (err) {
        console.warn(`Preset live fetch failed for ${key}, using cached fallback:`, err);
      } finally {
        if (presetReqIdRef.current === currentReq) {
          setIsLoading(false);
        }
      }
    } else if (preset?.satellite_layers?.run_id) {
      try {
        const runSt = await getCopernicusRunStatus(preset.satellite_layers.run_id);
        if (presetReqIdRef.current === currentReq && runSt) setCopernicusRun(runSt);
      } catch (e) {
        // Safe ignore
      }
    } else {
      setCopernicusRun(null);
    }
  };

  // User-Driven Query Execution from UI
  const handleAnalyze = async (rawQuery) => {
    const q = (rawQuery || '').trim();
    if (!q) return;

    setIsLoading(true);
    setErrorNotice(null);

    if (isLive) {
      try {
        const liveData = await queryDisaster(q, { limit: 10 });

        // Match key if present in presets
        const qLower = q.toLowerCase();
        let matchedKey = '';
        if (qLower.includes('kerala')) matchedKey = 'kerala';
        else if (qLower.includes('lucknow') || qLower.includes('gomti')) matchedKey = 'lucknow';
        else if (qLower.includes('nepal') || qLower.includes('trishuli') || qLower.includes('landslide')) matchedKey = 'nepal';
        else if (qLower.includes('camp') || qLower.includes('california') || qLower.includes('fire')) matchedKey = 'california';

        const baseMock = matchedKey && MOCK_INCIDENTS[matchedKey] ? MOCK_INCIDENTS[matchedKey] : null;
        const fullIncident = {
          ...mergeWithSampleBaseline(baseMock, liveData),
          id: matchedKey || 'custom-incident',
        };

        setCurrentIncidentKey(matchedKey);
        setCurrentIncident(fullIncident);

        // Link with Copernicus run if benchmark or resolved
        const runId = liveData.benchmark_run_id || fullIncident.satellite_layers?.run_id;
        if (runId) {
          const runSt = await getCopernicusRunStatus(runId);
          if (runSt) setCopernicusRun(runSt);
        } else {
          setCopernicusRun(null);
        }
      } catch (err) {
        setErrorNotice(`Backend query failed: ${err.message}. Retaining cached baseline.`);
        fallbackLocalAnalyze(q);
      } finally {
        setIsLoading(false);
      }
    } else {
      fallbackLocalAnalyze(q);
      setIsLoading(false);
    }
  };

  const fallbackLocalAnalyze = (q) => {
    const qLower = q.toLowerCase();
    let matchedKey = null;
    if (qLower.includes('kerala')) matchedKey = 'kerala';
    else if (qLower.includes('lucknow') || qLower.includes('gomti')) matchedKey = 'lucknow';
    else if (qLower.includes('nepal') || qLower.includes('trishuli') || qLower.includes('landslide')) matchedKey = 'nepal';
    else if (qLower.includes('camp') || qLower.includes('california') || qLower.includes('fire')) matchedKey = 'california';

    if (matchedKey && MOCK_INCIDENTS[matchedKey]) {
      const inc = MOCK_INCIDENTS[matchedKey];
      setCurrentIncidentKey(matchedKey);
      setCurrentIncident({
        ...inc,
        is_live: false,
        provenance: 'OFFLINE_BASELINE',
      });
      if (!inc.satellite_layers?.run_id) {
        setCopernicusRun(null);
      }
    } else {
      const dynamicIncident = {
        ...MOCK_INCIDENTS['kerala'],
        id: 'custom',
        original_query: q,
        location: q.split(' ')[0].toUpperCase(),
        incident_date_str: 'Event Window',
        is_live: false,
        provenance: 'OFFLINE_DYNAMIC',
      };
      setCurrentIncidentKey('');
      setCurrentIncident(dynamicIncident);
    }
  };

  const handleRecenter = () => {
    setRecenterTrigger((prev) => prev + 1);
  };

  // Callback when user tests query in DisasterApiMonitor and clicks "View on Geospatial Map"
  const handleApplyFromMonitor = async (apiReport) => {
    if (!apiReport) return;
    const q = apiReport.original_query || '';
    setQuery(q);

    const qLower = q.toLowerCase();
    let matchedKey = '';
    if (qLower.includes('kerala')) matchedKey = 'kerala';
    else if (qLower.includes('lucknow') || qLower.includes('gomti')) matchedKey = 'lucknow';
    else if (qLower.includes('nepal') || qLower.includes('trishuli') || qLower.includes('landslide')) matchedKey = 'nepal';
    else if (qLower.includes('camp') || qLower.includes('california') || qLower.includes('fire')) matchedKey = 'california';

    const baseMock = matchedKey && MOCK_INCIDENTS[matchedKey] ? MOCK_INCIDENTS[matchedKey] : null;
    const fullIncident = {
      ...mergeWithSampleBaseline(baseMock, apiReport),
      id: matchedKey || 'custom-incident',
    };

    setCurrentIncidentKey(matchedKey);
    setCurrentIncident(fullIncident);

    const runId = apiReport.benchmark_run_id || fullIncident.satellite_layers?.run_id;
    if (runId) {
      try {
        const runSt = await getCopernicusRunStatus(runId);
        if (runSt) setCopernicusRun(runSt);
      } catch (e) {
        // Safe ignore
      }
    }
  };

  return (
    <>
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onOpenJsonModal={() => setIsJsonModalOpen(false || true)}
        isLive={isLive}
        cdseStatus={cdseStatus}
        isFetching={isLoading}
      />

      <main className="app-container">
        {errorNotice && (
          <div style={{ background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '6px', padding: '10px 14px', marginBottom: '16px', fontSize: '0.82rem', color: '#fca5a5' }}>
            ⚠️ {errorNotice}
          </div>
        )}

        {/* TAB 1: DISASTER INTELLIGENCE PLATFORM DASHBOARD */}
        {activeTab === 'dashboard' && (
          <>
            {/* Search & Preset Selection Bar */}
            <QueryCard
              query={query}
              onQueryChange={setQuery}
              onAnalyze={handleAnalyze}
              currentIncidentId={currentIncidentKey}
              onSelectPreset={handleSelectPreset}
              isLoading={isLoading}
            />

            {/* HERO FOCUS: Disaster Geospatial Satellite Map (Full-Width Horizontal Slab) */}
            <MapCard incident={currentIncident} recenterTrigger={recenterTrigger} />

            {/* LOWER WORKSPACE: Two-Column Intelligence & Analytics */}
            <section className="workspace-grid">
              {/* COLUMN 1: Incident Grounding & Feeds Navigation (Left) */}
              <div className="column-stack">
                <IncidentHeaderCard incident={currentIncident} onRecenter={handleRecenter} />
                <FeedsCard incident={currentIncident} />
              </div>

              {/* COLUMN 2: Multi-Temporal Satellite Analytics & Copernicus Stepper (Right) */}
              <div className="column-stack">
                <SatelliteComparisonCard
                  incident={currentIncident}
                  copernicusRun={copernicusRun}
                  onSelectPreset={handleSelectPreset}
                />
                <CopernicusStepperCard
                  incident={currentIncident}
                  runId={copernicusRun?.run_id}
                  onRunUpdated={(updated) => setCopernicusRun(updated)}
                  onSelectPreset={handleSelectPreset}
                />
                <GroundTruthNotice />
              </div>
            </section>
          </>
        )}

        {/* TAB 2: DISASTER API LIVE DIAGNOSTICS & MONITOR */}
        {activeTab === 'disaster_api' && (
          <DisasterApiMonitor
            onSwitchToDashboard={() => setActiveTab('dashboard')}
            onApplyIncidentToDashboard={handleApplyFromMonitor}
          />
        )}
      </main>

      {/* Raw JSON Inspection Modal */}
      <JsonModal
        isOpen={isJsonModalOpen}
        onClose={() => setIsJsonModalOpen(false)}
        incident={currentIncident}
      />
    </>
  );
}
