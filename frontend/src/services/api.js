/**
 * api.js: Production API client connecting Frontend to FastAPI Backend & Copernicus FetchEngine.
 * Handles timeouts, network retries, and honest online/fallback status detection.
 */
// Base URL for backend API calls. In local dev, defaults to '' (proxied by Vite).
// In production on Vercel, can be pointed directly to the live backend via VITE_API_URL.
const rawApiUrl = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ? import.meta.env.VITE_API_URL.trim() : '';
const BASE_URL = rawApiUrl.replace(/\/+$/, '');

/**
 * Perform a fetch request with timeout protection.
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = 25000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
    throw error;
  }
}

/**
 * Safely parse JSON from a response, protecting against HTML SPA rewrites or edge error pages.
 */
async function safeJson(res) {
  if (!res) return null;
  const contentType = res.headers?.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error('Received non-JSON response from server (possible HTML rewrite).');
  }
  return await res.json();
}

/**
 * 1. Health & Subsystem Reachability Check
 */
export async function checkHealth() {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/health`, {}, 5000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await safeJson(res);
  } catch (err) {
    return {
      status: 'offline',
      available: false,
      message: 'Backend server is currently unreachable over HTTP.',
      subsystems: {},
    };
  }
}

/**
 * 2. Unified Disaster Intelligence Query
 */
export async function queryDisaster(queryText, options = {}) {
  const payload = {
    query: queryText,
    enable_tavily: options.enable_tavily ?? true,
    enable_usgs: options.enable_usgs ?? true,
    enable_gdacs: options.enable_gdacs ?? true,
    enable_reliefweb: options.enable_reliefweb ?? true,
    enable_firms: options.enable_firms ?? true,
    limit: options.limit || 10,
  };

  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/disaster/query`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await safeJson(res).catch(() => ({}));
      throw new Error(errData?.detail || `Server returned HTTP ${res.status}`);
    }

    const data = await safeJson(res);
    if (!data) throw new Error('Invalid JSON response from server.');
    return {
      ...data,
      is_live: true,
      provenance: 'LIVE_API',
    };
  } catch (err) {
    // Attempt GET fallback if POST was blocked by intermediary
    try {
      const encoded = encodeURIComponent(queryText);
      const getRes = await fetchWithTimeout(`${BASE_URL}/api/disaster/query?q=${encoded}&limit=${payload.limit}`, {
        method: 'GET',
      });
      if (getRes.ok) {
        const getData = await safeJson(getRes);
        if (getData) {
          return {
            ...getData,
            is_live: true,
            provenance: 'LIVE_API_GET',
          };
        }
      }
    } catch (fallbackErr) {
      // Intentionally fall through
    }
    throw err;
  }
}

/**
 * 3. Fetch List of Benchmark Incidents
 */
export async function getBenchmarkIncidents() {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/disaster/incidents`, {}, 8000);
    if (!res.ok) return null;
    return await safeJson(res);
  } catch (err) {
    return null;
  }
}

/**
 * 4. Fetch Full Benchmark Incident by ID
 */
export async function getBenchmarkIncident(incidentId) {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/disaster/incidents/${incidentId}`, {}, 10000);
    if (!res.ok) return null;
    const data = await safeJson(res);
    if (!data) return null;
    return {
      ...data,
      is_live: true,
      provenance: 'BENCHMARK_VERIFIED_API',
    };
  } catch (err) {
    return null;
  }
}

/**
 * 5. Copernicus CDSE STAC Search
 */
export async function searchCopernicusCatalog(searchParams) {
  const res = await fetchWithTimeout(`${BASE_URL}/api/copernicus/catalog`, {
    method: 'POST',
    body: JSON.stringify(searchParams),
  });

  if (!res.ok) {
    const errData = await safeJson(res).catch(() => ({}));
    throw new Error(errData?.detail || `Catalog search failed (HTTP ${res.status})`);
  }
  return await safeJson(res);
}

/**
 * 6. Trigger or Register FetchEngine Run
 */
export async function triggerCopernicusFetch(fetchParams) {
  const res = await fetchWithTimeout(`${BASE_URL}/api/copernicus/fetch`, {
    method: 'POST',
    body: JSON.stringify(fetchParams),
  });

  if (!res.ok) {
    const errData = await safeJson(res).catch(() => ({}));
    throw new Error(errData?.detail || `Pipeline trigger failed (HTTP ${res.status})`);
  }
  return await safeJson(res);
}

/**
 * 7. Retrieve Live Stage Progression & Output Images
 */
export async function getCopernicusRunStatus(runId) {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/copernicus/status/${runId}`, {}, 8000);
    if (!res.ok) return null;
    return await safeJson(res);
  } catch (err) {
    return null;
  }
}

/**
 * 8. List All Available Disk Runs
 */
export async function listCopernicusRuns() {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/copernicus/runs`, {}, 6000);
    if (!res.ok) return [];
    const data = await safeJson(res);
    return Array.isArray(data) ? data : [];
  } catch (err) {
    return [];
  }
}

/**
 * 9. Retrieve Markdown Mission Intelligence Report
 */
export async function getCopernicusReport(runId) {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/copernicus/runs/${runId}/report`, {}, 8000);
    if (!res.ok) return null;
    const text = await res.text();
    if (text.startsWith('<!DOCTYPE') || text.startsWith('<html')) return null;
    return text;
  } catch (err) {
    return null;
  }
}

