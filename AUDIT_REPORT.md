# Comprehensive Engineering & Remote-Sensing Platform Audit
**Target System:** Disaster Intelligence Platform (Rakhshak) & RAG-AI Integration  
**Auditor:** Senior Engineer & Remote-Sensing Specialist  
**Workspace:** `Disaster-API-Check`  
**Date:** October 2026  
**Mode:** READ-ONLY Verification (No project code altered)

---

## 0. Executive Summary & Readiness Scores

The workspace contains two substantial but decoupled codebases: (1) **Rakhshak**, an asynchronous disaster monitoring platform combining a FastAPI backend, a Vite/React geospatial frontend, a multi-source intelligence aggregator (Tavily, USGS, GDACS, ReliefWeb, NASA FIRMS), and a Copernicus Sentinel-1 SAR change-detection engine (`fetchengine`); and (2) **RAG-AI-main**, an unintegrated, standalone question-answering and web-scraping module featuring local ChromaDB vector indexing, sentence-transformers embeddings, and LLM answer generation (Gemini/OpenAI/offline).

While both subsystems exhibit strong software craftsmanship in isolation—including comprehensive unit test suites and resilient error fallbacks—they are completely disconnected today. The frontend relies heavily on precomputed disk fixtures (`kerala_2018-08-10`, `lucknow_2026-10-01`) and hardcoded mock objects. The SAR pipeline implements a functional differential backscatter algorithm via Sentinel Hub Process API, but lacks critical radiometric terrain flattening (RTC), Height Above Nearest Drainage (HAND) or slope masking, and true multi-temporal baseline averaging. The trigger endpoint in the backend initializes a directory but never dispatches an execution worker.

### Overall Readiness Scorecard (out of 10)

| Dimension | Score (/10) | Primary Driver / Blocker |
| :--- | :---: | :--- |
| **Integration** | **3 / 10** | RAG-AI is completely standalone; `create_ai_router()` is not mounted in FastAPI; `frontend` has no UI for RAG Q&A. |
| **Live Data** | **4 / 10** | External APIs (ReliefWeb, Tavily, FIRMS, CDSE) fall back silently to precomputed sample fixtures; UI displays "ONLINE" even with missing credentials. |
| **Scientific Validity** | **4 / 10** | Ellipsoid sigma0 used instead of RTC; no HAND or slope mask; heuristic permanent water exclusion; no validation against Copernicus EMS ground truth. |
| **Automation** | **2 / 10** | Triggering the pipeline from the API creates a `metadata.json` marked `QUEUED` but never spawns a background process or worker. |

---

## 1. Env / Config Inventory & Canonical Configuration

### 1.1 Inventory of Config and Environment Files

| Configuration File | Path | Scope / Consumers |
| :--- | :--- | :--- |
| Root `.env.example` | `/.env.example` | Template for platform API keys (Tavily, FIRMS, ReliefWeb, CDSE). |
| RAG-AI `.env.example` | `/RAG-AI-main/.env.example` | Template for LLM keys (Gemini, OpenAI, local Chroma, Embeddings). |
| Fetchengine YAML (Kerala) | `/fetchengine/config.yaml` | Search windows, AOI bbox, resolution, and threshold parameters for Kerala 2018. |
| Fetchengine YAML (Lucknow) | `/fetchengine/config_lucknow.yaml` | AOI bbox, search windows, and thresholds for Lucknow 2026 test. |
| RAG Scraper Sources | `/RAG-AI-main/config/sources.json` | Web scraping targets (HTML URLs, RSS feeds, ReliefWeb REST endpoint). |
| Disaster API Config Module | `/Disaster API/src/config.py` | Python configuration classes for Tavily, USGS, GDACS, ReliefWeb, FIRMS. |
| Fetchengine Pipeline Utils | `/fetchengine/pipeline_utils.py` | Hardcoded `.env` loader looking strictly inside `fetchengine/.env`. |
| Fetchengine OData Prototype | `/fetchengine/cdse_fetch.py` | Legacy downloader script reading `CDSE_USER` and `CDSE_PASS`. |
| Root Server Runner | `/run_server.py` | Hardcoded host (`127.0.0.1`), port (`8000`), and `app_dir` configuration. |
| Batch Launcher | `/start_all.bat` | Windows CMD launcher running `py run_server.py` and `npm run dev`. |
| PowerShell Launcher | `/start_all.ps1` | Windows PowerShell launcher running background process and dev server. |
| Vite Server Config | `/frontend/vite.config.js` | Dev server port (`5173`) and proxy forwarding (`/api`, `/runs` to `http://127.0.0.1:8000`). |
| Frontend API Service | `/frontend/src/services/api.js` | Client-side base URL configuration (`const BASE_URL = ''`). |

### 1.2 Variable Inventory & Audit Table

| Variable Name | Defined in Files | Values Conflicting? | Read by Code (File:Line) | Status | Secret? | Semantic Aliases / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `CDSE_CLIENT_ID` | `/.env.example:21` | No | `cdse_bridge.py:104`, `pipeline_utils.py:29`, `cdse_process.py:72` | Active | Yes | OAuth2 Client ID for Copernicus Sentinel Hub Process API. |
| `CDSE_CLIENT_SECRET` | `/.env.example:22` | No | `cdse_bridge.py:105`, `pipeline_utils.py:30`, `cdse_process.py:73` | Active | Yes | OAuth2 Client Secret for Copernicus Sentinel Hub. |
| `CDSE_USER` | None (`.env` note) | **CONFLICT** | `cdse_fetch.py:55` | Stale | Yes | Legacy OData username; conflicts with OAuth2 client workflow. |
| `CDSE_PASS` | None (`.env` note) | **CONFLICT** | `cdse_fetch.py:56` | Stale | Yes | Legacy OData password; conflicts with OAuth2 client workflow. |
| `TAVILY_API_KEY` | `/.env.example:9`, `RAG-AI-main/.env.example:14` | No | `Disaster API/src/config.py:49`, `Disaster API/src/server.py:135`, `RAG-AI-main/scraper/tavily_scraper.py:40` | Active | Yes | Shared across Disaster API and RAG-AI module. |
| `TAVILY_SEARCH_DEPTH` | None (defaults to `advanced`) | No | `Disaster API/src/config.py:52` | Active | No | Search depth (`basic` vs `advanced`). |
| `TAVILY_MAX_RESULTS` | None (defaults to `5`) | No | `Disaster API/src/config.py:54` | Active | No | Max articles returned. |
| `FIRMS_MAP_KEY` | `/.env.example:13` | No | `Disaster API/src/config.py:303`, `Disaster API/src/server.py:139` | Active | Yes | 32-character NASA EOSDIS thermal map key. |
| `FIRMS_BASE_URL` | None (defaults) | No | `Disaster API/src/config.py:306` | Active | No | Defaults to `https://firms.modaps.eosdis.nasa.gov/api`. |
| `FIRMS_SOURCE` | None (defaults) | No | `Disaster API/src/config.py:312` | Active | No | Satellite sensor: defaults to `VIIRS_SNPP_NRT`. |
| `RELIEFWEB_APPNAME` | `/.env.example:17` | No | `Disaster API/src/config.py:221`, `RAG-AI-main/scraper/api_scraper.py:78` | Active | No | Mandatory app identifier for ReliefWeb API v2. |
| `RELIEFWEB_BASE_URL` | None (defaults) | **CONFLICT** | `Disaster API/src/config.py:224` | Active | No | `Disaster API` uses v2 (`api.reliefweb.int/v2/reports`); `RAG-AI` uses v1 (`api.reliefweb.int/v1/reports`). |
| `USGS_BASE_URL` | None (defaults) | No | `Disaster API/src/config.py:121` | Active | No | Defaults to `https://earthquake.usgs.gov/fdsnws/event/1/query`. |
| `GDACS_BASE_URL` | None (defaults) | No | `Disaster API/src/config.py:166` | Active | No | Defaults to `https://www.gdacs.org/gdacsapi/api/events/geteventlist/search`. |
| `GOOGLE_API_KEY` | `RAG-AI-main/.env.example:7` | No | `RAG-AI-main/rag/generator.py:138,288`, `metadata_extractor.py:55` | Active | Yes | Used for Gemini LLM text generation. |
| `OPENAI_API_KEY` | `RAG-AI-main/.env.example:10` | No | `RAG-AI-main/rag/generator.py:143,303`, `metadata_extractor.py:57` | Active | Yes | Used for OpenAI GPT-4o-mini generation. |
| `EMBEDDING_MODEL` | `RAG-AI-main/.env.example:17` | No | `RAG-AI-main/rag/embedder.py:16` | Active | No | Defaults to `all-MiniLM-L6-v2`. |
| `EMBEDDING_DEVICE` | `RAG-AI-main/.env.example:18` | No | `RAG-AI-main/rag/embedder.py:17` | Active | No | Defaults to `cpu`. |
| `CHROMA_PERSIST_DIR` | `RAG-AI-main/.env.example:21` | No | `RAG-AI-main/rag/vector_store.py:23`, `RAG-AI-main/rag/pipeline.py:128` | Active | No | Defaults to `RAG-AI-main/data/chroma_db`. |
| `LOG_LEVEL` | `RAG-AI-main/.env.example:24` | No | `RAG-AI-main/rag/generator.py`, etc. | Active | No | Controls logging verbosity. |

### 1.3 Hardcoded Secrets, URLs, Ports, and Paths in Code

1. **Hardcoded Ports**:
   - `run_server.py:23`: Port `8000` hardcoded.
   - `frontend/vite.config.js:8`: Port `5173` hardcoded.
   - `frontend/vite.config.js:11,15`: Proxy target `http://127.0.0.1:8000` hardcoded.
   - `start_all.bat:9,21` and `start_all.ps1:8,19`: Ports `8000` and `5173` hardcoded in echo strings and CLI flags.
2. **Hardcoded Upstream API Endpoints**:
   - `fetchengine/pipeline_utils.py:19-25`: `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`, `https://sh.dataspace.copernicus.eu/process/v1`, and `https://sh.dataspace.copernicus.eu/catalog/v1/search`.
   - `fetchengine/cdse_fetch.py:37-47`: `https://catalogue.dataspace.copernicus.eu/odata/v1/Products` and `https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value`.
   - `RAG-AI-main/scraper/api_scraper.py:27`: `https://api.reliefweb.int/v1/reports` (outdated v1 endpoint).
3. **Hardcoded File System Paths**:
   - `fetchengine/pipeline_utils.py:16`: Hardcoded `Path(__file__).resolve().parent / ".env"`.
   - `Disaster API/src/config.py:14`: Hardcoded `Path(__file__).resolve().parent.parent / ".env"`.
   - `Disaster API/src/server.py:67`: `FETCHENGINE_DIR / "runs"` hardcoded static mount.
4. **Hardcoded Model Names**:
   - `RAG-AI-main/rag/embedder.py:16`: `"all-MiniLM-L6-v2"` hardcoded default.
   - `RAG-AI-main/rag/generator.py:139,144`: `"gemini-1.5-flash"` and `"gpt-4o-mini"` hardcoded fallbacks.
5. **No Leaked Secret Keys**: All test API keys (`tvly-mock-valid-key-for-testing`, `sample_key_00000000000000000000`) are explicitly synthetic mock strings.

### 1.4 Canonical `.env.example` Proposal

A single, unified `.env.example` at the repository root must replace all fragmented configuration files:

```bash
# ==============================================================================
# RAKHSHAK DISASTER INTELLIGENCE PLATFORM — CANONICAL ENVIRONMENT CONFIGURATION
# Copy to .env at workspace root. All services load from this single file.
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. COPERNICUS DATA SPACE ECOSYSTEM (CDSE) / SENTINEL HUB SAR
# ------------------------------------------------------------------------------
# Register OAuth2 client at: https://dataspace.copernicus.eu
CDSE_CLIENT_ID=your_cdse_client_id_here
CDSE_CLIENT_SECRET=your_cdse_client_secret_here

# ------------------------------------------------------------------------------
# 2. DISASTER INTELLIGENCE & SITUATION REPORT APIS
# ------------------------------------------------------------------------------
# Tavily Search API key (https://tavily.com)
TAVILY_API_KEY=your_tavily_api_key_here
TAVILY_SEARCH_DEPTH=advanced
TAVILY_MAX_RESULTS=10
TAVILY_TIMEOUT_SEC=30

# NASA FIRMS Active Fire Map Key (https://firms.modaps.eosdis.nasa.gov/api/map_key)
FIRMS_MAP_KEY=your_firms_map_key_here
FIRMS_SOURCE=VIIRS_SNPP_NRT
FIRMS_TIMEOUT_SEC=30

# UN OCHA ReliefWeb API v2 (Register approved appname: https://apidoc.reliefweb.int/parameters#appname)
RELIEFWEB_APPNAME=your_registered_appname_here
RELIEFWEB_BASE_URL=https://api.reliefweb.int/v2/reports
RELIEFWEB_TIMEOUT_SEC=30
RELIEFWEB_LIMIT=10

# USGS Earthquake Catalog API (Public)
USGS_BASE_URL=https://earthquake.usgs.gov/fdsnws/event/1/query
USGS_TIMEOUT_SEC=30

# GDACS Multi-Hazard Alerts (Public)
GDACS_BASE_URL=https://www.gdacs.org/gdacsapi/api/events/geteventlist/search
GDACS_EVENT_DATA_URL=https://www.gdacs.org/gdacsapi/api/events/geteventdata
GDACS_TIMEOUT_SEC=30

# ------------------------------------------------------------------------------
# 3. LLM GENERATION & RAG REASONING
# ------------------------------------------------------------------------------
# Google Gemini API Key (ai.google.dev)
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# OpenAI API Key (platform.openai.com)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# Local Vector Store & Embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu
CHROMA_PERSIST_DIR=./data/chroma_db

# ------------------------------------------------------------------------------
# 4. SERVER PORTS & APPLICATION PATHS
# ------------------------------------------------------------------------------
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_PORT=5173
RUNS_STORAGE_DIR=./fetchengine/runs
LOG_LEVEL=INFO
```

#### Configuration Rename & Migration Map

| Old Variable / Path | Canonical Variable Name | Impacted Source Code Files Requiring Edits |
| :--- | :--- | :--- |
| `CDSE_USER`, `CDSE_PASS` | *Deprecated / Removed* | `fetchengine/cdse_fetch.py:55-56` (Delete or refactor to OAuth2). |
| `TAVILY_TIMEOUT` | `TAVILY_TIMEOUT_SEC` | `Disaster API/src/config.py:62` |
| `USGS_TIMEOUT` | `USGS_TIMEOUT_SEC` | `Disaster API/src/config.py:127` |
| `GDACS_TIMEOUT` | `GDACS_TIMEOUT_SEC` | `Disaster API/src/config.py:178` |
| `RELIEFWEB_TIMEOUT` | `RELIEFWEB_TIMEOUT_SEC` | `Disaster API/src/config.py:230` |
| `FIRMS_TIMEOUT` | `FIRMS_TIMEOUT_SEC` | `Disaster API/src/config.py:315` |
| `api.reliefweb.int/v1/reports` | `RELIEFWEB_BASE_URL` | `RAG-AI-main/scraper/api_scraper.py:27` |
| Isolated `.env` path resolution | Workspace Root `.env` | `Disaster API/src/config.py:15`, `fetchengine/pipeline_utils.py:16`, `RAG-AI-main/rag/pipeline.py:128` |

### 1.5 Port Clashes, Duplicate Servers & Script Discrepancies

- **Port Allocations**: The backend runs on `8000` and Vite dev server runs on `5173`. No port collision exists between frontend and backend.
- **RAG-AI Server**: RAG-AI has no separate port or server process; it provides `create_ai_router()` designed for FastAPI mounting and CLI scripts (`main.py`, `query_rag.py`).
- **`start_all.bat` vs `start_all.ps1`**:
  - `start_all.bat:17` runs `start "Rakhshak Backend Server" cmd /k "py run_server.py"`: spawns a dedicated console window that remains open if the backend crashes.
  - `start_all.ps1:15` runs `Start-Process "py" -ArgumentList "run_server.py"`: launches Python detached without terminal error logging; if an unhandled exception occurs, the window closes instantaneously with no stack trace visible.
  - Neither script launches RAG-AI, verifies Python virtualenv packages, or runs `npm install` in `frontend`.

---

## 2. Architecture and Subsystem Overlap

### 2.1 Current Architecture Flow

```
[ Web Browser ]
      │  (HTTP :5173)
      ▼
[ Vite Dev Server (Proxy :5173 -> :8000) ]
      │  (/api/*, /runs/*)
      ▼
[ FastAPI Backend (:8000 - src/server.py) ]
      ├── GET /api/health ─────────► [ Hardcoded "healthy" status ]
      ├── POST /api/disaster/query ─► [ DisasterPipeline (Disaster API/src/pipeline.py) ]
      │                                     ├── TavilySearchService (News/Web)
      │                                     ├── USGSClient (Earthquake Catalog)
      │                                     ├── GDACSClient (Alerts & GLIDE)
      │                                     ├── ReliefWebClient (v2 SitReps)
      │                                     └── FIRMSClient (NASA Thermal Hotspots)
      │                                     └── Regex Cross-Verification (verification.py)
      ├── GET /api/copernicus/runs ──► [ Reads fetchengine/runs/ from Disk ]
      ├── GET /api/copernicus/status ─► [ Reads metadata.json from Disk ]
      └── POST /api/copernicus/fetch ─► [ cdse_bridge.py -> Writes QUEUED metadata, NO worker ]

============================== COMPLETELY ISOLATED ==============================

[ RAG-AI-main (Standalone Subsystem) ]
      ├── main.py / scripts/run_scraper.py ──► [ Scraper Pipeline ]
      │                                              ├── Trafilatura HTML Scraper
      │                                              ├── Feedparser RSS Scraper
      │                                              ├── ReliefWeb API v1 Client (Duplicate)
      │                                              └── Tavily Scraper (Duplicate)
      ├── processor/cleaner.py & deduplicator.py ──► [ SHA-256 JSONL Processor ]
      ├── rag/embedder.py (sentence-transformers) ──► [ ChromaDB Vector Store ]
      ├── rag/retriever.py ────────────────────────► [ Hybrid Vector + Keyword Retrieval ]
      ├── rag/satellite_adapter.py ────────────────► [ Expects unproduced impact schema ]
      └── rag/generator.py (Gemini / OpenAI) ──────► [ Grounded LLM Answers with [SOURCE N] ]
```

### 2.2 Subsystem Overlaps

1. **Duplicate Web Search Clients**:
   - `Disaster API/src/tavily_client.py` implements a Tavily client with domain credibility filtering and query formatting.
   - `RAG-AI-main/scraper/tavily_scraper.py` implements a separate Tavily search wrapper doing raw URL harvesting.
2. **Duplicate ReliefWeb API Clients**:
   - `Disaster API/src/clients/reliefweb_client.py` uses ReliefWeb API **v2** (`https://api.reliefweb.int/v2/reports`) with query filtering by ISO3 country, disaster type, and dates.
   - `RAG-AI-main/scraper/api_scraper.py:27` queries ReliefWeb API **v1** (`https://api.reliefweb.int/v1/reports`), creating endpoint divergence and conflicting schemas.
3. **Duplicate Scraper / Extraction Pipelines**:
   - `Disaster API/src/verification.py` cleans text, strips boilerplate, and identifies news wires using regex.
   - `RAG-AI-main/processor/cleaner.py` and `RAG-AI-main/scraper/base_scraper.py` clean text using Trafilatura and custom regex rules.
4. **Duplicate Data Schemas**:
   - `Disaster API/src/models.py:UnifiedIncidentReport` models disaster events with sensor coordinates, GLIDE IDs, and claim lists.
   - `RAG-AI-main/processor/validator.py:DisasterDocument` models documents with `content_hash`, `hazard_types`, and `coordinates`.
   - `RAG-AI-main/rag/api_schemas.py:DisasterQueryResponse` defines yet a third format for Q&A answers.
5. **Conflicting Dependencies & Package Pins**:
   - `Disaster API/requirements.txt`: Lightweight (`tavily-python>=0.5.0`, `python-dotenv>=1.0.0`, `pydantic>=2.0.0`, `pytest>=8.0.0`).
   - `RAG-AI-main/requirements.txt`: Heavy ML stack (`sentence-transformers>=2.7.0`, `chromadb>=0.5.0`, `trafilatura>=1.8.0`, `feedparser>=6.0.10`, `google-generativeai>=0.7.0`, `openai>=1.35.0`).
   - Neither requirements file lists `fastapi` or `uvicorn` (which are installed in the global Python environment but omitted from version control pins).

### 2.3 Target Unified Architecture Flow

```
[ User Query / Web Dashboard ]
              │
              ▼
    [ Unified FastAPI Server (:8000) ]
              │
    ┌─────────┴────────────────────────────────────────┐
    ▼                                                  ▼
[ /api/disaster/query ]                     [ /api/copernicus/fetch ]
    │                                                  │
    ├─► USGS / GDACS / FIRMS / ReliefWeb              ├─► CDSE STAC Discovery (01_catalog.py)
    │   (Multi-Source Fetch)                           ├─► Sentinel Hub Process API (02_fetch.py)
    │                                                  ├─► Raster Validation (03_validate.py)
    └─► Tavily Web News Fetch                          ├─► Radiometric Change Detection (04_process.py)
              │                                        ├─► Visual Synthesis (05_visualize.py)
              │                                        └─► Structured Observation JSON
              │                                                        │
              └──────────────────────┬─────────────────────────────────┘
                                     ▼
                      [ RAG-AI Ingestion & Grounding ]
                                     │
                                     ├─► Dynamic Indexing into ChromaDB
                                     ├─► SatelliteEvidenceAdapter (SAR Inundation + Provenance)
                                     ├─► Cross-Corroboration (Sensor vs News vs Satellite)
                                     └─► Grounded LLM Generation (Strict Citations)
                                     │
                                     ▼
              [ Unified JSON Response with Source Attribution ]
                                     │
                                     ▼
                        [ Leaflet React Dashboard ]
```

### 2.4 Integration Points & Action Plan

| Component / File | Action | Technical Rationale |
| :--- | :--- | :--- |
| `RAG-AI-main/rag/fastapi_service.py` | **MOUNT** into `Disaster API/src/server.py` | Exposes `POST /api/ai/query` and `GET /api/ai/health` on port 8000. |
| `RAG-AI-main/scraper/api_scraper.py` | **DELETE** | Redundant with `Disaster API/src/clients/reliefweb_client.py` (which already uses v2 API). |
| `RAG-AI-main/scraper/tavily_scraper.py` | **DELETE** | Redundant with `Disaster API/src/tavily_client.py`. |
| `fetchengine/cdse_fetch.py` & `cdse_process.py` | **DELETE** | Obsolete OData prototypes superseded by `01_catalog.py` through `05_visualize.py`. |
| `Disaster API/src/server.py` | **MERGE** | Add background task queue (`BackgroundTasks` or Redis worker) to `trigger_cdse_pipeline`. |
| `frontend/src/utils/mergeBaseline.js` | **REFACTOR** | Stop overriding live API responses with hardcoded mock numbers. |

---

## 3. Demo vs Live Data Matrix

### 3.1 UI Panel Data Sources & Fallback Analysis

| UI Element / Panel | Displayed Content | Trigger Condition for Fallback | Data Status | True Data Origin & Honesty Assessment |
| :--- | :--- | :--- | :---: | :--- |
| **System Status Badge** (`Header.jsx:30`) | `"LIVE API (ONLINE)"` | None (Always active if port 8000 responds) | **HARDCODED** | `server.py:143` unconditionally returns `"status": "healthy"`. Gives illusion of full connectivity even when CDSE, Tavily, and FIRMS keys are missing. |
| **Severity Score Pill** (`IncidentHeaderCard.jsx:9`) | `"2.0 / 3.0"` | Missing `liveData.severity_score` | **HARDCODED** | `mergeBaseline.js:105` evaluates `baseMock.severity_score` before `liveData.gdacs?.alert_score`. Mock `2.0` always overrides live score. |
| **GLIDE Number Badge** (`IncidentHeaderCard.jsx:42`) | `"FL-2018-000134-IND"` | Missing live GDACS GLIDE | **PRECOMPUTED** | Hardcoded in `mockIncidents.js:14`. Only replaced if live GDACS match contains a valid GLIDE string. |
| **GDACS Feed Tab** (`FeedsCard.jsx:77`) | Alert Level, Exposure, Centroid | GDACS query returns empty / error | **LIVE / FALLBACK** | Queries live GDACS search API. If no event matches date window, displays mock GDACS event. Correctly shows alert details when live. |
| **USGS Feed Tab** (`FeedsCard.jsx:87`) | Earthquake Magnitude & Coordinates | USGS returns 0 events | **LIVE / FALLBACK** | Queries live USGS FDSNWS API. Live for Turkey/Kahramanmaras; falls back to mock for non-seismic queries. |
| **ReliefWeb SitRep Tab** (`FeedsCard.jsx:97`) | Humanitarian Reports & Bulletins | `RELIEFWEB_APPNAME` unconfigured / 403 error | **FALLBACK (SILENT)** | Live API returns HTTP 403 Forbidden. `mergeBaseline.js:61-67` injects `mockIncidents.js` reports with `[SAMPLE DEMO]` prefix. |
| **NASA FIRMS Tab** (`FeedsCard.jsx:107`) | Thermal Hotspot Detections | `FIRMS_MAP_KEY` unconfigured | **FALLBACK (SILENT)** | API unconfigured; falls back to 50 mock detections from California Lightning Complex August 2020. |
| **Tavily Intelligence Tab** (`FeedsCard.jsx:67`) | News Headlines & Synthesized Summary | `TAVILY_API_KEY` missing | **FALLBACK (SILENT)** | Falls back to pre-written summaries in `mockIncidents.js` with `[SAMPLE DEMO]` tags. |
| **Claims Table** (`FeedsCard.jsx`) | Rainfall, Displacement, Casualty tolls | Tavily unconfigured | **FALLBACK** | Pre-written claims in `mockIncidents.js:20-47`. |
| **SAR Stepper Status** (`CopernicusStepperCard.jsx:245`) | `"ALL 5 STAGES VERIFIED"` | Precomputed run exists on disk | **PRECOMPUTED** | Read directly from `metadata.json` on disk. Does not run real-time pipeline computation. |
| **SAR Image Previews** (`SatelliteComparisonCard.jsx`) | Pre/Post VV dB, Difference, Histogram | Triggered by active run selection | **PRECOMPUTED** | Served from static files in `fetchengine/runs/kerala_2018-08-10/previews/`. |
| **Candidate Vector Overlays** (`MapCard.jsx:125`) | Flood Polygon Clusters on Leaflet map | Run ID active | **PRECOMPUTED** | Served from `fetchengine/runs/<run_id>/candidates.geojson`. |

### 3.2 Analysis of Silent Fallbacks & Illusions of Liveness

1. **The "ALL 5 STAGES VERIFIED" Illusion**:
   - In `CopernicusStepperCard.jsx:245`, the status badge displays `"ALL 5 STAGES VERIFIED"` based strictly on `isComplete = runData?.is_complete` (`cdse_bridge.py:264`).
   - When the user clicks **"Verify Pipeline Execution"** (`handleTriggerFetch`), the backend checks if `target_dir.exists() and not force` (`cdse_bridge.py:473`). If found, it instantly returns the cached run status without validating credentials or contacting Copernicus.
2. **The "LIVE API (ONLINE)" Illusion**:
   - In `server.py:125-177`, `GET /api/health` hardcodes `"status": "healthy"`. Even when every upstream credential is missing and all subsystems report `unconfigured` or `failed`, the HTTP status code is 200 and the root status string is `healthy`. The UI interprets this as full operational readiness (`Header.jsx:30`).
3. **The Severity Score Override Bug**:
   - In `frontend/src/utils/mergeBaseline.js:105`:
     ```javascript
     severity_score: liveData.severity_score ?? baseMock.severity_score ?? liveData.gdacs?.alert_score,
     ```
   - Because `liveData.severity_score` is never set on the root Pydantic report, JavaScript nullish coalescing falls back to `baseMock.severity_score` (hardcoded `2.0` in `mockIncidents.js:17`), completely ignoring the live GDACS alert score (`liveData.gdacs?.alert_score`).

---

## 4. Scientific Rigor Findings (SAR Flood & Change Detection)

| # | Scientific Issue | Evidence (File:Line) | Severity | Technical Assessment & Concrete Fix |
| :-: | :--- | :--- | :-: | :--- |
| **1** | **Ellipsoidal Calibration vs Radiometric Terrain Flattening (RTC)** | `fetchengine/02_fetch.py:96`<br>`cdse_process.py:48-67` | **CRITICAL** | `02_fetch.py` requests `"backCoeff": "SIGMA0_ELLIPSOID"`. Over hilly or mountainous terrain (such as the Western Ghats catchment in Kerala), ellipsoidal sigma0 suffers severe radiometric distortion due to local incidence angle variations. Slopes facing the radar appear falsely bright, while slopes facing away appear dark and mimic water inundation.<br>**Fix**: Change Sentinel Hub Process API request parameter to `"backCoeff": "GAMMA0_TERRAIN"` with `"demInstance": "COPERNICUS_30"` to produce true Radiometric Terrain Corrected (RTC) gamma0 backscatter. |
| **2** | **Heuristic Permanent Water Masking vs JRC / WorldCover Surface Water** | `fetchengine/04_process.py:124` | **CRITICAL** | Permanent water is identified via heuristic: `(pre_vv_db < -16.0) & (pre_vh_db < -23.0)`. If pre-event water surfaces were wind-roughened or contained floating vegetation, backscatter exceeds -16 dB, causing rivers, reservoirs, and coastal lagoons to be classified as "new flood".<br>**Fix**: Integrate the JRC Global Surface Water (GSW) transition layer or ESA WorldCover (Class 80: Permanent Water Bodies) via Sentinel Hub Process API to mask out multi-year permanent water baselines before computing flood delta. |
| **3** | **No Height Above Nearest Drainage (HAND) or Slope Mask** | `fetchengine/04_process.py:109-130` | **HIGH** | The pipeline applies no topographic constraint. Hilltop depressions, dark agricultural fields on plateaus, and radar shadows on mountain ridges with $\Delta\text{VV} < -3.25\text{ dB}$ are vectorized as flood clusters.<br>**Fix**: Fetch MERIT-DEM or Copernicus 30m DEM slope and HAND raster. Exclude all candidate pixels where $\text{Slope} > 5^\circ$ or $\text{HAND} > 15\text{ m}$. |
| **4** | **Unimodal Adaptive Standard Deviation Thresholding Failure Mode** | `fetchengine/04_process.py:150-152` | **HIGH** | Threshold is computed as $\mu_{\Delta\text{VV}} - 1.5 \cdot \sigma_{\Delta\text{VV}}$, then clamped to $[-6.0, -2.0]\text{ dB}$. During catastrophic widespread inundation, the entire backscatter histogram shifts negative and widens $\sigma$, driving the threshold to $-5.0\text{ dB}$ or beyond and omitting large expanses of real standing water. Conversely, dry soil moistening can cause $-3.25\text{ dB}$ drops without water presence.<br>**Fix**: Implement dual-condition thresholding: $\Delta\text{VV} < \text{threshold}_{\text{delta}}$ **AND** $\text{post\_vv\_db} < -15.0\text{ dB}$ (physical ceiling for smooth water backscatter). Apply Kittler-Illingworth or Bimodal Otsu on the low-backscatter mode. |
| **5** | **Discarding Dual-Polarization VH Channel in Change Detection** | `fetchengine/04_process.py:119,159` | **MEDIUM** | Both VV and VH bands are fetched and calibrated in Stage 2, but Stage 4 computes `raw_mask = (delta_vv < threshold) & eligible`. Cross-polarized VH backscatter is significantly more sensitive to volume scattering from vegetation and less sensitive to wind-induced water surface roughness.<br>**Fix**: Formulate dual-polarization flood index: $\text{DPI} = \Delta\text{VV} + 0.5 \cdot \Delta\text{VH}$ or use VH to filter out wind-roughened false positives over open water. |
| **6** | **Absence of Orbit Ephemeris Validation (POE vs RES)** | `fetchengine/01_catalog.py:100-150` | **MEDIUM** | Stage 1 verifies scene acquisition times and relative orbits, but does not verify whether Precise Orbit Ephemerides (POEORB, available ~20 days post-acquisition) or Restituted orbits (RESORB) are applied by Sentinel Hub. While Sentinel Hub handles state vectors internally, residual geocoding shift (~5-10 m) between pre- and post-scenes can create edge artifacts along narrow riverbanks.<br>**Fix**: In Stage 3 (`03_validate.py`), compute cross-correlation over urban non-changing control points to verify sub-pixel raster registration before differencing. |
| **7** | **Zero Ground-Truth Validation Metrics or Confusion Matrices** | `fetchengine/04_process.py`<br>`fetchengine/run_pipeline.py:98-115` | **MEDIUM** | Total flooded area is calculated as `40.709 km²` (4,070.9 ha), but the system provides zero comparison against official emergency activations (e.g., Copernicus EMS Rapid Mapping Activation `EMSR301: Flood in Kerala, India`). No IoU (Intersection over Union), Cohen's Kappa, or Precision/Recall metrics are calculated.<br>**Fix**: Create a validation benchmarking script (`scripts/validate_ground_truth.py`) that ingests official EMS vector delineations and computes IoU and F1-score against `candidates.geojson`. |
| **8** | **Arbitrary Severity Score Formula** | `frontend/src/data/mockIncidents.js:17`<br>`mergeBaseline.js:105` | **HIGH** | The UI displays "Severity Score: 2.0 / 3.0" for Kerala and "1.5 / 3.0" for Lucknow. This number is hardcoded in frontend JavaScript. In the backend, GDACS alert scores exist, but the pipeline has no documented formula converting SAR flooded area or population exposure into a normalized 0.0–3.0 severity index.<br>**Fix**: Define an explicit, reproducible severity formula: $\text{Score} = \min\left(3.0, \; 0.5 \cdot \log_{10}(\text{Area}_{\text{km}^2}) + 0.3 \cdot \log_{10}(\text{Population}) + 0.2 \cdot \text{GDACS}_{\text{Score}}\right)$. Document this formula in `models.py`. |
| **9** | **Lack of Pixel-Level Uncertainty or Confidence Metrics** | `fetchengine/04_process.py:169-175` | **LOW** | `change_mask.tif` is binary (0 or 1). Pixels with $\Delta\text{VV} = -3.26\text{ dB}$ (just below threshold) are treated with identical certainty as pixels with $\Delta\text{VV} = -10.0\text{ dB}$.<br>**Fix**: Export a floating-point probability or confidence raster ($0.0$ to $1.0$) based on sigmoid distance from the threshold: $P(\text{flood}) = \frac{1}{1 + e^{-(\text{threshold} - \Delta\text{VV}) / \sigma}}$. |
| **10** | **Metric UTM Area Formulation vs Ellipsoidal Distortion** | `fetchengine/04_process.py:195-213` | **LOW** | Formula: `area_m2 = poly.area` on EPSG:32643 UTM projection. Converted via `area_ha = area_m2 / 10000.0` and `area_km2 = area_m2 / 1_000_000.0`. Mathematics and unit conversions are accurate, but UTM grid scale factor distortion ($k_0 = 0.9996$ at central meridian) is uncorrected.<br>**Fix**: Acceptable for emergency regional response ($< 0.1\%$ distortion error), but note in `report.md` that areas represent planar projected surface area. |

---

## 5. AI / RAG Quality & Integration Contract

### 5.1 RAG-AI-main Technical Assessment

| Subsystem Component | Current Implementation | Capabilities & Strengths | Weaknesses & Vulnerabilities |
| :--- | :--- | :--- | :--- |
| **Ingestion & Scraper** | Trafilatura, Feedparser, Requests in `RAG-AI-main/scraper/` | Clean article extraction; respects `robots.txt`; rate limiting (1.5 s sleep). | Relies on outdated ReliefWeb v1 API; cannot execute client-side JavaScript on modern news portals. |
| **Validation & Cleaning** | Pydantic `DisasterDocument` in `processor/validator.py` | Rigorous schema; automatic hazard detection; coordinate validation; SHA-256 content deduplication. | Regular expressions for region extraction are basic dictionary matches; cannot resolve ambiguous place names. |
| **Chunking** | Sliding window in `rag/chunker.py` | Sentence-aware boundary detection; configurable size (512 tokens) and overlap (64 tokens). | Does not preserve markdown table structures or GeoJSON coordinate metadata inside chunks. |
| **Embeddings** | `sentence-transformers` (`all-MiniLM-L6-v2`) in `rag/embedder.py` | 100% offline, local execution; no API fees; compact 90 MB model. | CPU inference adds 1.5–3 s latency on cold start; missing package in active environment. |
| **Vector Store** | ChromaDB (`data/chroma_db`) in `rag/vector_store.py` | Persistent local SQLite/DuckDB index; metadata filtering by region and hazard. | Empty on fresh clone; index must be manually built using `build_index.py`. |
| **Retriever** | Hybrid search in `rag/retriever.py` | Cosine similarity combined with domain keyword boost (+0.15 for SAR terms). | Boost weights are hardcoded heuristics rather than learned reciprocal rank fusion (RRF). |
| **LLM Generator** | `rag/generator.py` (Gemini, OpenAI, Offline) | Strict anti-hallucination prompt; enforces `[SOURCE N]` citations; deterministic offline fallback. | Does not stream responses; prompt template lacks chain-of-thought verification. |
| **Satellite Adapter** | `SatelliteEvidenceAdapter` in `rag/satellite_adapter.py` | Differentiates verified radar instruments from demo simulations. | Schema expects impact parameters (`affectedRoadKm`, `priority_zones`) that `fetchengine` does not compute. |

### 5.2 Hallucination Protection & Conflict Resolution

In `RAG-AI-main/rag/generator.py:34-47`, the prompt instructs:
```text
3. If the documents and satellite data do not contain enough information to answer confidently,
   say so clearly ("Insufficient evidence in provided data") — do NOT extrapolate, invent coordinates,
   speculate on damage extents, or guess casualty counts.
4. When source documents present conflicting or varying reports (e.g. differing fatality counts...),
   you must explicitly highlight the disagreement, report the differing figures with their respective
   source citations, and NOT arbitrarily choose or guess which one is correct.
```
This is a sound anti-hallucination policy. Furthermore, `RAG-AI-main/rag/retriever.py` extracts disaster events and timestamps, and formats uncertainty notices if relevance scores fall below `0.20`.

### 5.3 SAR Output to RAG Interface Contract

To connect `fetchengine` outputs directly into `RAG-AI` without synthetic mocks, the following shared JSON schema contract must be implemented:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CopernicusSARObservation",
  "type": "object",
  "required": [
    "run_id",
    "event_date",
    "aoi_bbox",
    "sensor",
    "relative_orbit",
    "orbit_direction",
    "pre_scene_id",
    "post_scene_id",
    "flooded_area_km2",
    "flooded_area_ha",
    "threshold_db",
    "candidate_clusters_count"
  ],
  "properties": {
    "run_id": { "type": "string" },
    "event_date": { "type": "string", "format": "date" },
    "aoi_bbox": {
      "type": "array",
      "items": { "type": "number" },
      "minItems": 4,
      "maxItems": 4
    },
    "sensor": { "type": "string", "enum": ["Sentinel-1A", "Sentinel-1B", "Sentinel-1C", "Sentinel-1D"] },
    "relative_orbit": { "type": "integer" },
    "orbit_direction": { "type": "string", "enum": ["ASCENDING", "DESCENDING"] },
    "pre_scene_id": { "type": "string" },
    "post_scene_id": { "type": "string" },
    "flooded_area_km2": { "type": "number" },
    "flooded_area_ha": { "type": "number" },
    "threshold_db": { "type": "number" },
    "candidate_clusters_count": { "type": "integer" },
    "permanent_water_excluded_ha": { "type": "number" },
    "geojson_candidates_url": { "type": "string" }
  }
}
```

---

## 6. Automation & Operational Pipeline Design

### 6.1 Current Manual Friction Points
1. To run a new disaster AOI, an engineer must manually create or edit `fetchengine/config.yaml`.
2. The engineer must manually run five CLI scripts sequentially (`01_catalog.py`, `02_fetch.py`, `03_validate.py`, `04_process.py`, `05_visualize.py`).
3. The engineer must manually run `build_index.py` in `RAG-AI-main` to vectorize new situation reports.
4. The backend trigger endpoint (`/api/copernicus/fetch`) writes a `metadata.json` with status `QUEUED`, but executes no code.

### 6.2 Target Automated Pipeline Architecture

```
[ Scheduled Trigger: Every 15 min ]
              │
              ▼
    [ Polling Ingestion Worker ]
              │  (Checks GDACS RSS & ReliefWeb API for Red/Orange Flood Alerts)
              ▼
    [ AOI & Parameter Derivation ]
              │  Extracts Bounding Box, Event Date, Country ISO3
              ▼
    [ Idempotency & Cache Check ]
              │  Does run_id (e.g. 'kerala_2026-10-21') exist in database/runs?
              ├── YES ──► Skip or update existing run.
              └── NO  ──► Enqueue SAR Pipeline Job
                                │
                                ▼
              [ Celery / Asyncio Worker Task ]
                                │
                                ├─► 1. STAC Discovery (Selects same-orbit pre/post pair)
                                ├─► 2. Process API Fetch (Orthorectified UTM GeoTIFFs)
                                ├─► 3. Raster Validation (Overlap & nodata checks)
                                ├─► 4. Radiometric Differencing & RTC Change Mask
                                ├─► 5. GeoJSON Vectorization & Preview Generation
                                └─► 6. Update metadata.json (Progress: 20% -> 100%)
                                                │
                                                ▼
                                [ RAG Ingestion Trigger ]
                                                │
                                                ├─► Scrapes Situation Reports & GDACS Summary
                                                ├─► Indexes into ChromaDB with metadata tags
                                                └─► Pre-generates Grounded Situation Assessment
                                                                │
                                                                ▼
                                                [ Published to Live Dashboard ]
```

### 6.3 State & Status Progression Model
- **`QUEUED`**: AOI received, scene search pending.
- **`CATALOGING`**: CDSE STAC search running, evaluating orbit footprint overlap.
- **`FETCHING`**: Sentinel Hub Process API downloading orthorectified GeoTIFFs.
- **`PROCESSING`**: Dual-polarization change detection, permanent water masking, vectorization.
- **`VISUALIZING`**: Preview generation, summary panel rendering, markdown report creation.
- **`COMPLETED`**: All rasters, vector polygons, and preview PNGs validated and reachable.
- **`FAILED`**: Explicit failure record with error traceback and stage identifier.

---

## 7. Security and Code Hygiene Findings

1. **Permissive CORS with Credentials**:
   - `Disaster API/src/server.py:57-60`:
     ```python
     app.add_middleware(
         CORSMiddleware,
         allow_origins=["*"],
         allow_credentials=True,
         allow_methods=["*"],
         allow_headers=["*"],
     )
     ```
   - Specifying `allow_origins=["*"]` alongside `allow_credentials=True` violates web security standards and browser policies.
   - **Fix**: Restrict origins to `["http://localhost:5173", "http://127.0.0.1:5173"]` or environment-configured domain origins.
2. **Unauthenticated Dangerous Endpoints**:
   - `POST /api/copernicus/fetch` allows arbitrary internet clients to trigger heavy raster disk writes and network calls without authentication or rate limiting.
   - **Fix**: Protect administrative and pipeline trigger endpoints using API key bearer tokens or JWT authentication.
3. **Unvalidated Bounding Box Inputs & Denial-of-Service Risk**:
   - `server.py:86,97` validates `bbox` only as `List[float]` of length 4.
   - No validation ensures $-180 \le \text{lon} \le 180$, $-90 \le \text{lat} \le 90$, $\text{west} < \text{east}$, or $\text{south} < \text{north}$.
   - A client could submit a global bounding box `[-180, -90, 180, 90]`, crashing memory or exhausting Sentinel Hub processing units.
   - **Fix**: Add Pydantic validator enforcing coordinate boundaries and capping maximum AOI area (e.g., $\le 10,000\text{ km}^2$).
4. **Information Disclosure in Exception Messages**:
   - `server.py:210`: `detail=f"Query execution error: {str(exc)}"` directly exposes internal Python exception messages to HTTP clients.
   - **Fix**: Log detailed tracebacks internally; return sanitized error messages to the client.
5. **Untracked Module in Git**:
   - `git status` reveals `RAG-AI-main/` is completely untracked. Any changes to RAG-AI risk being lost without formal version control tracking.
   - **Fix**: Add `RAG-AI-main/` to git tracking while ensuring `RAG-AI-main/data/chroma_db/` and local test logs are excluded in root `.gitignore`.

---

## 8. Prioritized Engineering Roadmap

### Phase P0: Core Unification & Working Live Demo (Effort: ~3–4 Days)
*Blocks an authentic, integrated end-to-end demo.*

| Task | Files to Touch | Estimated Effort |
| :--- | :--- | :--- |
| **P0.1: Mount RAG-AI Router into FastAPI** | `Disaster API/src/server.py`<br>`RAG-AI-main/rag/fastapi_service.py` | 0.5 Day |
| **P0.2: Implement Single Canonical `.env` Loader** | `Disaster API/src/config.py`<br>`fetchengine/pipeline_utils.py`<br>`RAG-AI-main/rag/pipeline.py` | 0.5 Day |
| **P0.3: Fix Frontend Mock Severity Score Override** | `frontend/src/utils/mergeBaseline.js`<br>`frontend/src/components/IncidentHeaderCard.jsx` | 0.5 Day |
| **P0.4: Bridge Live Fetchengine Metadata into RAG** | `fetchengine/cdse_bridge.py`<br>`RAG-AI-main/rag/satellite_adapter.py` | 1.0 Day |
| **P0.5: Add Interactive AI Q&A Panel in Frontend** | `frontend/src/App.jsx`<br>`frontend/src/components/FeedsCard.jsx` | 1.0 Day |

### Phase P1: Scientific Defensibility & Live Pipelines (Effort: ~4–5 Days)
*Eliminates false alarms and enables real live data generation.*

| Task | Files to Touch | Estimated Effort |
| :--- | :--- | :--- |
| **P1.1: Radiometric Terrain Correction (RTC)** | `fetchengine/02_fetch.py:96`<br>`fetchengine/cdse_process.py:53` | 1.0 Day |
| **P1.2: Permanent Water Masking (JRC GSW / WorldCover)** | `fetchengine/04_process.py:121-131` | 1.0 Day |
| **P1.3: Dual-Condition Flood Thresholding (ΔVV + Absolute Floor)** | `fetchengine/04_process.py:140-165` | 1.0 Day |
| **P1.4: Real Background Pipeline Worker for `/fetch`** | `Disaster API/src/server.py:355-368`<br>`fetchengine/cdse_bridge.py:458-515` | 1.5 Days |

### Phase P2: Full Automation, Verification & Production Hardening (Effort: ~5–6 Days)
*Autonomous operation, ground truth benchmarking, and security.*

| Task | Files to Touch | Estimated Effort |
| :--- | :--- | :--- |
| **P2.1: Automated GDACS Alert Polling Trigger** | New `scripts/auto_monitor.py`<br>`Disaster API/src/pipeline.py` | 2.0 Days |
| **P2.2: Copernicus EMS Ground Truth Benchmark Script** | New `scripts/validate_ground_truth.py` | 1.5 Days |
| **P2.3: Security Hardening (CORS, AOI Limits, Auth)** | `Disaster API/src/server.py:54-61,85-99` | 1.0 Day |
| **P2.4: Unified Dependency Management & Dockerization** | `requirements.txt`<br>`Dockerfile`<br>`docker-compose.yml` | 1.0 Day |

---

## 9. Open Questions & Verification Boundaries

### 9.1 Open Questions for the Development Team

1. **Copernicus CDSE Credentials**: Are the team's CDSE credentials provisioned for Sentinel Hub Process API (OAuth2 `client_credentials`) or standard Copernicus OData portal access?
2. **ReliefWeb Appname Registration**: Has an official appname been requested and approved via `https://apidoc.reliefweb.int/parameters#appname`? (Without an approved appname, all live ReliefWeb calls return HTTP 403 Forbidden).
3. **LLM Deployment Target**: For the integrated platform, should grounded generation default to **Google Gemini 1.5 Flash** (via `GOOGLE_API_KEY`), **OpenAI GPT-4o-mini**, or a local Ollama/offline fallback?
4. **Target Deployment Infrastructure**: Will the combined platform be deployed to a cloud VM with GPU acceleration, or is it intended to run locally on developer workstations?
5. **AOI Size Limits**: What is the maximum AOI bounding box area supported before Sentinel Hub Process API credit usage must be capped?

### 9.2 Verification Boundaries

- **`C:\Users\Sarvesh Pillai\Videos\RAG-AI-main` (External Path)**: This external directory outside the workspace was not directly accessible due to IDE workspace boundary policies. All code analysis was conducted directly on `c:\Users\Sarvesh Pillai\Videos\bhumi-deploy-ready\Disaster-API-Check\RAG-AI-main\`.
- **Live Upstream APIs**: In compliance with the READ-ONLY mandate and zero-cost constraints, no paid or rate-limited API calls (Tavily, NASA FIRMS, CDSE Process API downloads) were initiated. Subsystem connectivity was verified using local test suites, cached unit fixtures, and mock evaluation.
