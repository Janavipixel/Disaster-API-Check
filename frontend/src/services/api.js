/**
 * api.js: Production API client connecting Frontend to FastAPI Backend & Copernicus FetchEngine.
 * Handles timeouts, network retries, and honest online/fallback status detection.
 */

const BASE_URL = '';

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
 * 1. Health & Subsystem Reachability Check
 */
export async function checkHealth() {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/health`, {}, 5000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
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
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Server returned HTTP ${res.status}`);
    }

    const data = await res.json();
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
        const getData = await getRes.json();
        return {
          ...getData,
          is_live: true,
          provenance: 'LIVE_API_GET',
        };
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
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return null;
  }
}

/**
 * 4. Fetch Full Benchmark Incident by ID
 */
export async function getBenchmarkIncident(incidentId) {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/disaster/incidents/${incidentId}`, {}, 15000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
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
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Catalog search failed (HTTP ${res.status})`);
  }
  return await res.json();
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
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Pipeline trigger failed (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * 7. Retrieve Live Stage Progression & Output Images
 */
export async function getCopernicusRunStatus(runId) {
  const res = await fetchWithTimeout(`${BASE_URL}/api/copernicus/status/${runId}`, {}, 10000);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(`Failed to load run status (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * 8. List All Available Disk Runs
 */
export async function listCopernicusRuns() {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/api/copernicus/runs`, {}, 6000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
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
    return await res.text();
  } catch (err) {
    return null;
  }
}

