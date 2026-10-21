"""
Pydantic schema and validation for scraped disaster-intelligence documents.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    OFFICIAL_DOCUMENTATION = "official_documentation"
    DISASTER_REPORT = "disaster_report"
    NEWS_ARTICLE = "news_article"
    RSS_FEED = "rss_feed"
    API_RESPONSE = "api_response"
    FIXTURE = "fixture"
    UNKNOWN = "unknown"


class ContentType(str, Enum):
    TECHNICAL_DOCUMENTATION = "technical_documentation"
    DISASTER_ALERT = "disaster_alert"
    DISASTER_REPORT = "disaster_report"
    SITUATION_REPORT = "situation_report"
    NEWS_ARTICLE = "news_article"
    GUIDE = "guide"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    FIXTURE = "fixture"


HAZARD_TYPES = {
    "flood", "earthquake", "cyclone", "typhoon", "hurricane",
    "wildfire", "fire", "tsunami", "landslide", "drought",
    "volcano", "volcanic_eruption", "storm", "tornado", "avalanche",
    "chemical", "biological", "nuclear", "industrial_accident",
}


# ─────────────────────────────────────────────────────────────────────────────
# Document Schema
# ─────────────────────────────────────────────────────────────────────────────

class DisasterDocument(BaseModel):
    """
    Canonical schema for one scraped document in the Disaster Intelligence pipeline.
    One instance = one JSON line in the JSONL output.
    """

    # Identity
    document_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable unique identifier. Derived from URL when possible.",
    )
    title: str = Field(..., min_length=1, description="Actual extracted page title.")
    source_url: str = Field(..., description="Canonical URL of the scraped page.")
    source_type: SourceType = Field(default=SourceType.UNKNOWN)
    publisher: Optional[str] = Field(default=None)

    # Disaster metadata
    hazard_types: List[str] = Field(
        default_factory=list,
        description="Detected hazard categories, e.g. ['flood', 'earthquake'].",
    )
    region: Optional[str] = Field(
        default=None,
        description="Country, state, or region name extracted from content.",
    )
    coordinates: Optional[List[float]] = Field(
        default=None,
        description="[latitude, longitude] only if explicitly present in source.",
    )
    event_date: Optional[str] = Field(
        default=None,
        description="ISO-8601 date of the disaster event, if explicitly stated.",
    )

    # Document metadata
    content_type: ContentType = Field(default=ContentType.UNKNOWN)
    published_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 publication date of the article/page.",
    )
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp when this document was fetched.",
    )

    # Content
    content: str = Field(..., min_length=1, description="Cleaned extracted text.")
    content_hash: str = Field(
        default="",
        description="SHA-256 of the content string. Auto-computed if empty.",
    )

    # Quality
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.PENDING
    )
    tags: List[str] = Field(default_factory=list)
    language: Optional[str] = Field(default=None)
    word_count: int = Field(default=0)

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https", "file"):
            raise ValueError(f"Invalid URL scheme: {v}")
        return v

    @field_validator("hazard_types")
    @classmethod
    def normalise_hazards(cls, v: List[str]) -> List[str]:
        return [h.lower().replace(" ", "_") for h in v]

    @field_validator("coordinates")
    @classmethod
    def validate_coords(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is None:
            return None
        if len(v) != 2:
            raise ValueError("coordinates must be [latitude, longitude]")
        lat, lon = v
        if not (-90 <= lat <= 90):
            raise ValueError(f"Latitude {lat} out of range")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Longitude {lon} out of range")
        return v

    @model_validator(mode="after")
    def compute_derived_fields(self) -> "DisasterDocument":
        # Auto-compute content hash
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                self.content.encode("utf-8")
            ).hexdigest()

        # Auto-compute word count
        if self.word_count == 0:
            self.word_count = len(self.content.split())

        # Generate stable document_id from URL if it looks like a UUID default
        if len(self.document_id) == 36 and self.document_id[8] == "-":
            # Replace with URL-based ID if possible
            url_hash = hashlib.sha256(self.source_url.encode()).hexdigest()[:16]
            self.document_id = f"doc_{url_hash}"

        return self


def make_document_id(url: str) -> str:
    """Generate a stable document ID from a URL."""
    return "doc_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def detect_hazard_types(text: str) -> List[str]:
    """
    Simple keyword-based hazard detection from text.
    Returns a sorted deduplicated list of detected hazard types.
    No LLM required.
    """
    text_lower = text.lower()
    found = set()
    for hazard in HAZARD_TYPES:
        keyword = hazard.replace("_", " ")
        if keyword in text_lower or hazard in text_lower:
            found.add(hazard)
    # Merge synonyms
    if "typhoon" in found or "hurricane" in found:
        found.add("cyclone")
    if "fire" in found and "wildfire" not in found:
        if "wild" in text_lower:
            found.add("wildfire")
            found.discard("fire")
    return sorted(found)


def extract_region(text: str) -> Optional[str]:
    """
    Lightweight region detection: find country names in the first 500 chars.
    Returns the first match or None. Does NOT geocode.
    """
    COUNTRIES = [
        "Afghanistan", "Bangladesh", "Brazil", "China", "Ethiopia",
        "Haiti", "India", "Indonesia", "Japan", "Kenya", "Myanmar",
        "Nepal", "Nigeria", "Pakistan", "Philippines", "Somalia",
        "Sudan", "Syria", "Turkey", "United States", "USA", "Vietnam",
        "Yemen", "Mozambique", "Madagascar", "Australia",
    ]
    snippet = text[:500]
    for country in COUNTRIES:
        if re.search(rf"\b{re.escape(country)}\b", snippet, re.IGNORECASE):
            return country
    return None
