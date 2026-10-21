# Rakhshak Refactor & Migration Log

**Platform:** Disaster Intelligence & Copernicus Sentinel-1 SAR Analysis ("Rakhshak")  
**Branch:** `refactor/unify` (Baseline Snapshot: `pre-refactor-snapshot` commit `8de525e`)  
**Source of Truth:** `AUDIT_REPORT.md` (Sections 1, 2, 3, 7)  

---

## Stage 0 — Baseline & Move Plan

### 1. Baseline Test Suite Execution

All existing test suites were executed on the unmodified codebase before any moves or edits.

| Test Suite | Command | Total Collected | Passed | Failed | Skipped | Errors | Duration | Status / Root Cause |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Disaster API** | `py -m pytest "Disaster API/tests"` | 207 | 205 | 2 | 0 | 0 | 36.58s | **2 Failures**: `test_server.py:342` and `test_server.py:371` fail due to unmocked live ReliefWeb HTTP 403 Forbidden errors (`AccessDeniedHttpException: You are not using an approved appname`). All other 205 unit tests pass. |
| **RAG-AI-main** | `py -m pytest RAG-AI-main/tests` | 91 | 63 | 15 | 10 | 3 | 35.12s | **15 Failures / 3 Errors**: Root cause is missing heavy ML dependencies in active Python environment (`trafilatura`, `feedparser`, `sentence_transformers`, `chromadb`, `google.generativeai`). Pure cleaner, validator, and mocked tests pass (63 passing). |
| **Fetchengine** | *(No separate pytest suite)* | N/A | N/A | N/A | N/A | N/A | N/A | Verified via `scripts/self_audit.py` and precomputed run fixtures in `fetchengine/runs/` (`kerala_2018-08-10`, `lucknow_2026-10-01`). |
| **Frontend** | `npm test` (in `frontend/`) | 4 | 4 | 0 | 0 | 0 | 0.63s | **All 4 tests pass** (ReliefWeb sample baseline preservation and fallback logic in `mergeBaseline.js`). |

---

### 2. Verified Active Services, Endpoints & Ports

Both backend and frontend servers were started and verified with live HTTP queries:

- **Backend Daemon:** `py run_server.py` on `http://127.0.0.1:8000` (PID active)
- **Frontend Dev Server:** `npm run dev -- --port 5173 --host` on `http://localhost:5173` (PID active)
- **Vite Proxy:** Routes `/api/*` and `/runs/*` proxied from `5173` to `8000`.

#### Verified Live Routes

| Method | Endpoint | HTTP Status | Response Summary |
| :--- | :--- | :---: | :--- |
| `GET` | `/api/health` | 200 OK | Overall status `healthy` (hardcoded illusion); lists 7 subsystem statuses and 2 precomputed runs. |
| `GET` | `/docs` / `/openapi.json` | 200 OK | Swagger documentation and OpenAPI schema operational. |
| `POST` | `/api/disaster/query` | 200 OK | Multi-source aggregator query (USGS, GDACS, ReliefWeb, FIRMS, Tavily). |
| `GET` | `/api/disaster/query` | 200 OK | Sample query endpoint. |
| `GET` | `/api/disaster/incidents` | 200 OK | Returns list of sample demo incidents (Kerala 2018, Lucknow 2026). |
| `GET` | `/api/disaster/incidents/{id}` | 200 OK | Returns incident detail by ID. |
| `POST` | `/api/copernicus/catalog` | 200 OK | STAC catalog search proxy. |
| `POST` | `/api/copernicus/fetch` | 200 OK | Registers pipeline run metadata (`QUEUED`), no worker attached. |
| `GET` | `/api/copernicus/runs` | 200 OK | Returns `["kerala_2018-08-10", "lucknow_2026-10-01"]`. |
| `GET` | `/api/copernicus/status/{run_id}` | 200 OK | Returns complete `metadata.json` for specified run. |
| `GET` | `/api/copernicus/runs/{run_id}/images/{img}` | 200 OK | Serves preview rasters (PNG/JPG). |
| `GET` | `/api/copernicus/runs/{run_id}/candidates.geojson` | 200 OK | Serves vectorized flood candidate polygons. |
| `GET` | `/api/copernicus/runs/{run_id}/report` | 200 OK | Serves generated markdown summary report. |
| `GET` | `/runs/*` | 200 OK | Static mount pointing to `fetchengine/runs/`. |
| `GET` | `http://localhost:5173/` | 200 OK | React geospatial dashboard interface. |

---

### 3. Structural Name Problems Flagged

1. **Space in `"Disaster API"` Directory Name:**
   - **Problem:** Python cannot import packages with spaces (`import Disaster API` raises `SyntaxError`). The system currently circumvents this with `sys.path.insert(0, str(DISASTER_API_DIR))` and imports using the generic name `src.*` (`from src.pipeline import ...`), polluting namespace and preventing clean module packaging.
   - **Resolution:** Move `Disaster API/src` to `backend/intel/`.
2. **Hyphen in `"RAG-AI-main"` Directory Name:**
   - **Problem:** Python syntax prohibits hyphens in module/package names (`import RAG-AI-main` raises `SyntaxError: invalid decimal literal`). Scripts in `RAG-AI-main` currently rely on `sys.path.insert(0, str(Path(__file__).resolve().parent))` and direct imports like `from rag.pipeline import ...`.
   - **Resolution:** Move `RAG-AI-main` into `backend/rag/`.
3. **Numbered Scripts in `fetchengine/` (`01_catalog.py` ... `05_visualize.py`):**
   - **Problem:** Python identifiers cannot start with numbers (`import 01_catalog` raises `SyntaxError`). These critical pipeline steps cannot be imported as modules by backend jobs or test runners.
   - **Resolution:** Rename to `catalog.py`, `fetch.py`, `validate.py`, `process.py`, `visualize.py` inside `backend/sar/`, leaving thin backward-compatibility wrapper shims (`01_catalog.py`, etc.) if needed during transition.

---

### 4. Move Plan Table (Old Path -> New Path)

| Existing Path | Target Path | Action | Rationale / Notes |
| :--- | :--- | :---: | :--- |
| **Unified App Root** | | | |
| `run_server.py` | `_deprecated/run_server.py` | Deprecate | Replaced by single root `run.py`. |
| `start_all.bat` | `_deprecated/start_all.bat` | Deprecate | Replaced by cross-platform `run.py`. |
| `start_all.ps1` | `_deprecated/start_all.ps1` | Deprecate | Replaced by cross-platform `run.py`. |
| `.env.example` | `_deprecated/root.env.example` | Deprecate | Replaced by unified root `.env.example`. |
| *(New File)* | `.env.example` | Create | Canonical `.env.example` combining all subsystems (AUDIT_REPORT 1.4). |
| *(New File)* | `requirements.txt` | Create | Merged unified requirements with fastapi, uvicorn, pydantic-settings. |
| *(New File)* | `run.py` | Create | Cross-platform launcher with dep checks, env validation, frontend npm runner. |
| *(New Directory)* | `backend/app/` | Create | Unified FastAPI application core. |
| *(New File)* | `backend/app/main.py` | Create | The ONLY FastAPI application instance, mounting all routers. |
| *(New File)* | `backend/app/config.py` | Create | The ONLY configuration module reading root `.env` via Pydantic Settings. |
| *(New File)* | `backend/app/schemas.py` | Create | Shared contract schemas (`Event`, `Evidence`, `SAROutput`, converters). |
| *(New Directory)* | `backend/app/api/` | Create | FastAPI APIRouters (`disaster.py`, `copernicus.py`, `ai.py`, `health.py`). |
| *(New Directory)* | `backend/jobs/` | Create | Asynchronous job runner & status placeholder (`__init__.py`). |
| **Disaster API (Intel Subsystem)** | | | |
| `Disaster API/src/` | `backend/intel/` | `git mv` | Core disaster intelligence aggregator. |
| `Disaster API/src/clients/` | `backend/intel/clients/` | `git mv` | USGS, GDACS, ReliefWeb, FIRMS clients. |
| `Disaster API/src/config.py` | `backend/intel/config.py` | Refactor | Replaced by/delegates to `backend/app/config.py`. |
| `Disaster API/src/models.py` | `backend/intel/models.py` | `git mv` | Pydantic models for disaster reports. |
| `Disaster API/src/pipeline.py` | `backend/intel/pipeline.py` | `git mv` | Multi-source aggregator pipeline. |
| `Disaster API/src/query_parser.py` | `backend/intel/query_parser.py` | `git mv` | Location and disaster keyword extractor. |
| `Disaster API/src/server.py` | `_deprecated/disaster_server.py` | Deprecate | Routes moved to `backend/app/api/disaster.py` and `copernicus.py`. |
| `Disaster API/src/tavily_client.py` | `backend/intel/tavily_client.py` | `git mv` | Tavily web search service with domain scoring. |
| `Disaster API/src/verification.py` | `backend/intel/verification.py` | `git mv` | Cross-source regex and claim verification. |
| `Disaster API/requirements.txt` | `_deprecated/disaster_api_requirements.txt` | Deprecate | Merged into root `requirements.txt`. |
| `Disaster API/README.md` | `_deprecated/disaster_api_README.md` | Deprecate | Subsumed by root documentation. |
| `Disaster API/.gitignore` | `_deprecated/disaster_api_gitignore` | Deprecate | Merged into root `.gitignore`. |
| `Disaster API/tests/` | `tests/intel/` | `git mv` | Disaster API unit test suite. |
| **Fetchengine (SAR Subsystem)** | | | |
| `fetchengine/01_catalog.py` | `backend/sar/catalog.py` | `git mv` | Renamed to valid Python module identifier. |
| `fetchengine/02_fetch.py` | `backend/sar/fetch.py` | `git mv` | Renamed to valid Python module identifier. |
| `fetchengine/03_validate.py` | `backend/sar/validate.py` | `git mv` | Renamed to valid Python module identifier. |
| `fetchengine/04_process.py` | `backend/sar/process.py` | `git mv` | Renamed to valid Python module identifier. |
| `fetchengine/05_visualize.py` | `backend/sar/visualize.py` | `git mv` | Renamed to valid Python module identifier. |
| `fetchengine/pipeline_utils.py` | `backend/sar/pipeline_utils.py` | `git mv` | Core utilities, token caching, bbox transforms. |
| `fetchengine/cdse_bridge.py` | `backend/sar/bridge.py` | `git mv` | Status querying, run listings, metadata generation. |
| `fetchengine/run_pipeline.py` | `backend/sar/run_pipeline.py` | `git mv` | Sequential pipeline coordinator. |
| `fetchengine/check_s1_catalog.py` | `scripts/check_s1_catalog.py` | `git mv` | Standalone diagnostic tool moved to `scripts/`. |
| `fetchengine/visualize_rasters.py` | `scripts/visualize_rasters.py` | `git mv` | Diagnostic visualizer moved to `scripts/`. |
| `fetchengine/config.yaml` | `backend/sar/config/kerala_2018.yaml` | `git mv` | Named config for Kerala benchmark. |
| `fetchengine/config_lucknow.yaml` | `backend/sar/config/lucknow_2026.yaml` | `git mv` | Named config for Lucknow benchmark. |
| `fetchengine/cdse_fetch.py` | `_deprecated/cdse_fetch.py` | Move | Legacy OData downloader (unused, superseded by Process API). |
| `fetchengine/cdse_process.py` | `_deprecated/cdse_process.py` | Move | Legacy prototype script (unused, superseded by 02_fetch/04_process). |
| `fetchengine/README.md` | `backend/sar/README.md` | `git mv` | SAR engineering docs. |
| `fetchengine/instruction.md` | `backend/sar/instruction.md` | `git mv` | Remote sensing reference instructions. |
| `fetchengine/runs/` | `data/runs/` | `git mv` | Relocated to shared data directory. |
| **RAG-AI-main Subsystem** | | | |
| `RAG-AI-main/.env.example` | `_deprecated/rag_ai.env.example` | Deprecate | Merged into root `.env.example`. |
| `RAG-AI-main/.gitignore` | `_deprecated/rag_ai_gitignore` | Deprecate | Merged into root `.gitignore`. |
| `RAG-AI-main/requirements.txt` | `_deprecated/rag_ai_requirements.txt` | Deprecate | Merged into root `requirements.txt`. |
| `RAG-AI-main/main.py` | `_deprecated/rag_main.py` | Deprecate | Standalone demo CLI superseded by API & scripts. |
| `RAG-AI-main/README.md` | `backend/rag/README.md` | `git mv` | RAG module documentation. |
| `RAG-AI-main/config/sources.json` | `backend/rag/config/sources.json` | `git mv` | Ingestion sources configuration. |
| `RAG-AI-main/data/fixtures/` | `data/fixtures/` | `git mv` | Sample JSONL test documents. |
| `RAG-AI-main/data/chroma_db/` | `data/chroma_db/` | `git mv` | Local ChromaDB vector database. |
| `RAG-AI-main/processor/` | `backend/rag/processor/` | `git mv` | Cleaner, deduplicator, validator. |
| `RAG-AI-main/rag/` | `backend/rag/` | `git mv` | Embedder, chunker, vector store, retriever, generator, satellite adapter. |
| `RAG-AI-main/rag/fastapi_service.py` | `backend/rag/fastapi_service.py` | `git mv` | Service layer adapted for `backend/app/api/ai.py`. |
| `RAG-AI-main/scraper/api_scraper.py` | `_deprecated/rag_api_scraper.py` | Move | Duplicate ReliefWeb v1 client; replaced by intel client adapter. |
| `RAG-AI-main/scraper/tavily_scraper.py` | `_deprecated/rag_tavily_scraper.py` | Move | Duplicate Tavily client; replaced by intel client adapter. |
| `RAG-AI-main/scraper/base_scraper.py` | `backend/rag/scraper/base_scraper.py` | `git mv` | Trafilatura HTML scraper. |
| `RAG-AI-main/scraper/rss_scraper.py` | `backend/rag/scraper/rss_scraper.py` | `git mv` | Feedparser RSS scraper. |
| `RAG-AI-main/scraper/metadata_extractor.py` | `backend/rag/scraper/metadata_extractor.py` | `git mv` | LLM-assisted metadata enhancer. |
| `RAG-AI-main/scraper/pipeline.py` | `backend/rag/scraper/pipeline.py` | `git mv` | Ingestion coordinator. |
| `RAG-AI-main/scripts/` | `scripts/rag/` | `git mv` | `build_index.py`, `query_rag.py`, `run_scraper.py`. |
| `RAG-AI-main/tests/` | `tests/rag/` | `git mv` | RAG unit test suite. |
| **Frontend & Shared Scripts** | | | |
| `frontend/` | `frontend/` | Unchanged | Location preserved per specification. |
| `scripts/self_audit.py` | `scripts/self_audit.py` | Update | Update import paths to `backend.intel` & `backend.sar`. |

---

### 5. Detailed List of Broken Imports (File : Line)

The following 108 import statements across the codebase will break upon structural movement and will be updated in Stage 1 and Stage 2:

#### A. Disaster API (`Disaster API/src/*` -> `backend/intel/*`)
- `Disaster API/src/clients/__init__.py:9`: `from src.clients.usgs_client import ...` -> `from backend.intel.clients.usgs_client import ...`
- `Disaster API/src/clients/__init__.py:18`: `from src.clients.gdacs_client import ...` -> `from backend.intel.clients.gdacs_client import ...`
- `Disaster API/src/clients/__init__.py:27`: `from src.clients.reliefweb_client import ...` -> `from backend.intel.clients.reliefweb_client import ...`
- `Disaster API/src/clients/__init__.py:36`: `from src.clients.firms_client import ...` -> `from backend.intel.clients.firms_client import ...`
- `Disaster API/src/clients/__init__.py:84`: `import src.clients.usgs_client as usgs_mod` -> `import backend.intel.clients.usgs_client as usgs_mod`
- `Disaster API/src/clients/__init__.py:87`: `import src.clients.gdacs_client as gdacs_mod` -> `import backend.intel.clients.gdacs_client as gdacs_mod`
- `Disaster API/src/clients/__init__.py:90`: `import src.clients.reliefweb_client as rw_mod` -> `import backend.intel.clients.reliefweb_client as rw_mod`
- `Disaster API/src/clients/__init__.py:93`: `import src.clients.firms_client as firms_mod` -> `import backend.intel.clients.firms_client as firms_mod`
- `Disaster API/src/clients/firms_client.py:38`: `from src.config import FIRMSConfig, get_firms_config, mask_api_key` -> `from backend.app.config import get_settings`
- `Disaster API/src/clients/firms_client.py:39`: `from src.models import ActiveFireDetection, FIRMSQueryResponse` -> `from backend.intel.models import ActiveFireDetection, FIRMSQueryResponse`
- `Disaster API/src/clients/gdacs_client.py:23`: `from src.config import GDACSConfig, get_gdacs_config` -> `from backend.app.config import get_settings`
- `Disaster API/src/clients/gdacs_client.py:24`: `from src.models import GDACSEvent, GDACSQueryResponse, GeoBounds` -> `from backend.intel.models import GDACSEvent, GDACSQueryResponse, GeoBounds`
- `Disaster API/src/clients/reliefweb_client.py:24`: `from src.config import ReliefWebConfig, get_reliefweb_config` -> `from backend.app.config import get_settings`
- `Disaster API/src/clients/reliefweb_client.py:25`: `from src.models import ReliefWebReport, ReliefWebQueryResponse` -> `from backend.intel.models import ReliefWebReport, ReliefWebQueryResponse`
- `Disaster API/src/clients/usgs_client.py:18`: `from src.config import USGSConfig, get_usgs_config` -> `from backend.app.config import get_settings`
- `Disaster API/src/clients/usgs_client.py:19`: `from src.models import EarthquakeEvent, EarthquakeQueryResponse, GeoBounds` -> `from backend.intel.models import EarthquakeEvent, EarthquakeQueryResponse, GeoBounds`
- `Disaster API/src/main.py:23`: `from src.config import ConfigurationError` -> `from backend.app.config import ConfigurationError`
- `Disaster API/src/main.py:24`: `from src.tavily_client import ...` -> `from backend.intel.tavily_client import ...`
- `Disaster API/src/main.py:172`: `from src.pipeline import DisasterPipeline` -> `from backend.intel.pipeline import DisasterPipeline`
- `Disaster API/src/pipeline.py:30`: `from src.clients.firms_client import FIRMSClient, FIRMSClientError` -> `from backend.intel.clients.firms_client import ...`
- `Disaster API/src/pipeline.py:31`: `from src.clients.gdacs_client import GDACSClient, GDACSClientError` -> `from backend.intel.clients.gdacs_client import ...`
- `Disaster API/src/pipeline.py:32`: `from src.clients.reliefweb_client import ReliefWebClient, ReliefWebClientError` -> `from backend.intel.clients.reliefweb_client import ...`
- `Disaster API/src/pipeline.py:33`: `from src.clients.usgs_client import USGSClient, USGSClientError` -> `from backend.intel.clients.usgs_client import ...`
- `Disaster API/src/pipeline.py:34`: `from src.config import ConfigurationError` -> `from backend.app.config import ConfigurationError`
- `Disaster API/src/pipeline.py:35`: `from src.models import UnifiedIncidentReport...` -> `from backend.intel.models import UnifiedIncidentReport...`
- `Disaster API/src/pipeline.py:50`: `from src.query_parser import parse_disaster_query` -> `from backend.intel.query_parser import parse_disaster_query`
- `Disaster API/src/pipeline.py:55`: `from src.tavily_client import TavilySearchError, TavilySearchService` -> `from backend.intel.tavily_client import ...`
- `Disaster API/src/pipeline.py:56`: `from src.verification import ...` -> `from backend.intel.verification import ...`
- `Disaster API/src/server.py:36`: `from src.pipeline import DisasterPipeline` -> `from backend.intel.pipeline import DisasterPipeline`
- `Disaster API/src/server.py:37`: `from src.models import UnifiedIncidentReport` -> `from backend.intel.models import UnifiedIncidentReport`
- `Disaster API/src/server.py:38`: `from src.clients.reliefweb_client import ReliefWebClient` -> `from backend.intel.clients.reliefweb_client import ...`
- `Disaster API/src/server.py:39`: `import fetchengine.cdse_bridge as cdse_bridge` -> `import backend.sar.bridge as cdse_bridge`
- `Disaster API/src/tavily_client.py:22`: `from src.config import ConfigurationError, TavilyConfig...` -> `from backend.app.config import get_settings`
- `Disaster API/src/tavily_client.py:23`: `from src.models import ...` -> `from backend.intel.models import ...`
- `Disaster API/src/tavily_client.py:29`: `from src.query_parser import parse_disaster_query` -> `from backend.intel.query_parser import ...`
- `Disaster API/src/tavily_client.py:30`: `from src.verification import ...` -> `from backend.intel.verification import ...`
- `Disaster API/src/verification.py:12`: `from src.models import ...` -> `from backend.intel.models import ...`
- `Disaster API/src/verification.py:17`: `from src.query_parser import ...` -> `from backend.intel.query_parser import ...`

#### B. Fetchengine (`fetchengine/*` -> `backend/sar/*`)
- `fetchengine/01_catalog.py:16`: `from pipeline_utils import load_config, get_cdse_token, CATALOG_URL` -> `from backend.sar.pipeline_utils import ...`
- `fetchengine/02_fetch.py:16`: `from pipeline_utils import ...` -> `from backend.sar.pipeline_utils import ...`
- `fetchengine/03_validate.py:14`: `from pipeline_utils import load_config` -> `from backend.sar.pipeline_utils import load_config`
- `fetchengine/04_process.py:19`: `from pipeline_utils import load_config` -> `from backend.sar.pipeline_utils import load_config`
- `fetchengine/05_visualize.py:17`: `from pipeline_utils import load_config` -> `from backend.sar.pipeline_utils import load_config`
- `fetchengine/cdse_bridge.py:31`: `from pipeline_utils import ...` -> `from backend.sar.pipeline_utils import ...`
- `fetchengine/cdse_bridge.py:39`: `from fetchengine.pipeline_utils import ...` -> `from backend.sar.pipeline_utils import ...`
- `fetchengine/run_pipeline.py:13`: `from pipeline_utils import load_config` -> `from backend.sar.pipeline_utils import load_config`

#### C. RAG-AI-main (`RAG-AI-main/*` -> `backend/rag/*`)
- `RAG-AI-main/rag/fastapi_service.py:18`: `from rag.api_schemas import ...` -> `from backend.rag.api_schemas import ...`
- `RAG-AI-main/rag/fastapi_service.py:26`: `from rag.pipeline import DisasterIntelligenceResult, DisasterRAGPipeline` -> `from backend.rag.pipeline import ...`
- `RAG-AI-main/rag/fastapi_service.py:27`: `from rag.satellite_adapter import ...` -> `from backend.rag.satellite_adapter import ...`
- `RAG-AI-main/rag/pipeline.py:28`: `from rag.embedder import Embedder` -> `from backend.rag.embedder import Embedder`
- `RAG-AI-main/rag/pipeline.py:29`: `from rag.generator import Generator, RAGResponse` -> `from backend.rag.generator import Generator, RAGResponse`
- `RAG-AI-main/rag/pipeline.py:30`: `from rag.retriever import Retriever, extract_disaster_events` -> `from backend.rag.retriever import ...`
- `RAG-AI-main/rag/pipeline.py:31`: `from rag.satellite_adapter import ...` -> `from backend.rag.satellite_adapter import ...`
- `RAG-AI-main/rag/pipeline.py:32`: `from rag.vector_store import VectorStore` -> `from backend.rag.vector_store import VectorStore`
- `RAG-AI-main/rag/retriever.py:18`: `from rag.vector_store import VectorStore` -> `from backend.rag.vector_store import VectorStore`
- `RAG-AI-main/rag/vector_store.py:17`: `from rag.chunker import Chunk` -> `from backend.rag.chunker import Chunk`
- `RAG-AI-main/rag/vector_store.py:18`: `from rag.embedder import Embedder` -> `from backend.rag.embedder import Embedder`
- `RAG-AI-main/scraper/api_scraper.py:21`: `from processor.cleaner import clean_text, clean_title` -> `from backend.rag.processor.cleaner import ...`
- `RAG-AI-main/scraper/api_scraper.py:22`: `from processor.validator import ...` -> `from backend.rag.processor.validator import ...`
- `RAG-AI-main/scraper/base_scraper.py:21`: `from processor.cleaner import ...` -> `from backend.rag.processor.cleaner import ...`
- `RAG-AI-main/scraper/base_scraper.py:22`: `from processor.validator import ...` -> `from backend.rag.processor.validator import ...`
- `RAG-AI-main/scraper/metadata_extractor.py:19`: `from processor.validator import ...` -> `from backend.rag.processor.validator import ...`
- `RAG-AI-main/scraper/pipeline.py:16`: `from processor.deduplicator import Deduplicator` -> `from backend.rag.processor.deduplicator import Deduplicator`
- `RAG-AI-main/scraper/pipeline.py:17`: `from processor.validator import DisasterDocument` -> `from backend.rag.processor.validator import DisasterDocument`
- `RAG-AI-main/scraper/pipeline.py:18-21`: `from scraper.* import ...` -> `from backend.rag.scraper.* import ...`
- `RAG-AI-main/scraper/rss_scraper.py:19-20`: `from processor.* import ...` -> `from backend.rag.processor.* import ...`
- `RAG-AI-main/scraper/tavily_scraper.py:19-20`: `from processor.* import ...` -> `from backend.rag.processor.* import ...`

#### D. Tests (`Disaster API/tests/*` and `RAG-AI-main/tests/*`)
- `Disaster API/tests/test_config.py:7,67,89,118`: `from src.config import ...` -> `from backend.app.config import ...`
- `Disaster API/tests/test_firms_client.py:23,35,36`: `from src.clients.firms_client import ...; from src.config import ...; from src.models import ...` -> `backend.intel.*` and `backend.app.config`
- `Disaster API/tests/test_gdacs_client.py:27,36,37`: `from src.clients.gdacs_client import ...` -> `backend.intel.*`
- `Disaster API/tests/test_models.py:5,103`: `from src.models import ...` -> `from backend.intel.models import ...`
- `Disaster API/tests/test_pipeline.py:20-62`: `from src.clients.* import ...; from src.models import ...; from src.pipeline import ...` -> `backend.intel.*`
- `Disaster API/tests/test_query_parser.py:6`: `from src.query_parser import ...` -> `from backend.intel.query_parser import ...`
- `Disaster API/tests/test_reliefweb_client.py:27,37,38`: `from src.clients.reliefweb_client import ...` -> `backend.intel.*`
- `Disaster API/tests/test_server.py:21`: `from src.server import app` -> `from backend.app.main import app`
- `Disaster API/tests/test_tavily_client.py:15,16,22`: `from src.tavily_client import ...` -> `backend.intel.*`
- `Disaster API/tests/test_usgs_client.py:26,35,36`: `from src.clients.usgs_client import ...` -> `backend.intel.*`
- `Disaster API/tests/test_verification.py:12-14`: `from src.verification import ...` -> `backend.intel.*`
- `RAG-AI-main/tests/test_ai_integration.py:19-22,184-187,229-232,275-276`: `from rag.* import ...; from processor.* import ...` -> `from backend.rag.* import ...`
- `RAG-AI-main/tests/test_processor.py:16-18,314`: `from processor.* import ...; from scraper.* import ...` -> `from backend.rag.processor.* import ...`
- `RAG-AI-main/tests/test_rag.py:13,14,126-402`: `from rag.* import ...; from processor.* import ...` -> `from backend.rag.* import ...`
- `RAG-AI-main/tests/test_scraper.py:14,15,57,172,299`: `from scraper.* import ...; from processor.* import ...` -> `from backend.rag.scraper.* import ...`

#### E. Root Scripts
- `scripts/self_audit.py:63`: `import fetchengine.cdse_bridge as cdse_bridge` -> `import backend.sar.bridge as cdse_bridge`
- `scripts/self_audit.py:70`: `from src.server import app` -> `from backend.app.main import app`

---

### 6. Detailed List of Hardcoded Paths & Sys.path Modifications (File : Line)

The following 27 hardcoded path references will break or must be refactored to use `backend.app.config.Settings`:

| File : Line | Hardcoded Path / Expression | Problem | Resolution in Refactor |
| :--- | :--- | :--- | :--- |
| `run_server.py:10-17` | `DISASTER_API_DIR = ROOT_DIR / "Disaster API"`, `sys.path.insert(0, ...)` | Ad-hoc `sys.path` injection bypasses normal Python package resolution. | Deprecate `run_server.py`; use `run.py` pointing to `backend.app.main:app`. |
| `Disaster API/src/config.py:14-16` | `Path(__file__).resolve().parent.parent / ".env"` | Hardcodes `.env` location inside `Disaster API/`. | Replace with unified loader in `backend/app/config.py` resolving root `.env`. |
| `Disaster API/src/server.py:27-33` | `PROJECT_ROOT = Path(__file__).resolve().parent.parent`, `sys.path.insert(0, ...)` | Injects `Disaster API` and `fetchengine` into `sys.path`. | Unified package structure with `backend/` as top-level package; remove manual injections. |
| `Disaster API/src/server.py:67` | `runs_dir = FETCHENGINE_DIR / "runs"` | Hardcodes static file mount to `fetchengine/runs`. | Configure via `settings.RUNS_STORAGE_DIR` (defaults to `data/runs`). |
| `fetchengine/pipeline_utils.py:16` | `ENV_PATH = Path(__file__).resolve().parent / ".env"` | Hardcodes `.env` inside `fetchengine/.env`. | Replace with `backend.app.config.get_settings()`. |
| `fetchengine/pipeline_utils.py:144` | `run_dir = Path("runs") / f"{cfg['name'].lower()}_{cfg['event_date']}"` | Relative path assumes execution strictly from `fetchengine/` cwd. | Anchor to `settings.RUNS_STORAGE_DIR / f"{cfg['name'].lower()}_{cfg['event_date']}"`. |
| `fetchengine/cdse_bridge.py:26-28` | `FETCHENGINE_DIR = Path(__file__).resolve().parent`, `sys.path.insert(0, ...)` | Manual `sys.path` injection. | Remove; use standard package imports `backend.sar.*`. |
| `fetchengine/cdse_bridge.py:49` | `RUNS_DIR = FETCHENGINE_DIR / "runs"` | Hardcoded path to `fetchengine/runs`. | Replace with `settings.RUNS_STORAGE_DIR` (`data/runs`). |
| `fetchengine/cdse_bridge.py:209,226` | `"static_url": f"/runs/{clean_id}/previews/{defn['filename']}"` | Assumes `/runs/` URL static mount. | Preserve route contract mounted at `settings.RUNS_STORAGE_DIR`. |
| `RAG-AI-main/main.py:28` | `sys.path.insert(0, str(Path(__file__).resolve().parent))` | Injects `RAG-AI-main` to `sys.path`. | Deprecate file; CLI moved to `scripts/rag/query_rag.py`. |
| `RAG-AI-main/main.py:66` | `config_path=Path("config/sources.json")` | Relative path breaks if run from root. | Anchor to `backend/rag/config/sources.json`. |
| `RAG-AI-main/main.py:89` | `persist_dir="data/chroma_db"` | Relative path breaks if run from root. | Configure via `settings.CHROMA_PERSIST_DIR` (`data/chroma_db`). |
| `RAG-AI-main/rag/pipeline.py:128-131` | `DEFAULT_CHROMA_DIR = os.environ.get("CHROMA_PERSIST_DIR", str(Path(__file__).resolve().parent.parent / "data" / "chroma_db"))` | Hardcodes fallback to `RAG-AI-main/data/chroma_db`. | Replace with `settings.CHROMA_PERSIST_DIR` (`./data/chroma_db`). |
| `RAG-AI-main/rag/vector_store.py:23-26` | `DEFAULT_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", str(Path(__file__).resolve().parent.parent / "data" / "chroma_db"))` | Hardcodes fallback to `RAG-AI-main/data/chroma_db`. | Replace with `settings.CHROMA_PERSIST_DIR` (`./data/chroma_db`). |
| `RAG-AI-main/scraper/pipeline.py:66` | `config_path=Path("config/sources.json")` | Relative path assumes `RAG-AI-main/` cwd. | Anchor to absolute package path `backend/rag/config/sources.json`. |
| `RAG-AI-main/scripts/build_index.py:26` | `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` | Manual `sys.path` injection. | Update to workspace root resolution. |
| `RAG-AI-main/scripts/build_index.py:331` | `default="data/chroma_db"` | Default path relative to child folder. | Default to `settings.CHROMA_PERSIST_DIR`. |
| `RAG-AI-main/scripts/query_rag.py:26` | `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` | Manual `sys.path` injection. | Update to workspace root resolution. |
| `RAG-AI-main/scripts/run_scraper.py:27` | `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` | Manual `sys.path` injection. | Update to workspace root resolution. |
| `RAG-AI-main/scripts/run_scraper.py:48` | `default="config/sources.json"` | Relative path. | Anchor to `backend/rag/config/sources.json`. |
| `RAG-AI-main/tests/test_ai_integration.py:17` | `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` | Manual `sys.path` injection in test file. | Remove or anchor to workspace root. |
| `RAG-AI-main/tests/test_processor.py:14` | `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` | Manual `sys.path` injection in test file. | Remove or anchor to workspace root. |
| `RAG-AI-main/tests/test_rag.py:11` | `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` | Manual `sys.path` injection in test file. | Remove or anchor to workspace root. |
| `RAG-AI-main/tests/test_scraper.py:12` | `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` | Manual `sys.path` injection in test file. | Remove or anchor to workspace root. |
| `scripts/self_audit.py:20-27` | `ROOT_DIR = Path(__file__).resolve().parent.parent`, `sys.path.insert(...)` | Manual `sys.path` injection. | Update to include workspace root only. |
| `frontend/vite.config.js:11,15` | `target: 'http://127.0.0.1:8000'` | Hardcoded proxy backend port 8000. | Matches `settings.BACKEND_PORT=8000`. |
| `Disaster API/tests/test_server.py:304` | `client.get("/runs/kerala_2018-08-10/previews/summary_panel.png")` | Test targets static `/runs` mount. | Verify static mount preserved on unified `backend/app/main.py`. |

---

### 7. Stage 0 Approval Gate

- [x] Baseline test results recorded in `MIGRATION_LOG.md`
- [x] Live services, routes, and ports documented
- [x] Name problems flagged (space in "Disaster API", hyphen in "RAG-AI-main", numbered scripts in "fetchengine")
- [x] Complete Move Plan table created
- [x] All 108 broken imports and 27 hardcoded paths cataloged with file:line
- [ ] **Awaiting user approval ("continue") before proceeding to Stage 1.**
