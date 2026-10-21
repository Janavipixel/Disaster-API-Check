"""
Optional Tavily search/extraction client.

Only active when TAVILY_API_KEY is set. The core pipeline works without it.
Tavily provides web search + content extraction in one API call, which is
useful for finding recent disaster reports not yet in our configured sources.

Docs: https://docs.tavily.com/
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

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


class TavilyScraper:
    """
    Uses Tavily Search API to find and extract disaster-related content.
    Gracefully disabled if TAVILY_API_KEY is not set.
    """

    def __init__(self, settings: Dict):
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        self.rate_limit = settings.get("rate_limit_delay_seconds", 1.5)
        self._client = None
        if self.api_key:
            try:
                from tavily import TavilyClient  # type: ignore
                self._client = TavilyClient(api_key=self.api_key)
                logger.info("Tavily client initialised.")
            except ImportError:
                logger.warning(
                    "TAVILY_API_KEY is set but 'tavily-python' package is not installed. "
                    "Run: pip install tavily-python"
                )
        else:
            logger.info("Tavily scraper disabled (no TAVILY_API_KEY found).")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def scrape_queries(self, queries: List[Dict]) -> List[DisasterDocument]:
        """Run Tavily searches for each enabled query config."""
        if not self.is_available:
            logger.info("Skipping Tavily queries (client not available).")
            return []

        results: List[DisasterDocument] = []
        enabled = [q for q in queries if q.get("enabled", False)]
        logger.info("Tavily: running %d queries", len(enabled))

        for query_cfg in enabled:
            try:
                docs = self._run_query(query_cfg)
                results.extend(docs)
                logger.info("✅ Tavily: %d results for '%s'", len(docs), query_cfg.get("query"))
            except Exception as exc:
                logger.error("❌ Tavily query failed '%s': %s", query_cfg.get("query"), exc)
            finally:
                time.sleep(self.rate_limit)

        return results

    def _run_query(self, query_cfg: Dict) -> List[DisasterDocument]:
        query = query_cfg["query"]
        response = self._client.search(
            query=query,
            search_depth="advanced",
            include_raw_content=True,
            max_results=5,
        )
        docs = []
        for result in response.get("results", []):
            try:
                doc = self._result_to_doc(result, query_cfg)
                if doc:
                    docs.append(doc)
            except Exception as exc:
                logger.debug("Skipping Tavily result: %s", exc)
        return docs

    def _result_to_doc(self, result: Dict, query_cfg: Dict) -> Optional[DisasterDocument]:
        url = result.get("url", "")
        if not url:
            return None

        title = clean_title(result.get("title") or "Untitled")
        # Prefer raw_content (full page) over snippet
        raw_text = result.get("raw_content") or result.get("content") or ""
        content = clean_text(raw_text)
        if len(content) < 50:
            content = title

        hazards = detect_hazard_types(content + " " + title)
        region = extract_region(content)

        return DisasterDocument(
            document_id=make_document_id(url),
            title=title,
            source_url=url,
            source_type=SourceType.UNKNOWN,
            publisher=result.get("source"),
            hazard_types=hazards,
            region=region,
            content_type=ContentType.UNKNOWN,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            content=content,
            verification_status=VerificationStatus.PENDING,
            tags=query_cfg.get("tags", []),
        )
