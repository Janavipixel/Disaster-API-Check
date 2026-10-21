"""
Base HTTP + Trafilatura scraper for HTML pages.

Fetches each configured URL, extracts readable content using Trafilatura,
cleans the text, and returns a validated DisasterDocument.
Handles errors gracefully without stopping the full scraping run.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
import trafilatura
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from processor.cleaner import clean_text, clean_title, truncate_content
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

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def _build_session(user_agent: str, timeout: int, max_retries: int) -> requests.Session:
    session = requests.Session()
    session.headers.update({**DEFAULT_HEADERS, "User-Agent": user_agent})
    retry = Retry(
        total=max_retries,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class HTMLScraper:
    """
    Fetches HTML pages and extracts readable content with Trafilatura.

    Parameters
    ----------
    settings : dict
        The ``settings`` block from sources.json.
    """

    def __init__(self, settings: Dict):
        self.timeout = settings.get("request_timeout_seconds", 20)
        self.max_retries = settings.get("max_retries", 3)
        self.rate_limit = settings.get("rate_limit_delay_seconds", 1.5)
        self.max_content = settings.get("max_content_length_chars", 50_000)
        self.min_content = settings.get("min_content_length_chars", 100)
        self.user_agent = settings.get(
            "user_agent",
            "DisasterIntelligenceBot/1.0 (Academic Research Project)",
        )
        self._session = _build_session(self.user_agent, self.timeout, self.max_retries)

    # ── Public API ────────────────────────────────────────────────────────────

    def scrape_sources(self, sources: List[Dict]) -> List[DisasterDocument]:
        """Scrape a list of HTML source configs. Returns validated documents."""
        results: List[DisasterDocument] = []
        enabled = [s for s in sources if s.get("enabled", True)]
        logger.info("HTML scraper: %d enabled sources", len(enabled))

        for source in enabled:
            url = source["url"]
            try:
                doc = self._scrape_one(source)
                if doc:
                    results.append(doc)
                    logger.info("✅ Scraped: %s (%d words)", url, doc.word_count)
                else:
                    logger.warning("⚠️  No content extracted from: %s", url)
            except Exception as exc:
                logger.error("❌ Failed to scrape %s: %s", url, exc)
            finally:
                time.sleep(self.rate_limit)

        logger.info("HTML scraper complete: %d documents collected", len(results))
        return results

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch(self, url: str) -> Optional[str]:
        """Fetch raw HTML. Returns None on failure."""
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                logger.warning("Skipping non-HTML content-type '%s' at %s", content_type, url)
                return None
            return resp.text
        except requests.exceptions.Timeout:
            logger.error("Timeout fetching %s", url)
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error("Connection error fetching %s: %s", url, e)
            return None
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error %s fetching %s", e.response.status_code, url)
            return None

    def _extract(self, html: str, url: str) -> Optional[Dict]:
        """Use Trafilatura to extract title, text, date, author."""
        extracted = None
        meta = None

        try:
            extracted = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                output_format="txt",
            )
        except Exception as e:
            logger.debug("Trafilatura text extraction error for %s: %s", url, e)

        try:
            meta = trafilatura.extract_metadata(html, default_url=url)
        except Exception as e:
            logger.debug("Trafilatura metadata error for %s: %s", url, e)

        title = None
        published_at = None
        author = None

        if meta:
            title = meta.title
            if meta.date:
                published_at = meta.date
            if meta.author:
                author = meta.author

        return {
            "text": extracted,
            "title": title,
            "published_at": published_at,
            "author": author,
        }

    def _scrape_one(self, source: Dict) -> Optional[DisasterDocument]:
        url = source["url"]
        html = self._fetch(url)
        if not html:
            return None

        extracted = self._extract(html, url)
        raw_text = extracted.get("text") or ""
        raw_text = clean_text(raw_text)
        raw_text = truncate_content(raw_text, self.max_content)

        if len(raw_text) < self.min_content:
            logger.warning("Content too short (%d chars) at %s", len(raw_text), url)
            return None

        title = clean_title(extracted.get("title") or source.get("name") or url)
        published_at = extracted.get("published_at")
        hazards = detect_hazard_types(raw_text + " " + title)
        region = extract_region(raw_text)

        return DisasterDocument(
            document_id=make_document_id(url),
            title=title,
            source_url=url,
            source_type=SourceType(source.get("source_type", "unknown")),
            publisher=extracted.get("author") or source.get("publisher"),
            hazard_types=hazards,
            region=region,
            content_type=ContentType(source.get("content_type", "unknown")),
            published_at=published_at,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            content=raw_text,
            verification_status=VerificationStatus.PENDING,
            tags=source.get("tags", []),
        )
