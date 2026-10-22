"""
Pydantic API Schemas for FastAPI backend and React frontend integration.

Standardises request and response payloads across:
  - Natural language disaster queries
  - Verified Copernicus Sentinel-1 satellite observations
  - Retrieved evidence citations and grounding
  - Disaster events, timestamps, and uncertainty
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DisasterQueryRequest(BaseModel):
    """Incoming query request from frontend or backend services."""
    question: str = Field(
        ...,
        description="Natural language question (e.g. 'How does Sentinel-1 detect flood extent in Assam?')",
        examples=["What is the flood footprint and population impact in Assam?"],
    )
    event_id: Optional[str] = Field(
        None,
        description="Optional specific disaster event ID (e.g. 'assam-2024-06')",
    )
    hazard_type: Optional[str] = Field(
        None,
        description="Optional hazard filter (e.g. 'flood', 'cyclone', 'earthquake')",
    )
    region: Optional[str] = Field(
        None,
        description="Optional region / country filter (e.g. 'Assam', 'India', 'Bangladesh')",
    )
    operational_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional operational context from dispatch, sensors, or mission logs",
    )
    satellite_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Raw Copernicus Sentinel-1 change-detection analysis dictionary",
    )
    top_k: Optional[int] = Field(
        10,
        description="Number of candidate passages to retrieve before domain re-ranking",
    )
    final_k: Optional[int] = Field(
        5,
        description="Number of top passages to include in final LLM context",
    )


class EvidenceChunkSchema(BaseModel):
    chunk_id: str
    text: str
    metadata: Dict[str, Any] = {}
    distance: Optional[float] = None
    relevance_score: float = 0.0


class DisasterEventSchema(BaseModel):
    title: Optional[str] = None
    source_url: Optional[str] = None
    event_id: Optional[str] = None
    hazard_types: List[str] = []
    region: Optional[str] = None
    event_date: Optional[str] = None
    published_at: Optional[str] = None
    coordinates: Optional[List[float]] = None
    severity: Optional[str] = None
    affected_population: Optional[str] = None
    relevance_score: float = 0.0


class SatelliteEvidenceSchema(BaseModel):
    event_id: str
    event_name: str
    hazard_type: str
    sensor: str = "Sentinel-1"
    polarisation: str = "VV"
    pass_direction: str = "Ascending"
    pre_event_date: str
    post_event_date: str
    aoi_bbox: Optional[List[float]] = None
    aoi_center: Optional[List[float]] = None
    total_flood_area_km2: Optional[float] = None
    new_flood_area_km2: Optional[float] = None
    change_threshold_db: Optional[float] = None
    affected_roads_km: Optional[float] = None
    affected_bridges: Optional[int] = None
    affected_agri_km2: Optional[float] = None
    estimated_population_affected: Optional[int] = None
    priority_zones: List[Dict[str, Any]] = []
    confidence_notes: Optional[str] = None
    verification_source: str = "Copernicus Sentinel-1 SAR Pipeline"
    is_demo: bool = False


class SourceCitationSchema(BaseModel):
    title: str
    url: str
    relevance_score: float = 0.0
    chunk_id: Optional[str] = None


class DisasterQueryResponse(BaseModel):
    """Outgoing standardised response for FastAPI and React dashboard consumption."""
    question: str
    answer: str
    evidence: List[EvidenceChunkSchema] = []
    source_urls: List[str] = []
    disaster_events: List[DisasterEventSchema] = []
    timestamps: Dict[str, Optional[str]] = {}
    uncertainty_or_limitations: Optional[str] = None
    model_used: str = "offline"
    offline_mode: bool = True
    disaster_context: Optional[Dict[str, Any]] = None
    satellite_evidence: Optional[SatelliteEvidenceSchema] = None
    satellite_match_status: Optional[str] = None
    cited_sources: List[SourceCitationSchema] = []
