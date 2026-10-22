"""
Integration tests for AI-side platform integration:
  - Satellite Evidence Adapter (Copernicus Sentinel-1 SAR outputs)
  - Event-to-Observation spatial and temporal matching
  - Dual-stream grounding (disaster reports + satellite measurements)
  - Pydantic API schemas and DisasterAIService for FastAPI
  - Citation preservation, missing data handling, and uncertainty reporting
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.api_schemas import DisasterQueryRequest, DisasterQueryResponse
from rag.fastapi_service import DisasterAIService, create_ai_router
from rag.pipeline import DisasterRAGPipeline
from rag.satellite_adapter import SatelliteEvidence, SatelliteEvidenceAdapter


@pytest.fixture
def sample_copernicus_data():
    """Sample output conforming to teammate's Copernicus SAR pipeline."""
    return {
        "event": {
            "id": "assam-2024-06",
            "name": "Assam Flood — June 2024",
            "type": "flood",
            "status": "complete",
            "severity": "high",
            "preDate": "2024-05-28",
            "postDate": "2024-06-21",
            "sensor": "Sentinel-1A",
            "polarisation": "VV",
            "passDirection": "Ascending",
            "aoi": {
                "center": [26.58, 93.1],
                "zoom": 10,
                "bbox": [92.4, 26.1, 93.8, 27.1],
            },
            "summary": "Monsoon-driven inundation across Brahmaputra floodplain.",
        },
        "analysis": {
            "processingDate": "2024-06-24T08:31:00Z",
            "algorithmVersion": "1.2.0",
            "changeThresholdDb": -3.5,
            "confidenceNotes": "SRTM DEM shadow masked. JRC permanent water excluded.",
        },
        "impact": {
            "totalFloodAreaKm2": 312.4,
            "newFloodAreaKm2": 298.5,
            "affectedRoadKm": 27.5,
            "affectedBridgeCount": 3,
            "affectedAgriKm2": 148.2,
            "estimatedPopulationAffected": 68400,
        },
        "priority_zones": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "pz-01",
                        "rank": 1,
                        "priority": "critical",
                        "label": "NH-715 Bridge Inundation",
                        "reason": "Major arterial road submerged > 1 m depth.",
                        "popEstimate": None,
                    },
                    "geometry": {"type": "Point", "coordinates": [92.92, 26.52]},
                }
            ],
        },
        "images": {
            "pre": {
                "date": "2024-05-28",
                "sensor": "Sentinel-1A",
                "sourceId": "S1A_IW_GRDH_1SDV_20240528_...",
            },
            "post": {
                "date": "2024-06-21",
                "sensor": "Sentinel-1A",
                "sourceId": "S1A_IW_GRDH_1SDV_20240621_...",
            },
        },
    }


class TestSatelliteAdapter:
    def test_adapter_parses_copernicus_output(self, sample_copernicus_data):
        sat = SatelliteEvidenceAdapter.from_copernicus_output(
            event=sample_copernicus_data["event"],
            analysis=sample_copernicus_data["analysis"],
            impact=sample_copernicus_data["impact"],
            priority_zones=sample_copernicus_data["priority_zones"],
            images=sample_copernicus_data["images"],
        )
        assert sat.event_id == "assam-2024-06"
        assert sat.sensor == "Sentinel-1A"
        assert sat.total_flood_area_km2 == 312.4
        assert sat.new_flood_area_km2 == 298.5
        assert sat.change_threshold_db == -3.5
        assert sat.estimated_population_affected == 68400
        assert len(sat.priority_zones) == 1
        assert sat.priority_zones[0]["label"] == "NH-715 Bridge Inundation"

        ctx_str = sat.to_context_string()
        assert "Verified Copernicus Satellite Observations" in ctx_str
        assert "312.4 km²" in ctx_str
        assert "NH-715 Bridge Inundation" in ctx_str

    def test_matching_success_with_spatial_and_temporal_overlap(self, sample_copernicus_data):
        sat = SatelliteEvidenceAdapter.from_copernicus_output(
            event=sample_copernicus_data["event"],
            impact=sample_copernicus_data["impact"],
        )
        disaster_event = {
            "event_id": "assam-2024-06",
            "region": "Assam, India",
            "coordinates": [26.55, 92.90],  # inside bbox [92.4, 26.1, 93.8, 27.1]
            "event_date": "2024-06-15",     # between 2024-05-28 and 2024-06-21
            "hazard": "flood",
        }
        matched, reason, score = SatelliteEvidenceAdapter.match_satellite_with_event(sat, disaster_event)
        assert matched is True
        assert score >= 0.70
        assert "Event ID matches" in reason

    def test_matching_fails_on_spatial_mismatch(self, sample_copernicus_data):
        sat = SatelliteEvidenceAdapter.from_copernicus_output(
            event=sample_copernicus_data["event"]
        )
        # Event located in Mexico: lat 23.63, lon -102.55
        mexico_event = {
            "event_id": "different-event-id",
            "region": "Mexico",
            "coordinates": [23.63, -102.55],
            "event_date": "2024-06-15",
            "hazard": "flood",
        }
        matched, reason, score = SatelliteEvidenceAdapter.match_satellite_with_event(sat, mexico_event)
        assert matched is False
        assert "Spatial mismatch" in reason

    def test_matching_fails_on_temporal_mismatch(self, sample_copernicus_data):
        sat = SatelliteEvidenceAdapter.from_copernicus_output(
            event=sample_copernicus_data["event"]
        )
        # Event in 2021 (satellite pass was in 2024)
        old_event = {
            "event_id": "assam-2021-flood",
            "region": "Assam",
            "coordinates": [26.55, 92.90],
            "event_date": "2021-07-10",
            "hazard": "flood",
        }
        matched, reason, score = SatelliteEvidenceAdapter.match_satellite_with_event(sat, old_event)
        assert matched is False
        assert "Temporal mismatch" in reason

    def test_demo_data_is_distinguished_from_verified_measurements(self, sample_copernicus_data):
        demo_event = dict(sample_copernicus_data["event"])
        demo_event["isDemo"] = True
        demo_event["id"] = "demo-flood-01"

        sat = SatelliteEvidenceAdapter.from_copernicus_output(
            event=demo_event,
            impact=sample_copernicus_data["impact"],
        )
        assert sat.is_demo is True
        assert "Demo / Simulated" in sat.verification_source

        ctx_str = sat.to_context_string()
        assert "[DEMO / SIMULATED DATA - UNVERIFIED]" in ctx_str
        assert "NOT independently verified" in ctx_str


class TestDualGroundedAIResponses:
    def test_pipeline_integrates_satellite_and_retrieved_reports(self, tmp_path, sample_copernicus_data):
        from rag.embedder import Embedder
        from rag.chunker import chunk_document
        from rag.vector_store import VectorStore
        from processor.validator import DisasterDocument

        embedder = Embedder()
        store_dir = str(tmp_path / "dual_chroma")
        store = VectorStore(embedder=embedder, persist_dir=store_dir, collection_name="dual_test")

        doc = DisasterDocument(
            title="Local Relief Agency Situation Report — Assam",
            source_url="https://reliefweb.int/report/assam-flood-report",
            content="Local authorities report heavy monsoon floods in Kaziranga district. 50,000 people displaced.",
            hazard_types=["flood"],
            region="Assam",
            event_date="2024-06-18",
        )
        chunks = chunk_document(doc, chunk_size=80, overlap=10)
        store.add_chunks(chunks)

        pipeline = DisasterRAGPipeline(persist_dir=store_dir)
        pipeline._store = store
        pipeline._embedder = embedder

        res = pipeline.query(
            question="What is the observed flood extent and displacement in Assam?",
            disaster_context={"hazard": "flood", "location": "Assam, India", "event_id": "assam-2024-06"},
            satellite_data=sample_copernicus_data,
        )

        assert res.satellite_evidence is not None
        assert res.satellite_evidence["total_flood_area_km2"] == 312.4
        assert res.satellite_evidence["sensor"] == "Sentinel-1A"
        assert res.satellite_match_status is not None
        assert len(res.source_urls) >= 1
        assert "https://reliefweb.int/report/assam-flood-report" in res.source_urls

        # Verify display format includes verified satellite radar section
        disp = res.display()
        assert "[VERIFIED SATELLITE RADAR OBSERVATIONS]" in disp
        assert "312.4 km²" in disp


class TestFastAPIServiceAndSchemas:
    def test_service_query_returns_valid_response_schema(self, tmp_path, sample_copernicus_data):
        from rag.embedder import Embedder
        from rag.chunker import chunk_document
        from rag.vector_store import VectorStore
        from processor.validator import DisasterDocument

        embedder = Embedder()
        store_dir = str(tmp_path / "service_chroma")
        store = VectorStore(embedder=embedder, persist_dir=store_dir, collection_name="service_test")

        doc = DisasterDocument(
            title="Copernicus EMS Activation Report",
            source_url="https://emergency.copernicus.eu/emser",
            content="Copernicus EMS activated for Assam inundation. Rapid mapping underway.",
            hazard_types=["flood"],
            region="Assam",
        )
        store.add_chunks(chunk_document(doc, chunk_size=50, overlap=5))

        pipeline = DisasterRAGPipeline(persist_dir=store_dir)
        pipeline._store = store
        pipeline._embedder = embedder

        service = DisasterAIService(pipeline=pipeline)

        req = DisasterQueryRequest(
            question="What is the activation status for Assam?",
            event_id="assam-2024-06",
            hazard_type="flood",
            region="Assam",
            satellite_data=sample_copernicus_data,
        )

        resp = service.query(req)
        assert isinstance(resp, DisasterQueryResponse)
        assert resp.question == req.question
        assert resp.satellite_evidence is not None
        assert resp.satellite_evidence.total_flood_area_km2 == 312.4
        assert len(resp.source_urls) > 0
        assert resp.timestamps["queried_at"] is not None

        # Verify JSON serialisability (matches FastAPI response serialization)
        data = resp.model_dump()
        assert data["question"] == req.question
        assert data["satellite_evidence"]["sensor"] == "Sentinel-1A"

    def test_missing_data_returns_clear_uncertainty(self, tmp_path):
        from rag.embedder import Embedder
        from rag.vector_store import VectorStore

        embedder = Embedder()
        store_dir = str(tmp_path / "empty_chroma")
        store = VectorStore(embedder=embedder, persist_dir=store_dir, collection_name="empty_test")

        pipeline = DisasterRAGPipeline(persist_dir=store_dir)
        pipeline._store = store
        pipeline._embedder = embedder

        service = DisasterAIService(pipeline=pipeline)
        req = DisasterQueryRequest(question="Where is the volcanic eruption in Antarctica?")

        resp = service.query(req)
        assert "Insufficient evidence" in resp.answer
        assert resp.uncertainty_or_limitations is not None
        assert len(resp.evidence) == 0

    def test_create_ai_router_without_fastapi_raises_informative_error(self):
        with patch.dict("sys.modules", {"fastapi": None}):
            with pytest.raises(ImportError) as exc_info:
                create_ai_router()
            assert "FastAPI is required" in str(exc_info.value)

    def test_fastapi_router_mount_and_endpoints(self, sample_copernicus_data):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        mock_service = MagicMock(spec=DisasterAIService)
        mock_pipeline = MagicMock()
        mock_pipeline.store.count.return_value = 42
        mock_pipeline.generator._backend = "offline"
        mock_pipeline.generator._model_name = "offline"
        mock_service.pipeline = mock_pipeline

        mock_resp = DisasterQueryResponse(
            question="What is the flood impact?",
            answer="Verified SAR radar shows 312.4 km2 inundation.",
            evidence=[],
            source_urls=["https://emergency.copernicus.eu"],
            disaster_events=[],
            timestamps={"queried_at": "2024-06-25T10:00:00Z"},
            model_used="offline",
            offline_mode=True,
        )
        mock_service.query.return_value = mock_resp

        app = FastAPI()
        app.include_router(create_ai_router(service=mock_service), prefix="/api/ai", tags=["Disaster AI"])
        client = TestClient(app)

        # 1. Health endpoint test
        health_res = client.get("/api/ai/health")
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert health_data["status"] == "healthy"
        assert health_data["indexed_chunks"] == 42
        assert health_data["llm_backend"] == "offline"

        # 2. Query endpoint test
        query_res = client.post(
            "/api/ai/query",
            json={
                "question": "What is the flood impact?",
                "region": "Assam",
                "hazard_type": "flood",
                "satellite_data": sample_copernicus_data,
            },
        )
        assert query_res.status_code == 200
        query_data = query_res.json()
        assert query_data["question"] == "What is the flood impact?"
        assert "312.4 km2" in query_data["answer"]
        assert query_data["source_urls"] == ["https://emergency.copernicus.eu"]
