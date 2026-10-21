"""
RSS / Atom feed scraper for disaster alerts.

Parses feeds from GDACS, ReliefWeb, NASA, etc. using the feedparser library.
Each feed entry becomes one DisasterDocument.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import feedparser

from processor.cleaner import clean_text, clean_title
from processor.validator import (
    ContentType,
    DisasterDocument,
    SourceType,
    VerificationStatus,
    detect_hazard_types,
    extract_region,
    make_document_id,
)

logger = logging.getLogger(__name__)


def _get_entry_val(entry: Any, key: str, default: Any = None) -> Any:
    """Safely get field from feedparser entry (dict or object) without MagicMock issues."""
    if isinstance(entry, dict):
        val = entry.get(key)
        if val is not None and not isinstance(val, MagicMock):
            return val
    if hasattr(entry, key):
        val = getattr(entry, key)
        if val is not None and not isinstance(val, MagicMock):
            return val
    return default


def _parse_date(entry: Any) -> Optional[str]:
    """Try to extract a publish date from an RSS entry."""
    pub = _get_entry_val(entry, "published_parsed")
    if pub:
        try:
            dt = datetime(*pub[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    upd = _get_entry_val(entry, "updated_parsed")
    if upd:
        try:
            dt = datetime(*upd[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    return None


def _entry_text(entry: Any) -> str:
    """Extract the best available text from a feed entry."""
    # Prefer content field over summary
    content = _get_entry_val(entry, "content")
    if content:
        for c in content:
            if isinstance(c, dict) and c.get("value"):
                return c["value"]
    summary = _get_entry_val(entry, "summary")
    if summary:
        return summary
    description = _get_entry_val(entry, "description")
    if description:
        return description
    return ""


class RSSScraper:
    """
    Parses RSS/Atom feeds and converts entries to DisasterDocument objects.
    """

    def __init__(self, settings: Dict):
        self.rate_limit = settings.get("rate_limit_delay_seconds", 1.5)
        self.min_content = settings.get("min_content_length_chars", 50)

    def scrape_sources(self, sources: List[Dict]) -> List[DisasterDocument]:
        """Parse all enabled RSS sources. Returns validated documents."""
        results: List[DisasterDocument] = []
        enabled = [s for s in sources if s.get("enabled", True)]
        logger.info("RSS scraper: %d enabled sources", len(enabled))

        for source in enabled:
            url = source["url"]
            try:
                docs = self._parse_feed(source)
                results.extend(docs)
                logger.info("✅ RSS: %d entries from %s", len(docs), url)
            except Exception as exc:
                logger.error("❌ RSS failed for %s: %s", url, exc)
            finally:
                time.sleep(self.rate_limit)

        logger.info("RSS scraper complete: %d documents", len(results))
        return results

    def _parse_feed(self, source: Dict) -> List[DisasterDocument]:
        url = source["url"]
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            # bozo=True means malformed feed, but entries might still be present
            logger.warning("Feed may be malformed: %s (bozo_exception=%s)", url, feed.bozo_exception)
            if not feed.entries:
                return []

        docs = []
        for entry in feed.entries:
            try:
                doc = self._entry_to_doc(entry, source)
                if doc:
                    docs.append(doc)
            except Exception as exc:
                logger.debug("Skipping RSS entry: %s", exc)
        return docs

    def _entry_to_doc(
        self, entry: feedparser.util.FeedParserDict, source: Dict
    ) -> Optional[DisasterDocument]:
        # Get entry URL
        entry_url = _get_entry_val(entry, "link") or source["url"]

        # Get title
        raw_title = _get_entry_val(entry, "title") or "Untitled"
        title = clean_title(raw_title)

        # Get text
        raw_text = clean_text(_entry_text(entry))

        # Extract coordinates if explicitly present
        coordinates = None
        lat = _get_entry_val(entry, "geo_lat")
        lon = _get_entry_val(entry, "geo_long")
        if lat is not None and lon is not None:
            try:
                flat, flon = float(lat), float(lon)
                if -90 <= flat <= 90 and -180 <= flon <= 180:
                    coordinates = [flat, flon]
            except (ValueError, TypeError):
                pass
        georss = _get_entry_val(entry, "georss_point")
        if coordinates is None and georss:
            try:
                parts = str(georss).strip().split()
                if len(parts) == 2:
                    flat, flon = float(parts[0]), float(parts[1])
                    if -90 <= flat <= 90 and -180 <= flon <= 180:
                        coordinates = [flat, flon]
            except (ValueError, TypeError):
                pass

        # Enrich text with specific incident parameters so individual events remain distinct
        details = []
        if raw_text:
            details.append(raw_text)

        event_id = _get_entry_val(entry, "gdacs_eventid")
        if event_id:
            details.append(f"Event ID: {event_id}")

        severity = _get_entry_val(entry, "gdacs_severity")
        if isinstance(severity, dict):
            val = severity.get("value")
            unit = severity.get("unit", "")
            if val:
                details.append(f"Severity: {val} {unit}".strip())
        elif severity:
            details.append(f"Severity: {severity}")

        population = _get_entry_val(entry, "gdacs_population")
        if isinstance(population, dict) and population.get("value"):
            details.append(f"Affected Population: {population.get('value')}")

        if coordinates:
            details.append(f"Coordinates: [{coordinates[0]:.4f}, {coordinates[1]:.4f}]")

        content = "\n\n".join(details)
        if len(content) < self.min_content:
            if len(title) < 10:
                return None
            content = title

        # Hazard detection
        combined = title + " " + content
        hazards = detect_hazard_types(combined)
        gdacs_type = str(_get_entry_val(entry, "gdacs_eventtype", "")).upper()
        type_map = {
            "WF": "wildfire",
            "EQ": "earthquake",
            "FL": "flood",
            "TC": "cyclone",
            "VO": "volcano",
            "DR": "drought",
            "TS": "tsunami",
        }
        if gdacs_type in type_map and type_map[gdacs_type] not in hazards:
            hazards.append(type_map[gdacs_type])
        hazards = sorted(set(hazards))

        # Region
        region = _get_entry_val(entry, "gdacs_country") or _get_entry_val(entry, "country")
        if not region:
            region = extract_region(combined)

        published_at = _parse_date(entry)
        event_date = _get_entry_val(entry, "gdacs_fromdate")

        return DisasterDocument(
            document_id=make_document_id(entry_url),
            title=title,
            source_url=entry_url,
            source_type=SourceType.RSS_FEED,
            publisher=source.get("publisher"),
            hazard_types=hazards,
            region=region,
            coordinates=coordinates,
            event_date=event_date,
            content_type=ContentType(source.get("content_type", "unknown")),
            published_at=published_at,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            content=content,
            verification_status=VerificationStatus.PENDING,
            tags=source.get("tags", []),
        )
