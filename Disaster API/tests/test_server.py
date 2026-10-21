"""
test_server.py: Comprehensive automated tests for FastAPI Disaster Intelligence & CDSE Sentinel-1 Server.
Tests all endpoints, request/response contracts, Kerala and Lucknow test cases,
preview image serving, error handling, and security boundaries.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
FETCHENGINE_DIR = WORKSPACE_ROOT / "fetchengine"
if str(FETCHENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(FETCHENGINE_DIR))

from src.server import app

client = TestClient(app)


# ------------------------------------------------------------------------------
# 1. Health & Upstream Reachability Tests
# ------------------------------------------------------------------------------
def test_health_endpoint():
    """Verify /api/health responds with 200 and comprehensive subsystem breakdown."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "subsystems" in data

    subsystems = data["subsystems"]
    assert "api_server" in subsystems
    assert subsystems["api_server"]["status"] == "healthy"
    assert "copernicus_cdse" in subsystems
    assert "tavily_web_intelligence" in subsystems
    assert "usgs_earthquake_catalog" in subsystems
    assert "gdacs_disaster_alerts" in subsystems
    assert "reliefweb_humanitarian" in subsystems
    rw_sub = subsystems["reliefweb_humanitarian"]
    assert "status" in rw_sub
    assert "configured" in rw_sub
    assert "available" in rw_sub
    assert "api_verified" in rw_sub
    assert "nasa_firms_active_fire" in subsystems

    # Check runs catalog is reported
    assert "runs_catalog" in data
    assert data["runs_catalog"]["total_runs"] >= 2
    assert "kerala_2018-08-10" in data["runs_catalog"]["available_runs"]
    assert "lucknow_2026-10-01" in data["runs_catalog"]["available_runs"]


# ------------------------------------------------------------------------------
# 2. Disaster Intelligence Query Tests (Kerala Floods)
# ------------------------------------------------------------------------------
def test_disaster_query_post_kerala():
    """Verify POST /api/disaster/query identifies Kerala Floods and resolves AOI bbox."""
    payload = {
        "query": "Kerala floods August 2018",
        "enable_tavily": False,  # Test core deterministic routing without external network
        "enable_usgs": False,
        "enable_gdacs": False,
        "enable_reliefweb": False,
        "enable_firms": False,
        "limit": 5,
    }
    response = client.post("/api/disaster/query", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["original_query"] == "Kerala floods August 2018"
    assert data["location"].lower() == "kerala"
    assert data["disaster_type"] == "floods"
    assert data["bbox"] == [76.2, 9.8, 76.6, 10.2]
    assert data["is_benchmark"] is True
    assert data["benchmark_run_id"] == "kerala_2018-08-10"


def test_disaster_query_get_kerala():
    """Verify GET /api/disaster/query with ?q= query-string parameter works identically."""
    response = client.get("/api/disaster/query?q=Kerala+floods+August+2018&enable_tavily=false&enable_usgs=false&enable_gdacs=false&enable_reliefweb=false&enable_firms=false")
    assert response.status_code == 200
    data = response.json()
    assert data["location"].lower() == "kerala"
    assert data["bbox"] == [76.2, 9.8, 76.6, 10.2]
    assert data["benchmark_run_id"] == "kerala_2018-08-10"


# ------------------------------------------------------------------------------
# 3. Disaster Intelligence Query Tests (Lucknow Gomti Basin)
# ------------------------------------------------------------------------------
def test_disaster_query_post_lucknow():
    """Verify POST /api/disaster/query identifies Lucknow and resolves Gomti AOI bbox."""
    payload = {
        "query": "Lucknow Gomti floods October 2026",
        "enable_tavily": False,
        "enable_usgs": False,
        "enable_gdacs": False,
        "enable_reliefweb": False,
        "enable_firms": False,
        "limit": 5,
    }
    response = client.post("/api/disaster/query", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "lucknow" in (data["location"] or "").lower() or "lucknow" in data["original_query"].lower()
    assert data["bbox"] == [80.85, 26.75, 81.05, 26.95]
    assert data["is_benchmark"] is True
    assert data["benchmark_run_id"] == "lucknow_2026-10-01"


def test_disaster_query_get_lucknow():
    """Verify GET /api/disaster/query works for Lucknow test case."""
    response = client.get("/api/disaster/query?q=Lucknow+floods+October+2026&enable_tavily=false&enable_usgs=false&enable_gdacs=false&enable_reliefweb=false&enable_firms=false")
    assert response.status_code == 200
    data = response.json()
    assert data["bbox"] == [80.85, 26.75, 81.05, 26.95]
    assert data["benchmark_run_id"] == "lucknow_2026-10-01"


def test_disaster_query_empty_error():
    """Verify empty query returns 400 Bad Request."""
    res_post = client.post("/api/disaster/query", json={"query": "   "})
    assert res_post.status_code == 400

    res_get = client.get("/api/disaster/query?q=")
    assert res_get.status_code == 400


# ------------------------------------------------------------------------------
# 4. Benchmark Preset Incidents Tests
# ------------------------------------------------------------------------------
def test_benchmark_incidents_list():
    """Verify /api/disaster/incidents returns curated benchmark incidents."""
    response = client.get("/api/disaster/incidents")
    assert response.status_code == 200
    incidents = response.json()
    assert isinstance(incidents, list)
    assert len(incidents) >= 2

    ids = [inc["id"] for inc in incidents]
    assert "kerala-2018" in ids
    assert "lucknow-2026" in ids


def test_benchmark_incident_detail_kerala():
    """Verify /api/disaster/incidents/kerala-2018 returns full report and linked run."""
    response = client.get("/api/disaster/incidents/kerala-2018")
    assert response.status_code == 200
    data = response.json()
    assert "copernicus_run" in data
    assert data["copernicus_run"]["run_id"] == "kerala_2018-08-10"
    assert data["copernicus_run"]["is_complete"] is True


def test_benchmark_incident_detail_lucknow():
    """Verify /api/disaster/incidents/lucknow-2026 returns full report and linked run."""
    response = client.get("/api/disaster/incidents/lucknow-2026")
    assert response.status_code == 200
    data = response.json()
    assert "copernicus_run" in data
    assert data["copernicus_run"]["run_id"] == "lucknow_2026-10-01"
    assert data["copernicus_run"]["is_complete"] is True


def test_benchmark_incident_not_found():
    """Verify non-existent incident returns 404."""
    response = client.get("/api/disaster/incidents/atlantis-floods")
    assert response.status_code == 404


# ------------------------------------------------------------------------------
# 5. Copernicus Sentinel-1 Run Status & Progression Tests
# ------------------------------------------------------------------------------
def test_copernicus_runs_list():
    """Verify /api/copernicus/runs lists existing disk runs."""
    response = client.get("/api/copernicus/runs")
    assert response.status_code == 200
    runs = response.json()
    run_ids = [r["run_id"] for r in runs]
    assert "kerala_2018-08-10" in run_ids
    assert "lucknow_2026-10-01" in run_ids


def test_copernicus_status_kerala():
    """Verify /api/copernicus/status/kerala_2018-08-10 returns full 5-stage progression."""
    response = client.get("/api/copernicus/status/kerala_2018-08-10")
    assert response.status_code == 200
    st = response.json()

    assert st["run_id"] == "kerala_2018-08-10"
    assert st["is_complete"] is True
    assert st["progress_pct"] == 100

    # Stages checks
    stages = st["stages"]
    assert stages["catalog"]["status"] == "COMPLETED"
    assert stages["catalog"]["relative_orbit"] == 165
    assert stages["catalog"]["orbit_direction"] == "DESCENDING"
    assert "S1A" in stages["catalog"]["pre_scene_id"]
    assert "S1A" in stages["catalog"]["post_scene_id"]

    assert stages["fetch"]["status"] == "COMPLETED"
    assert stages["fetch"]["grid_width_px"] == 2202
    assert stages["fetch"]["grid_height_px"] == 2221

    assert stages["validate"]["status"] == "PASSED"
    assert stages["validate"]["common_valid_pixels"] == 4890642

    assert stages["process"]["status"] == "COMPLETED"
    assert stages["process"]["candidate_clusters"] == 4360
    assert stages["process"]["flooded_area_ha"] > 4000.0

    assert stages["visualize"]["status"] == "COMPLETED"

    # Images catalog check
    images = st["images"]
    assert len(images) == 6
    for img in images:
        assert img["available"] is True
        assert img["size_bytes"] > 0
        assert img["url"].startswith("/api/copernicus/runs/kerala_2018-08-10/images/")


def test_copernicus_status_lucknow():
    """Verify /api/copernicus/status/lucknow_2026-10-01 returns full 5-stage progression."""
    response = client.get("/api/copernicus/status/lucknow_2026-10-01")
    assert response.status_code == 200
    st = response.json()

    assert st["run_id"] == "lucknow_2026-10-01"
    assert st["is_complete"] is True
    assert st["progress_pct"] == 100

    stages = st["stages"]
    assert stages["catalog"]["status"] == "COMPLETED"
    assert stages["catalog"]["relative_orbit"] == 165
    assert stages["fetch"]["status"] == "COMPLETED"
    assert stages["validate"]["status"] == "PASSED"
    assert stages["process"]["status"] == "COMPLETED"
    assert stages["visualize"]["status"] == "COMPLETED"

    images = st["images"]
    assert len(images) == 6
    for img in images:
        assert img["available"] is True
        assert img["size_bytes"] > 0


def test_copernicus_status_not_found():
    """Verify requesting non-existent run ID returns 404."""
    response = client.get("/api/copernicus/status/nonexistent_run_9999")
    assert response.status_code == 404


# ------------------------------------------------------------------------------
# 6. Preview Image Serving Tests (Every Generated Image Reachable over HTTP)
# ------------------------------------------------------------------------------
PREVIEW_FILENAMES = [
    "pre_vv_db.png",
    "post_vv_db.png",
    "delta_vv_db.png",
    "change_mask_overlay.png",
    "delta_vv_histogram.png",
    "summary_panel.png",
]


@pytest.mark.parametrize("filename", PREVIEW_FILENAMES)
def test_serve_kerala_preview_images(filename: str):
    """Verify each Kerala preview image is served with 200 and image/png MIME type."""
    url = f"/api/copernicus/runs/kerala_2018-08-10/images/{filename}"
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 1000  # Non-trivial image bytes


@pytest.mark.parametrize("filename", PREVIEW_FILENAMES)
def test_serve_lucknow_preview_images(filename: str):
    """Verify each Lucknow preview image is served with 200 and image/png MIME type."""
    url = f"/api/copernicus/runs/lucknow_2026-10-01/images/{filename}"
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 1000


def test_serve_image_not_found():
    """Verify non-existent image returns 404."""
    response = client.get("/api/copernicus/runs/kerala_2018-08-10/images/fake_image.png")
    assert response.status_code == 404


def test_static_runs_mount():
    """Verify static route /runs/... also reaches generated previews directly."""
    response = client.get("/runs/kerala_2018-08-10/previews/summary_panel.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_candidates_geojson_and_report_serving():
    """Verify candidates.geojson and report.md endpoints."""
    geo_resp = client.get("/api/copernicus/runs/kerala_2018-08-10/candidates.geojson")
    assert geo_resp.status_code == 200
    assert geo_resp.headers["content-type"] == "application/geo+json"

    rep_resp = client.get("/api/copernicus/runs/kerala_2018-08-10/report")
    assert rep_resp.status_code == 200
    assert rep_resp.headers["content-type"].startswith("text/markdown")
    assert "Sentinel-1 Change Intelligence Report" in rep_resp.text


# ------------------------------------------------------------------------------
# 8. ReliefWeb Live Results & Sample Label Regression Tests
# ------------------------------------------------------------------------------
def test_disaster_query_reliefweb_live_not_labeled_as_sample():
    """Regression test: verify live ReliefWeb queries return authentic records without mock labels."""
    payload = {
        "query": "Kerala floods August 2018",
        "enable_tavily": False,
        "enable_usgs": False,
        "enable_gdacs": False,
        "enable_reliefweb": True,
        "enable_firms": False,
        "limit": 5,
    }
    response = client.post("/api/disaster/query", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "reliefweb" in data
    rw = data["reliefweb"]
    assert rw["queried"] is True
    assert rw["status"] == "success"
    assert len(rw["matched_reports"]) > 0

    for rep in rw["matched_reports"]:
        # Verify genuine reports are never tagged with mock/sample demo markers
        assert "[SAMPLE" not in rep["title"].upper()
        assert "SAMPLE DEMO" not in rep["title"].upper()
        for src in rep.get("sources", []):
            assert "SAMPLE DEMO" not in src.upper()


def test_disaster_query_reliefweb_zero_match_remains_clean_empty():
    """Verify when ReliefWeb query legitimately finds 0 reports, matched_reports is clean empty list."""
    payload = {
        "query": "Lucknow Gomti floods October 2026",
        "enable_tavily": False,
        "enable_usgs": False,
        "enable_gdacs": False,
        "enable_reliefweb": True,
        "enable_firms": False,
        "limit": 5,
    }
    response = client.post("/api/disaster/query", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "reliefweb" in data
    rw = data["reliefweb"]
    assert rw["queried"] is True
    assert rw["status"] == "no_matching_reports"
    assert rw["matched_reports"] == []

