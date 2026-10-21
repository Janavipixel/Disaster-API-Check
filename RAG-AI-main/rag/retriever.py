"""
RAG Retriever — finds the most relevant chunks for a question.

Combines vector similarity search with disaster intelligence re-ranking:
  - Exact keyword matching for query terms
  - Geographic/location relevance boost (e.g., Mexico, Spain, Turkey)
  - Hazard-type relevance boost (e.g., flood, earthquake, wildfire, cyclone)
  - Satellite/SAR technical term boosting (Sentinel-1, backscatter, change detection)
  - Temporal/freshness weighting for event dates
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

COMMON_HAZARDS = {
    "flood", "flooding", "floods",
    "earthquake", "earthquakes", "quake", "seismic",
    "wildfire", "wildfires", "fire", "bushfire", "forest fire",
    "cyclone", "cyclones", "hurricane", "typhoon", "storm",
    "tsunami", "tsunamis",
    "volcano", "volcanic", "eruption",
    "drought", "droughts",
}

SAR_KEYWORDS = {
    "sentinel", "sentinel-1", "sar", "radar", "copernicus",
    "backscatter", "c-band", "synthetic aperture", "change detection",
    "inundation", "damage assessment", "earthdata", "earth engine",
}


def _keyword_boost(text: str, query: str, boost: float = 0.04) -> float:
    """
    Add a small boost to the relevance score for each query keyword
    that appears in the chunk text.
    """
    words = re.findall(r"\w+", query.lower())
    text_lower = text.lower()
    matched = sum(1 for w in words if w in text_lower and len(w) > 3)
    return min(boost * matched, 0.15)


def _disaster_intelligence_boost(chunk: Dict, query: str) -> float:
    """
    Domain-specific re-ranking boost for disaster intelligence:
      1. Geographic location match (+0.10)
      2. Hazard type match (+0.08)
      3. Satellite / SAR technical match (+0.06)
      4. Temporal match (+0.04)
    """
    query_lower = query.lower()
    boost = 0.0
    meta = chunk.get("metadata", {})
    text_lower = chunk.get("text", "").lower()

    # 1. Location match
    region = str(meta.get("region", "")).lower()
    if region and region != "unknown" and region != "global":
        if region in query_lower:
            boost += 0.10
        elif any(part.strip() in query_lower for part in region.split(",") if len(part.strip()) > 3):
            boost += 0.08

    # 2. Hazard match
    hazards_meta = str(meta.get("hazard_types", "")).lower()
    for hazard in COMMON_HAZARDS:
        if hazard in query_lower:
            if hazard in hazards_meta or hazard in text_lower:
                boost += 0.08
                break

    # 3. Satellite / SAR match
    for kw in SAR_KEYWORDS:
        if kw in query_lower:
            if kw in text_lower or kw in str(meta.get("tags", "")).lower():
                boost += 0.06
                break

    # 4. Temporal match (e.g. query specifies 2023, 2024, 2026 or "recent")
    years_in_query = re.findall(r"\b20\d{2}\b", query)
    event_date = str(meta.get("event_date", ""))
    pub_date = str(meta.get("published_at", ""))
    for y in years_in_query:
        if y in event_date or y in pub_date or y in text_lower:
            boost += 0.04
            break

    if "recent" in query_lower or "latest" in query_lower:
        if "2026" in pub_date or "2026" in event_date or "2026" in text_lower:
            boost += 0.04

    return min(boost, 0.25)


def extract_disaster_events(chunks: List[Dict]) -> List[Dict]:
    """
    Extract structured disaster events from retrieved chunks for downstream
    integration with GIS, backend APIs, or Copernicus acquisition services.
    """
    events = []
    seen = set()

    coord_pattern = re.compile(r"Coordinates:\s*\[([-\d.]+),\s*([-\d.]+)\]")
    severity_pattern = re.compile(r"Severity:\s*([^.\n]+)")
    population_pattern = re.compile(r"Affected Population:\s*([^.\n]+)")
    event_id_pattern = re.compile(r"Event ID:\s*([A-Za-z0-9_-]+)")

    for c in chunks:
        meta = c.get("metadata", {})
        text = c.get("text", "")
        url = meta.get("source_url", "")
        title = meta.get("title", "")

        # Look for explicit event indicators
        event_id_match = event_id_pattern.search(text)
        coord_match = coord_pattern.search(text)
        sev_match = severity_pattern.search(text)
        pop_match = population_pattern.search(text)

        key = event_id_match.group(1).strip() if event_id_match else (url or title)
        if key in seen:
            continue
        seen.add(key)

        coordinates = None
        if coord_match:
            try:
                coordinates = [float(coord_match.group(1)), float(coord_match.group(2))]
            except ValueError:
                pass

        hazard_str = meta.get("hazard_types", "")
        hazards = [h.strip() for h in hazard_str.split(",") if h.strip()] if isinstance(hazard_str, str) else []

        event_record = {
            "title": title,
            "source_url": url,
            "event_id": event_id_match.group(1).strip() if event_id_match else None,
            "hazard_types": hazards,
            "region": meta.get("region") or None,
            "event_date": meta.get("event_date") or None,
            "published_at": meta.get("published_at") or None,
            "coordinates": coordinates,
            "severity": sev_match.group(1).strip() if sev_match else None,
            "affected_population": pop_match.group(1).strip() if pop_match else None,
            "relevance_score": c.get("relevance_score", 0.0),
        }
        events.append(event_record)

    return events


class Retriever:
    """
    Retrieves and re-ranks chunks from the vector store with disaster intelligence.

    Parameters
    ----------
    vector_store : VectorStore
        Initialised and populated vector store.
    top_k : int
        Number of candidate chunks to retrieve before re-ranking.
    final_k : int
        Number of chunks to return after re-ranking.
    min_relevance : float
        Discard chunks below this cosine-based relevance score.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        top_k: int = 10,
        final_k: int = 5,
        min_relevance: float = 0.20,
    ):
        self.store = vector_store
        self.top_k = top_k
        self.final_k = final_k
        self.min_relevance = min_relevance

    def retrieve(
        self,
        query: str,
        where: Optional[Dict] = None,
        region: Optional[str] = None,
        hazard_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve and re-rank the best chunks for a query.

        Parameters
        ----------
        query : str
            User question or search phrase.
        where : Optional[Dict]
            Custom ChromaDB filter dict.
        region : Optional[str]
            Optional region to filter chunks.
        hazard_type : Optional[str]
            Optional hazard type to filter chunks.

        Returns
        -------
        List[Dict]
            Re-ranked list of chunk dicts with boosted relevance_score.
        """
        if self.store.count() == 0:
            logger.warning("Vector store is empty. Run build_index.py first.")
            return []

        # Construct ChromaDB where filter
        clauses = []
        if where:
            if "$and" in where and isinstance(where["$and"], list):
                clauses.extend(where["$and"])
            else:
                clauses.append(where)
        if region:
            clauses.append({"region": region})
        if hazard_type:
            clauses.append({"hazard_types": hazard_type})

        final_where = None
        if len(clauses) == 1:
            final_where = clauses[0]
        elif len(clauses) > 1:
            final_where = {"$and": clauses}

        # Step 1: vector similarity search
        candidates = self.store.query(
            query_text=query,
            n_results=self.top_k,
            where=final_where,
        )

        # Fall back to unconstrained semantic search if strict metadata filter yields 0 matches
        if not candidates and final_where is not None:
            logger.info("Strict metadata filter yielded 0 results; falling back to unconstrained semantic search")
            candidates = self.store.query(
                query_text=query,
                n_results=self.top_k,
                where=None,
            )

        # Step 2: Disaster intelligence + keyword re-scoring
        for c in candidates:
            kw_boost = _keyword_boost(c["text"], query)
            di_boost = _disaster_intelligence_boost(c, query)
            c["relevance_score"] = min(1.0, c["relevance_score"] + kw_boost + di_boost)

        # Step 3: filter low-relevance chunks
        candidates = [c for c in candidates if c["relevance_score"] >= self.min_relevance]

        # Step 4: sort by final score descending
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Step 5: return top final_k
        result = candidates[: self.final_k]
        logger.info(
            "Retrieved %d chunks for query '%s...'",
            len(result),
            query[:60],
        )
        return result

    def format_context(
        self,
        chunks: List[Dict],
        disaster_context: Optional[Dict] = None,
    ) -> str:
        """
        Format retrieved chunks and optional operational disaster context
        into a clean context block for the LLM prompt.
        """
        parts = []

        # Operational context from teammate's system or Copernicus if present
        if disaster_context:
            ctx_lines = ["## Operational Disaster Context (Copernicus / Sensor Feed)"]
            for k, v in disaster_context.items():
                k_clean = k.replace("_", " ").title()
                ctx_lines.append(f"- {k_clean}: {v}")
            parts.append("\n".join(ctx_lines))

        if not chunks:
            if parts:
                parts.append("## Retrieved Documents\nNo additional documents found in knowledge base.")
                return "\n\n".join(parts)
            return "No relevant documents found in the knowledge base."

        doc_parts = []
        for i, chunk in enumerate(chunks, 1):
            meta = chunk["metadata"]
            title = meta.get("title", "Unknown")
            url = meta.get("source_url", "")
            score = chunk["relevance_score"]
            text = chunk["text"]
            region = meta.get("region")
            date = meta.get("event_date") or meta.get("published_at")
            header_extra = []
            if region:
                header_extra.append(f"Region: {region}")
            if date:
                header_extra.append(f"Date: {date}")
            extra_str = f" ({', '.join(header_extra)})" if header_extra else ""

            doc_parts.append(
                f"[SOURCE {i}] {title}{extra_str}\n"
                f"URL: {url}\n"
                f"Relevance: {score:.2%}\n"
                f"---\n{text}"
            )

        parts.append("## Retrieved Source Documents\n\n" + "\n\n".join(doc_parts))
        return "\n\n".join(parts)

