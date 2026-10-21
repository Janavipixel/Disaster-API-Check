/**
 * mergeBaseline.js: Safely merges live API data with baseline sample content when specific upstream feeds return empty.
 * Any retained mock content is clearly labeled as SAMPLE or DEMO DATA to maintain data integrity.
 */

export function mergeWithSampleBaseline(baseMock, liveData) {
  if (!liveData) return baseMock;
  if (!baseMock) return { ...liveData, is_live: true, provenance: 'LIVE_API' };

  // 1. Tavily Intelligence & Claims
  const liveClaims = liveData.tavily?.verified_claims;
  const hasLiveClaims = Array.isArray(liveClaims) && liveClaims.length > 0;
  const mergedTavily = {
    ...baseMock.tavily,
    ...liveData.tavily,
  };

  if (!hasLiveClaims && baseMock.tavily?.verified_claims?.length > 0) {
    mergedTavily.verified_claims = baseMock.tavily.verified_claims.map((claim) => ({
      ...claim,
      statement: claim.statement || claim.claim,
      claim: claim.claim || claim.statement,
      topic: claim.topic?.includes('[SAMPLE DEMO]') ? claim.topic : `[SAMPLE DEMO] ${claim.topic || 'Factual Claim'}`,
      context_note: 'SAMPLE DATA: Live Tavily API returned no verified claims or is unconfigured.',
      verification_status: 'single_source',
    }));
    if (!liveData.tavily?.synthesized_summary) {
      mergedTavily.synthesized_summary = `[SAMPLE / DEMO BASELINE DATA] ${baseMock.tavily?.synthesized_summary || ''}`;
    }
  }

  // 2. ReliefWeb Situation Reports
  const liveReliefweb = liveData.reliefweb;
  const isReliefwebLive = Boolean(
    liveReliefweb &&
    liveReliefweb.queried &&
    liveReliefweb.status !== 'error' &&
    liveReliefweb.status !== 'unconfigured'
  );

  const liveReports = liveReliefweb?.matched_reports;
  const hasLiveReports = Array.isArray(liveReports) && liveReports.length > 0;
  const mergedReliefweb = {
    ...baseMock.reliefweb,
    ...liveReliefweb,
  };

  if (isReliefwebLive) {
    if (hasLiveReports) {
      mergedReliefweb.matched_reports = liveReports.map((rep) => ({
        ...rep,
        source: rep.source || (Array.isArray(rep.sources) && rep.sources.length > 0 ? rep.sources.join(', ') : 'ReliefWeb Dispatches'),
        date: rep.date || (rep.publication_date ? rep.publication_date.split('T')[0] : rep.published_date || '--'),
      }));
    } else {
      // Live ReliefWeb was queried and found 0 matching reports for this query window.
      // Do NOT inject mock data; maintain authentic zero-result live state.
      mergedReliefweb.matched_reports = [];
    }
  } else if (baseMock.reliefweb?.matched_reports?.length > 0) {
    // Only fall back to labeled sample data when live ReliefWeb feed is actually unavailable / unconfigured / errored
    mergedReliefweb.matched_reports = baseMock.reliefweb.matched_reports.map((rep) => ({
      ...rep,
      title: rep.title?.includes('[SAMPLE DEMO]') ? rep.title : `[SAMPLE DEMO] ${rep.title || 'Humanitarian SitRep'}`,
      source: rep.source ? `${rep.source} (Sample Demo)` : 'ReliefWeb (Sample Demo)',
      date: rep.date || rep.published_date || '--',
    }));
  }

  // 3. USGS Earthquakes (if seismic query)
  const liveEvents = liveData.usgs?.matched_events;
  const hasLiveEvents = Array.isArray(liveEvents) && liveEvents.length > 0;
  const mergedUsgs = {
    ...baseMock.usgs,
    ...liveData.usgs,
  };
  if (!hasLiveEvents && baseMock.usgs?.matched_events?.length > 0 && liveData.disaster_type === 'earthquake') {
    mergedUsgs.matched_events = baseMock.usgs.matched_events.map((evt) => ({
      ...evt,
      place: evt.place?.includes('[SAMPLE DEMO]') ? evt.place : `[SAMPLE DEMO] ${evt.place || ''}`,
    }));
  }

  // 4. NASA FIRMS (if wildfire query)
  const liveDetections = liveData.firms?.matched_detections;
  const hasLiveDetections = Array.isArray(liveDetections) && liveDetections.length > 0;
  const mergedFirms = {
    ...baseMock.firms,
    ...liveData.firms,
  };
  if (!hasLiveDetections && baseMock.firms?.matched_detections?.length > 0 && liveData.disaster_type === 'wildfire') {
    mergedFirms.matched_detections = baseMock.firms.matched_detections.map((det) => ({
      ...det,
      confidence: det.confidence ? `${det.confidence} (SAMPLE DEMO)` : 'SAMPLE DEMO',
    }));
  }

  return {
    ...baseMock,
    ...liveData,
    tavily: mergedTavily,
    reliefweb: mergedReliefweb,
    usgs: mergedUsgs,
    firms: mergedFirms,
    severity_score: liveData.severity_score ?? baseMock.severity_score ?? liveData.gdacs?.alert_score,
    severity_level: liveData.severity_level ?? baseMock.severity_level ?? liveData.gdacs?.alert_level,
    glide: liveData.glide ?? baseMock.glide,
    is_live: true,
    provenance: (hasLiveClaims || hasLiveReports || hasLiveEvents || hasLiveDetections) ? 'LIVE_API' : 'LIVE_API_SAMPLE_FALLBACK',
  };
}
