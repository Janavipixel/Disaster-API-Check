"""
Unified Disaster Intelligence RAG Pipeline.

Provides a clean, reusable interface for downstream systems:
  - Teammate's Disaster API
  - Copernicus Sentinel-1 Acquisition & Change Detection System
  - GIS Dashboard & Interactive CLI

Accepts a question and optional operational disaster context,
and returns structured intelligence:
  - Grounded AI answer
  - Retrieved evidence passages with confidence scores
  - Deduplicated source URLs
  - Extracted disaster events (coordinates, severity, dates)
  - Temporal metadata (query timestamp, evidence dates)
  - Uncertainty & limitations
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.embedder import Embedder
from rag.generator import Generator, RAGResponse
from rag.retriever import Retriever, extract_disaster_events
from rag.satellite_adapter import SatelliteEvidence, SatelliteEvidenceAdapter
from rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class DisasterIntelligenceResult:
    """
    Standardised result returned by the Disaster Intelligence RAG module.
    Directly serialisable to JSON for REST API endpoints.
    """
    question: str
    answer: str
    evidence: List[Dict[str, Any]]
    source_urls: List[str]
    disaster_events: List[Dict[str, Any]]
    timestamps: Dict[str, Optional[str]]
    uncertainty_or_limitations: Optional[str]
    model_used: str
    offline_mode: bool
    disaster_context: Optional[Dict[str, Any]] = None
    satellite_evidence: Optional[Dict[str, Any]] = None
    satellite_match_status: Optional[str] = None
    cited_sources: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a standard dictionary for backend API consumption."""
        return {
            "question": self.question,
            "answer": self.answer,
            "evidence": self.evidence,
            "source_urls": self.source_urls,
            "disaster_events": self.disaster_events,
            "timestamps": self.timestamps,
            "uncertainty_or_limitations": self.uncertainty_or_limitations,
            "model_used": self.model_used,
            "offline_mode": self.offline_mode,
            "disaster_context": self.disaster_context,
            "satellite_evidence": self.satellite_evidence,
            "satellite_match_status": self.satellite_match_status,
            "cited_sources": self.cited_sources,
        }

    def display(self) -> str:
        """Formatted terminal display safe for all console encodings."""
        divider = "=" * 70
        source_lines = (
            "\n".join(f"  * {url}" for url in self.source_urls)
            if self.source_urls
            else "  (None)"
        )

        event_lines = []
        for e in self.disaster_events[:5]:
            coords = f", coords: {e['coordinates']}" if e.get("coordinates") else ""
            date = f", date: {e['event_date']}" if e.get("event_date") else ""
            event_lines.append(
                f"  * {e.get('title', 'Unknown')} ({e.get('region', 'Global')}{date}{coords})"
            )
        event_str = "\n".join(event_lines) if event_lines else "  (None extracted)"

        sat_lines = ""
        if self.satellite_evidence:
            sat_status = f" [{self.satellite_match_status}]" if self.satellite_match_status else ""
            sat_lines = (
                f"\n[VERIFIED SATELLITE RADAR OBSERVATIONS]{sat_status}\n"
                f"  * Sensor: {self.satellite_evidence.get('sensor')} | Window: {self.satellite_evidence.get('pre_event_date')} to {self.satellite_evidence.get('post_event_date')}\n"
                f"  * Delineated Flood Footprint: {self.satellite_evidence.get('total_flood_area_km2')} km² (new water: {self.satellite_evidence.get('new_flood_area_km2')} km²)\n"
                f"  * Impact: ~{self.satellite_evidence.get('estimated_population_affected', 0):,} people in flood zone | {self.satellite_evidence.get('affected_roads_km')} km road flooded\n"
            )

        uncertainty_str = (
            f"\n[!] LIMITATIONS / UNCERTAINTY:\n{self.uncertainty_or_limitations}\n"
            if self.uncertainty_or_limitations
            else ""
        )

        mode_str = (
            "[OFFLINE MODE] No LLM called"
            if self.offline_mode
            else f"[MODEL: {self.model_used}]"
        )
        return (
            f"\n{divider}\n"
            f"[QUESTION] {self.question}\n"
            f"{mode_str}\n"
            f"{divider}\n"
            f"[ANSWER]\n\n{self.answer}\n"
            f"{sat_lines}"
            f"{uncertainty_str}\n"
            f"[DISASTER EVENTS] ({len(self.disaster_events)} found)\n{event_str}\n\n"
            f"[SOURCES] ({len(self.source_urls)} sources)\n{source_lines}\n"
            f"{divider}\n"
        )


DEFAULT_CHROMA_DIR = os.environ.get(
    "CHROMA_PERSIST_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "chroma_db"),
)


class DisasterRAGPipeline:
    """
    Unified high-level interface for Disaster Intelligence RAG.

    Usage::

        pipeline = DisasterRAGPipeline()
        result = pipeline.query("How does Sentinel-1 detect flood extents?")
        print(result.answer)
        print(result.source_urls)
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        model: Optional[str] = None,
        top_k: int = 10,
        final_k: int = 5,
        min_relevance: float = 0.20,
    ):
        self.persist_dir = persist_dir or DEFAULT_CHROMA_DIR
        self.top_k = top_k
        self.final_k = final_k
        self.min_relevance = min_relevance
        self.model = model

        # Lazy components
        self._embedder: Optional[Embedder] = None
        self._store: Optional[VectorStore] = None
        self._retriever: Optional[Retriever] = None
        self._generator: Optional[Generator] = None

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    @property
    def store(self) -> VectorStore:
        if self._store is None:
            self._store = VectorStore(embedder=self.embedder, persist_dir=self.persist_dir)
        return self._store

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever(
                vector_store=self.store,
                top_k=self.top_k,
                final_k=self.final_k,
                min_relevance=self.min_relevance,
            )
        return self._retriever

    @property
    def generator(self) -> Generator:
        if self._generator is None:
            self._generator = Generator(model=self.model)
        return self._generator

    def query(
        self,
        question: str,
        disaster_context: Optional[Dict[str, Any]] = None,
        region_filter: Optional[str] = None,
        hazard_filter: Optional[str] = None,
        satellite_data: Optional[Any] = None,
    ) -> DisasterIntelligenceResult:
        """
        Run end-to-end question answering with disaster intelligence grounding.

        Parameters
        ----------
        question : str
            Natural language question.
        disaster_context : Optional[Dict]
            Operational metadata from satellite pipeline or disaster feeds.
            Example: {"hazard": "flood", "location": "Valencia, Spain"}
        region_filter : Optional[str]
            Optional geographical filter (e.g. "Spain", "Mexico").
        hazard_filter : Optional[str]
            Optional hazard filter (e.g. "flood", "earthquake").
        satellite_data : Optional[SatelliteEvidence | Dict]
            Verified Copernicus Sentinel-1 change-detection output.

        Returns
        -------
        DisasterIntelligenceResult
            Structured result containing answer, evidence, URLs, events, and timestamps.
        """
        queried_at = datetime.now(timezone.utc).isoformat()

        # Step 1: Process and adapt satellite data if provided
        sat_evidence: Optional[SatelliteEvidence] = None
        sat_match_status: Optional[str] = None
        if satellite_data:
            if isinstance(satellite_data, SatelliteEvidence):
                sat_evidence = satellite_data
            elif isinstance(satellite_data, dict):
                # Could be a single dictionary representing event or a bundle
                event_dict = satellite_data.get("event") or satellite_data
                analysis_dict = satellite_data.get("analysis")
                impact_dict = satellite_data.get("impact")
                pz_dict = satellite_data.get("priority_zones")
                infra_dict = satellite_data.get("infrastructure")
                ts_dict = satellite_data.get("timeseries")
                img_dict = satellite_data.get("images")
                sat_evidence = SatelliteEvidenceAdapter.from_copernicus_output(
                    event=event_dict,
                    analysis=analysis_dict,
                    impact=impact_dict,
                    priority_zones=pz_dict,
                    infrastructure=infra_dict,
                    timeseries=ts_dict,
                    images=img_dict,
                )

        # Step 2: Retrieve relevant chunks
        chunks = self.retriever.retrieve(
            query=question,
            region=region_filter,
            hazard_type=hazard_filter,
        )

        # Step 3: Extract structured disaster events from documents
        events = extract_disaster_events(chunks)

        # Step 4: Validate correlation between satellite observations and disaster context/events
        if sat_evidence:
            # Check against operational context first if provided
            matched = False
            explanation = ""
            if disaster_context:
                matched, explanation, _ = SatelliteEvidenceAdapter.match_satellite_with_event(
                    satellite=sat_evidence, disaster_event=disaster_context
                )
            # If not matched yet, check against retrieved events
            if not matched and events:
                for ev in events:
                    matched, explanation, _ = SatelliteEvidenceAdapter.match_satellite_with_event(
                        satellite=sat_evidence, disaster_event=ev
                    )
                    if matched:
                        break

            sat_match_status = explanation if explanation else ("Verified Copernicus Satellite Observation" if matched else "Unmatched satellite observation")

        # Step 5: Format context (injecting disaster_context if present)
        context = self.retriever.format_context(
            chunks=chunks,
            disaster_context=disaster_context,
        )

        # Step 6: Call generator for grounded answer with both satellite and report evidence
        response: RAGResponse = self.generator.generate(
            question=question,
            chunks=chunks,
            context=context,
            disaster_context=disaster_context,
            satellite_evidence=sat_evidence,
        )

        source_urls = [s["url"] for s in response.sources if s.get("url")]

        dates = []
        for c in chunks:
            meta = c.get("metadata", {})
            d = meta.get("event_date") or meta.get("published_at")
            if d:
                dates.append(str(d))

        timestamps = {
            "queried_at": queried_at,
            "earliest_evidence_date": min(dates) if dates else None,
            "latest_evidence_date": max(dates) if dates else None,
        }

        # If satellite evidence was provided, include its timestamps
        if sat_evidence:
            if sat_evidence.pre_event_date and (not timestamps["earliest_evidence_date"] or sat_evidence.pre_event_date < timestamps["earliest_evidence_date"]):
                timestamps["earliest_evidence_date"] = sat_evidence.pre_event_date
            if sat_evidence.post_event_date and (not timestamps["latest_evidence_date"] or sat_evidence.post_event_date > timestamps["latest_evidence_date"]):
                timestamps["latest_evidence_date"] = sat_evidence.post_event_date

        return DisasterIntelligenceResult(
            question=question,
            answer=response.answer,
            evidence=chunks,
            source_urls=source_urls,
            disaster_events=events,
            timestamps=timestamps,
            uncertainty_or_limitations=response.uncertainty_or_limitations,
            model_used=response.model_used,
            offline_mode=response.offline_mode,
            disaster_context=disaster_context,
            satellite_evidence=sat_evidence.to_dict() if sat_evidence else None,
            satellite_match_status=sat_match_status,
            cited_sources=response.cited_sources,
        )
