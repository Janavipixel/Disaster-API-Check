"""
FastAPI Service and Integration Adapter for Disaster Intelligence.

Enables backend teammates to integrate the Scraper + RAG AI module into the
FastAPI application and React dashboard with minimal code:

    from rag.fastapi_service import create_ai_router
    app.include_router(create_ai_router(), prefix="/api/ai", tags=["Disaster AI"])

Also provides `DisasterAIService` for direct Python invocations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from rag.api_schemas import (
    DisasterQueryRequest,
    DisasterQueryResponse,
    DisasterEventSchema,
    EvidenceChunkSchema,
    SatelliteEvidenceSchema,
    SourceCitationSchema,
)
from rag.pipeline import DisasterIntelligenceResult, DisasterRAGPipeline
from rag.satellite_adapter import SatelliteEvidence, SatelliteEvidenceAdapter

logger = logging.getLogger(__name__)


class DisasterAIService:
    """
    Service wrapper around `DisasterRAGPipeline` implementing the
    FastAPI request/response contract.
    """

    def __init__(self, pipeline: Optional[DisasterRAGPipeline] = None):
        self.pipeline = pipeline or DisasterRAGPipeline()

    def query(self, req: DisasterQueryRequest) -> DisasterQueryResponse:
        """
        Process a structured query request and return a validated Pydantic response.
        """
        # Adapt satellite data if present
        sat_data = None
        if req.satellite_data:
            sat_data = req.satellite_data

        # Run pipeline
        result: DisasterIntelligenceResult = self.pipeline.query(
            question=req.question,
            disaster_context=req.operational_context,
            region_filter=req.region,
            hazard_filter=req.hazard_type,
            satellite_data=sat_data,
        )

        # Convert evidence chunks to schema
        evidence_schemas = []
        for ev in result.evidence:
            evidence_schemas.append(
                EvidenceChunkSchema(
                    chunk_id=ev.get("chunk_id", ""),
                    text=ev.get("text", ""),
                    metadata=ev.get("metadata", {}),
                    distance=ev.get("distance"),
                    relevance_score=ev.get("relevance_score", 0.0),
                )
            )

        # Convert disaster events to schema
        event_schemas = []
        for dev in result.disaster_events:
            event_schemas.append(
                DisasterEventSchema(
                    title=dev.get("title"),
                    source_url=dev.get("source_url"),
                    event_id=dev.get("event_id"),
                    hazard_types=dev.get("hazard_types", []),
                    region=dev.get("region"),
                    event_date=dev.get("event_date"),
                    published_at=dev.get("published_at"),
                    coordinates=dev.get("coordinates"),
                    severity=dev.get("severity"),
                    affected_population=dev.get("affected_population"),
                    relevance_score=dev.get("relevance_score", 0.0),
                )
            )

        # Convert citations
        citation_schemas = []
        for cite in result.cited_sources:
            citation_schemas.append(
                SourceCitationSchema(
                    title=cite.get("title", ""),
                    url=cite.get("url", ""),
                    relevance_score=cite.get("relevance_score", 0.0),
                    chunk_id=cite.get("chunk_id"),
                )
            )

        # Convert satellite evidence
        sat_schema = None
        if result.satellite_evidence:
            sat = result.satellite_evidence
            sat_schema = SatelliteEvidenceSchema(
                event_id=sat.get("event_id", ""),
                event_name=sat.get("event_name", ""),
                hazard_type=sat.get("hazard_type", "flood"),
                sensor=sat.get("sensor", "Sentinel-1"),
                polarisation=sat.get("polarisation", "VV"),
                pass_direction=sat.get("pass_direction", "Ascending"),
                pre_event_date=sat.get("pre_event_date", ""),
                post_event_date=sat.get("post_event_date", ""),
                aoi_bbox=sat.get("aoi_bbox"),
                aoi_center=sat.get("aoi_center"),
                total_flood_area_km2=sat.get("total_flood_area_km2"),
                new_flood_area_km2=sat.get("new_flood_area_km2"),
                change_threshold_db=sat.get("change_threshold_db"),
                affected_roads_km=sat.get("affected_roads_km"),
                affected_bridges=sat.get("affected_bridges"),
                affected_agri_km2=sat.get("affected_agri_km2"),
                estimated_population_affected=sat.get("estimated_population_affected"),
                priority_zones=sat.get("priority_zones", []),
                confidence_notes=sat.get("confidence_notes"),
                verification_source=sat.get("verification_source", "Copernicus Sentinel-1 SAR Pipeline"),
                is_demo=sat.get("is_demo", False),
            )

        return DisasterQueryResponse(
            question=result.question,
            answer=result.answer,
            evidence=evidence_schemas,
            source_urls=result.source_urls,
            disaster_events=event_schemas,
            timestamps=result.timestamps,
            uncertainty_or_limitations=result.uncertainty_or_limitations,
            model_used=result.model_used,
            offline_mode=result.offline_mode,
            disaster_context=result.disaster_context,
            satellite_evidence=sat_schema,
            satellite_match_status=result.satellite_match_status,
            cited_sources=citation_schemas,
        )


def create_ai_router(service: Optional[DisasterAIService] = None):
    """
    Create a FastAPI APIRouter for the Disaster Intelligence AI endpoints.

    Endpoints created:
      - POST /query: Run grounded disaster question answering
      - GET /health: Health check returning model and index status
    """
    try:
        from fastapi import APIRouter, HTTPException  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "FastAPI is required to use create_ai_router(). "
            "Install it in your backend environment using: pip install fastapi"
        ) from exc

    router = APIRouter()
    ai_service = service or DisasterAIService()

    @router.post(
        "/query",
        response_model=DisasterQueryResponse,
        summary="Query Disaster Intelligence RAG",
        description="Answers questions using grounded disaster documentation and verified Copernicus satellite observations.",
    )
    def query_endpoint(req: DisasterQueryRequest) -> DisasterQueryResponse:
        try:
            return ai_service.query(req)
        except Exception as exc:
            logger.error("AI service error processing query: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get(
        "/health",
        summary="AI Service Health Check",
    )
    def health_endpoint() -> Dict[str, Any]:
        count = ai_service.pipeline.store.count()
        backend = ai_service.pipeline.generator._backend
        model = ai_service.pipeline.generator._model_name
        return {
            "status": "healthy",
            "indexed_chunks": count,
            "llm_backend": backend,
            "model_name": model,
            "offline_mode": backend == "offline",
        }

    return router
