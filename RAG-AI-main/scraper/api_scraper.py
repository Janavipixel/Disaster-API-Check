"""
ReliefWeb REST API client.

Uses the official ReliefWeb API v2 to fetch disaster records.
Per official ReliefWeb documentation (https://apidoc.reliefweb.int/parameters#appname):
Requests to the v2 API require an approved application identifier parameter ('appname').
Users can register and set RELIEFWEB_APPNAME in their .env file.
If unapproved or missing, requests are handled gracefully without stopping the pipeline.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

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

RELIEFWEB_API_BASE = "https://api.reliefweb.int/v2"


class APIClient:
    """
    Fetches disaster data from documented REST APIs.
    Currently supports: ReliefWeb API v2.
    """

    def __init__(self, settings: Dict):
        self.timeout = settings.get("request_timeout_seconds", 20)
        self.rate_limit = settings.get("rate_limit_delay_seconds", 1.5)
        user_agent = settings.get(
            "user_agent",
            "DisasterIntelligenceBot/1.0 (academic research; contact: research@example.edu)",
        )
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def scrape_sources(self, sources: List[Dict]) -> List[DisasterDocument]:
        """Fetch all enabled API sources."""
        results: List[DisasterDocument] = []
        enabled = [s for s in sources if s.get("enabled", True)]
        logger.info("API client: %d enabled sources", len(enabled))

        for source in enabled:
            try:
                docs = self._fetch_source(source)
                results.extend(docs)
                logger.info("✅ API: %d records from %s", len(docs), source.get("name"))
            except Exception as exc:
                logger.error("❌ API failed for %s: %s", source.get("name"), exc)
            finally:
                time.sleep(self.rate_limit)

        return results

    def _fetch_source(self, source: Dict) -> List[DisasterDocument]:
        base_url = source.get("base_url", RELIEFWEB_API_BASE)
        params_cfg = source.get("params", {})
        endpoint = params_cfg.get("endpoint", "disasters")
        limit = params_cfg.get("limit", 20)
        fields = params_cfg.get("fields", ["name", "description", "date", "country", "type", "url"])

        appname = os.environ.get("RELIEFWEB_APPNAME") or source.get("appname", "")
        if not appname:
            # Per official docs, an appname is required. Use default bot identifier if none provided.
            appname = "disaster-intelligence-rag"

        url = f"{base_url}/{endpoint}"
        query_params = {"appname": appname}

        payload = {
            "limit": limit,
            "fields": {"include": fields},
            "sort": ["date:desc"],
        }

        try:
            resp = self._session.post(
                url, params=query_params, json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.HTTPError as err:
            status = err.response.status_code if err.response is not None else None
            if status == 403:
                logger.warning(
                    "ReliefWeb API v2 requires an approved appname token (HTTP 403). "
                    "Current appname '%s' is not registered. Set RELIEFWEB_APPNAME in your .env "
                    "after registering at: https://apidoc.reliefweb.int/parameters#appname. "
                    "Skipping ReliefWeb API ingestion gracefully.",
                    appname,
                )
                return []
            elif status == 400:
                err_msg = ""
                try:
                    err_msg = err.response.json().get("error", {}).get("message", "")
                except Exception:
                    pass
                logger.warning(
                    "ReliefWeb API v2 returned HTTP 400 Bad Request (%s). "
                    "An approved 'appname' parameter is mandatory for ReliefWeb API v2. "
                    "Set RELIEFWEB_APPNAME in .env. Skipping ReliefWeb API ingestion gracefully.",
                    err_msg or str(err),
                )
                return []
            elif status == 410:
                logger.warning(
                    "ReliefWeb API endpoint %s returned HTTP 410 Gone (deprecated). "
                    "Please use ReliefWeb API v2.",
                    url,
                )
                return []
            else:
                logger.error("API HTTP error for %s: %s", source.get("name"), err)
                return []

        items = data.get("data", [])
        docs = []
        for item in items:
            try:
                doc = self._record_to_doc(item, source)
                if doc:
                    docs.append(doc)
            except Exception as exc:
                logger.debug("Skipping API record %s: %s", item.get("id"), exc)
        return docs

    def _record_to_doc(self, item: Dict, source: Dict) -> Optional[DisasterDocument]:
        fields = item.get("fields", {})
        item_id = str(item.get("id", ""))

        # Title
        name = fields.get("name") or f"Disaster Event #{item_id}"
        title = clean_title(name)

        # Content: combine name + description
        description = fields.get("description", "") or ""
        content = clean_text(f"{name}\n\n{description}".strip())
        if not content:
            content = title

        # Dates
        date_info = fields.get("date", {}) or {}
        event_date = date_info.get("event") or date_info.get("created")
        published_at = date_info.get("created")

        # Location
        countries = fields.get("country", []) or []
        region = None
        if countries:
            if isinstance(countries, list):
                region = ", ".join(c.get("name", "") for c in countries if c.get("name"))
            elif isinstance(countries, dict):
                region = countries.get("name")

        primary_country = fields.get("primary_country", {}) or {}
        if not region and primary_country:
            region = primary_country.get("name")

        # Hazard type from ReliefWeb 'type' field
        rw_types = fields.get("type", []) or []
        hazard_types = []
        if isinstance(rw_types, list):
            for t in rw_types:
                name_str = t.get("name", "").lower() if isinstance(t, dict) else str(t).lower()
                hazard_types.append(name_str.replace(" ", "_"))
        elif isinstance(rw_types, str):
            hazard_types = [rw_types.lower().replace(" ", "_")]

        # Also auto-detect from text
        hazard_types = list(set(hazard_types + detect_hazard_types(content)))
        if not region:
            region = extract_region(content)

        # Source URL
        source_url = fields.get("url") or f"{RELIEFWEB_API_BASE}/disasters/{item_id}"

        return DisasterDocument(
            document_id=make_document_id(source_url),
            title=title,
            source_url=source_url,
            source_type=SourceType.API_RESPONSE,
            publisher=source.get("publisher", "OCHA ReliefWeb"),
            hazard_types=sorted(set(hazard_types)),
            region=region,
            content_type=ContentType(source.get("content_type", "disaster_report")),
            published_at=published_at,
            event_date=event_date,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            content=content,
            verification_status=VerificationStatus.PENDING,
            tags=source.get("tags", []),
        )
