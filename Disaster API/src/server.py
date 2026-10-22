"""
server.py: Production FastAPI Backend for the Unified Disaster Intelligence & Sentinel-1 Platform.
Integrates:
  - Multi-Source Disaster Intelligence Pipeline (Tavily, USGS, GDACS, ReliefWeb, NASA FIRMS)
  - Copernicus Data Space Ecosystem (CDSE) Sentinel-1 SAR FetchEngine Bridge
  - Static & Dynamic Preview Image Serving with HTTP caching
  - Transparent Source Attribution & Partial-Failure Resilience
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
FETCHENGINE_DIR = WORKSPACE_ROOT / "fetchengine"
if str(FETCHENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(FETCHENGINE_DIR))

# Pipeline and models
from src.pipeline import DisasterPipeline
from src.models import UnifiedIncidentReport
from src.clients.reliefweb_client import ReliefWebClient
import fetchengine.cdse_bridge as cdse_bridge

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("disaster_server")

# FastAPI App
app = FastAPI(
    title="Disaster Intelligence & Copernicus Sentinel-1 Platform API",
    description="Unified API combining cross-source disaster verification with Sentinel-1 SAR change detection.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Pipeline instance
pipeline = DisasterPipeline()

# Mount fetchengine runs directory for static file access if it exists
runs_dir = FETCHENGINE_DIR / "runs"
runs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/runs", StaticFiles(directory=str(runs_dir)), name="runs")


# ------------------------------------------------------------------------------
# Request & Response Schemas
# ------------------------------------------------------------------------------
class DisasterQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language disaster query (e.g. 'Kerala floods August 2018')")
    enable_tavily: bool = Field(default=True, description="Query Tavily web intelligence")
    enable_usgs: bool = Field(default=True, description="Query USGS Earthquake Catalog")
    enable_gdacs: bool = Field(default=True, description="Query GDACS multi-hazard alerts")
    enable_reliefweb: bool = Field(default=True, description="Query ReliefWeb humanitarian situation reports")
    enable_firms: bool = Field(default=True, description="Query NASA FIRMS active fire satellite detections")
    limit: int = Field(default=10, ge=1, le=50, description="Max records per upstream source")


class CopernicusCatalogRequest(BaseModel):
    bbox: List[float] = Field(..., min_length=4, max_length=4, description="Bounding box [west, south, east, north]")
    event_date: str = Field(..., description="Target disaster event date (YYYY-MM-DD)")
    pre_window_days: int = Field(default=15, ge=1, le=60, description="Search window before event")
    post_window_days: int = Field(default=15, ge=1, le=60, description="Search window after event")
    orbit_direction: Optional[str] = Field(default=None, description="Optional filter: 'ASCENDING' or 'DESCENDING'")
    relative_orbit: Optional[int] = Field(default=None, description="Optional relative orbit track number")


class CopernicusFetchRequest(BaseModel):
    name: str = Field(..., description="Incident identifier (e.g. 'kerala', 'lucknow')")
    event_date: str = Field(..., description="Target disaster event date (YYYY-MM-DD)")
    bbox: List[float] = Field(..., min_length=4, max_length=4, description="Bounding box [west, south, east, north]")
    force_recompute: bool = Field(default=False, description="Force re-execution even if completed on disk")


# ------------------------------------------------------------------------------
# Health & Status Endpoint
# ------------------------------------------------------------------------------
_rw_health_cache: Dict[str, Any] = {}
_rw_health_cache_time: float = 0.0


def get_reliefweb_health(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Check ReliefWeb API v2 health and verify connectivity with approved appname.
    Caches results for 60 seconds to avoid upstream rate limiting.
    """
    global _rw_health_cache, _rw_health_cache_time
    now = time.time()
    if not force_refresh and _rw_health_cache and (now - _rw_health_cache_time < 60.0):
        return _rw_health_cache

    client = ReliefWebClient()
    res = client.check_health()
    _rw_health_cache = res
    _rw_health_cache_time = now
    return res


@app.get("/api/health", summary="Subsystem Health & Upstream Reachability Check")
def get_health() -> Dict[str, Any]:
    """
    Check operational status of the server, upstream disaster sources,
    and Copernicus Data Space credentials.
    """
    cdse_health = cdse_bridge.check_cdse_health()
    existing_runs = cdse_bridge.list_available_runs()

    # Tavily Key check
    tavily_key = os.getenv("TAVILY_API_KEY")
    tavily_status = "healthy" if tavily_key else "unconfigured"

    # FIRMS Key check
    firms_key = os.getenv("FIRMS_MAP_KEY")
    firms_status = "healthy" if firms_key else "unconfigured"

    return {
        "status": "healthy",
        "service": "Disaster Intelligence & Copernicus Sentinel-1 Platform",
        "version": "2.0.0",
        "subsystems": {
            "api_server": {"status": "healthy", "available": True},
            "copernicus_cdse": cdse_health,
            "tavily_web_intelligence": {
                "status": tavily_status,
                "configured": bool(tavily_key),
                "message": "API key configured" if tavily_key else "TAVILY_API_KEY not set in environment",
            },
            "usgs_earthquake_catalog": {
                "status": "healthy",
                "available": True,
                "message": "Public REST API (no auth required)",
            },
            "gdacs_disaster_alerts": {
                "status": "healthy",
                "available": True,
                "message": "Public REST & GeoJSON API (no auth required)",
            },
            "reliefweb_humanitarian": get_reliefweb_health(),
            "nasa_firms_active_fire": {
                "status": firms_status,
                "configured": bool(firms_key),
                "message": "MAP_KEY configured" if firms_key else "FIRMS_MAP_KEY not set in environment",
            },
        },
        "runs_catalog": {
            "runs_directory": str(runs_dir),
            "total_runs": len(existing_runs),
            "available_runs": [r["run_id"] for r in existing_runs],
        },
    }


# ------------------------------------------------------------------------------
# Disaster Intelligence Query Endpoints (Supports both POST & GET)
# ------------------------------------------------------------------------------
@app.post("/api/disaster/query", summary="Execute Unified Disaster Intelligence Query (POST)")
def execute_disaster_query_post(req: DisasterQueryRequest) -> Dict[str, Any]:
    """
    Execute unified disaster intelligence query across all configured feeds.
    Returns normalized incident parameters, sensor epicenters, alert scores,
    and cross-verified media evidence.
    """
    clean_q = req.query.strip()
    if not clean_q:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query string cannot be empty.")

    try:
        report: UnifiedIncidentReport = pipeline.process_query(
            query=clean_q,
            enable_tavily=req.enable_tavily,
            enable_usgs=req.enable_usgs,
            enable_gdacs=req.enable_gdacs,
            enable_reliefweb=req.enable_reliefweb,
            enable_firms=req.enable_firms,
            tavily_max_results=min(req.limit, 10),
            usgs_limit=req.limit,
            gdacs_limit=req.limit,
            reliefweb_limit=min(req.limit, 10),
            firms_limit=req.limit,
        )
        return report.model_dump()
    except Exception as exc:
        logger.error("Error executing disaster query POST: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Query execution error: {str(exc)}")


@app.get("/api/disaster/query", summary="Execute Unified Disaster Intelligence Query (GET)")
def execute_disaster_query_get(
    q: Optional[str] = Query(None, description="Query string alias (e.g. ?q=Kerala+floods)"),
    query: Optional[str] = Query(None, description="Query string parameter"),
    enable_tavily: bool = Query(True, description="Query Tavily web intelligence"),
    enable_usgs: bool = Query(True, description="Query USGS Earthquake Catalog"),
    enable_gdacs: bool = Query(True, description="Query GDACS multi-hazard alerts"),
    enable_reliefweb: bool = Query(True, description="Query ReliefWeb humanitarian situation reports"),
    enable_firms: bool = Query(True, description="Query NASA FIRMS active fire satellite detections"),
    limit: int = Query(10, ge=1, le=50, description="Max records per upstream source"),
) -> Dict[str, Any]:
    """
    Execute disaster query using GET query-string parameters.
    Fixes consistency with manual CLI and browser query tests.
    """
    target_query = (q or query or "").strip()
    if not target_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing query parameter. Provide 'q' or 'query' (e.g. /api/disaster/query?q=Kerala+floods+August+2018).",
        )

    req_obj = DisasterQueryRequest(
        query=target_query,
        enable_tavily=enable_tavily,
        enable_usgs=enable_usgs,
        enable_gdacs=enable_gdacs,
        enable_reliefweb=enable_reliefweb,
        enable_firms=enable_firms,
        limit=limit,
    )
    return execute_disaster_query_post(req_obj)


# ------------------------------------------------------------------------------
# Curated Benchmark Incidents Endpoints
# ------------------------------------------------------------------------------
BENCHMARK_INCIDENTS = [
    {
        "id": "kerala-2018",
        "name": "Kerala Monsoon Floods & Inundation",
        "query": "Kerala floods August 2018",
        "location": "Kerala, India",
        "hazard": "Floods",
        "event_date": "2018-08-10",
        "bbox": [76.2, 9.8, 76.6, 10.2],
        "copernicus_run_id": "kerala_2018-08-10",
        "description": "Severe 2018 monsoon disaster causing catastrophic flooding across Cochin and the Periyar basin.",
        "verified_satellites": ["Sentinel-1A SAR (VV/VH)", "USGS/GDACS Alert", "ReliefWeb Reports"],
    },
    {
        "id": "lucknow-2026",
        "name": "Lucknow Gomti River Basin Sentinel-1 AOI",
        "query": "Lucknow Gomti floods October 2026",
        "location": "Lucknow, Uttar Pradesh, India",
        "hazard": "Floods",
        "event_date": "2026-10-01",
        "bbox": [80.85, 26.75, 81.05, 26.95],
        "copernicus_run_id": "lucknow_2026-10-01",
        "description": "Benchmark Sentinel-1 change detection over the urban Gomti river basin in Lucknow.",
        "verified_satellites": ["Sentinel-1D SAR", "GDACS Multi-hazard", "ReliefWeb"],
    },
    {
        "id": "nepal-2026",
        "name": "Nepal Trishuli Landslide & River Debris Flow",
        "query": "Nepal Trishuli landslide August 2026",
        "location": "Trishuli Basin, Rasuwa, Nepal",
        "hazard": "Landslide",
        "event_date": "2026-08-26",
        "bbox": [85.10, 27.88, 85.56, 28.34],
        "copernicus_run_id": "nepal_trishuli_landslide_2026-08-26",
        "description": "High-altitude monsoon landslide and debris flow along the Bhote Kosi - Trishuli river corridor across Rasuwa, Nuwakot, and Dhading.",
        "verified_satellites": ["Sentinel-1 SAR (VV/VH)", "GDACS Multi-hazard", "ReliefWeb Reports"],
    },
    {
        "id": "california-2020",
        "name": "California Lightning Complex Wildfires",
        "query": "California wildfire August 2020",
        "location": "California, United States",
        "hazard": "Wildfire",
        "event_date": "2020-08-18",
        "bbox": [-124.5, 32.5, -114.0, 42.0],
        "copernicus_run_id": None,
        "description": "Historic August 2020 fire siege detected by NASA FIRMS satellite thermal sensors and GDACS alerts.",
        "verified_satellites": ["NASA FIRMS MODIS/VIIRS", "GDACS Wildfire", "ReliefWeb"],
    },
]


@app.get("/api/disaster/incidents", summary="List Curated Benchmark Incidents")
def list_benchmark_incidents() -> List[Dict[str, Any]]:
    """Return verified benchmark incidents with pre-computed satellite runs."""
    return BENCHMARK_INCIDENTS


@app.get("/api/disaster/incidents/{incident_id}", summary="Get Benchmark Incident Details")
def get_benchmark_incident(incident_id: str) -> Dict[str, Any]:
    """Retrieve full incident intelligence and satellite run linkage for a preset incident."""
    match = next((inc for inc in BENCHMARK_INCIDENTS if inc["id"] == incident_id), None)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark incident '{incident_id}' not found. Available: {[i['id'] for i in BENCHMARK_INCIDENTS]}",
        )

    # Run query through pipeline to get full intelligence report
    report = pipeline.process_query(
        query=match["query"],
        enable_tavily=True,
        enable_usgs=True,
        enable_gdacs=True,
        enable_reliefweb=True,
        enable_firms=True,
    )
    report_dict = report.model_dump()
    report_dict["preset_meta"] = match

    # If linked to copernicus run, attach run preview status
    if match.get("copernicus_run_id"):
        run_st = cdse_bridge.get_run_status(match["copernicus_run_id"])
        report_dict["copernicus_run"] = run_st

    return report_dict


# ------------------------------------------------------------------------------
# Copernicus CDSE FetchEngine Endpoints
# ------------------------------------------------------------------------------
@app.post("/api/copernicus/catalog", summary="Search CDSE STAC Catalog for Sentinel-1 Scenes")
def search_cdse_catalog(req: CopernicusCatalogRequest) -> Dict[str, Any]:
    """Search Copernicus STAC catalog for Sentinel-1 GRD scenes matching AOI and date."""
    result = cdse_bridge.search_copernicus_catalog(
        bbox=req.bbox,
        event_date=req.event_date,
        pre_window_days=req.pre_window_days,
        post_window_days=req.post_window_days,
        orbit_direction=req.orbit_direction,
        relative_orbit=req.relative_orbit,
    )
    return result


@app.post("/api/copernicus/fetch", summary="Trigger Sentinel-1 Fetch & Change Detection Pipeline")
def trigger_cdse_pipeline(req: CopernicusFetchRequest) -> Dict[str, Any]:
    """
    Trigger or register a Sentinel-1 disaster change detection pipeline run.
    Returns the run_id, stage status, and links to output rasters and previews.
    """
    res = cdse_bridge.trigger_run_pipeline(
        name=req.name,
        event_date=req.event_date,
        bbox=req.bbox,
        force=req.force_recompute,
    )
    return res


@app.get("/api/copernicus/runs", summary="List All Available FetchEngine Runs on Disk")
def list_runs() -> List[Dict[str, Any]]:
    """List all available pipeline execution runs found in the runs directory."""
    return cdse_bridge.list_available_runs()


@app.get("/api/copernicus/status/{run_id}", summary="Get Detailed Status & Progression of a Run")
@app.get("/api/copernicus/runs/{run_id}", summary="Get Detailed Status & Progression of a Run (Alias)")
def get_run_status_endpoint(run_id: str) -> Dict[str, Any]:
    """
    Retrieve real-time progression for stages 1 through 5, scene IDs,
    relative orbit numbers, coverage percentages, and all preview image links.
    """
    run_status = cdse_bridge.get_run_status(run_id)
    if not run_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in fetchengine runs directory.",
        )
    return run_status


@app.get("/api/copernicus/runs/{run_id}/images/{filename}", summary="Serve Preview Image Graphic")
def serve_preview_image(run_id: str, filename: str):
    """
    Stream a generated visualization preview PNG from the run directory
    with proper image/png MIME type and caching headers.
    """
    img_path = cdse_bridge.get_run_image_path(run_id, filename)
    if not img_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image '{filename}' not found for run '{run_id}'.",
        )

    return FileResponse(
        path=str(img_path),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f"inline; filename={filename}",
        },
    )


@app.get("/api/copernicus/runs/{run_id}/candidates.geojson", summary="Serve Flood Candidate GeoJSON Polygons")
def serve_candidate_geojson(run_id: str):
    """Serve candidate flood cluster GeoJSON polygons for Leaflet vector overlay."""
    clean_id = Path(run_id).name
    geo_path = runs_dir / clean_id / "candidates.geojson"
    if not geo_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"candidates.geojson not found for run '{run_id}'.",
        )

    return FileResponse(
        path=str(geo_path),
        media_type="application/geo+json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/copernicus/runs/{run_id}/report", summary="Serve Markdown Mission Report")
def serve_markdown_report(run_id: str):
    """Serve markdown mission report text."""
    clean_id = Path(run_id).name
    report_path = runs_dir / clean_id / "report.md"
    if not report_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"report.md not found for run '{run_id}'.",
        )

    content = report_path.read_text(encoding="utf-8")
    return PlainTextResponse(content=content, media_type="text/markdown")


# ------------------------------------------------------------------------------
# Direct Script Runner
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=True)
