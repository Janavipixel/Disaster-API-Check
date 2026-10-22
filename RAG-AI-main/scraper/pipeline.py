"""
Main scraper orchestration pipeline.

Coordinates HTML, RSS, API, and Tavily scrapers.
Validates, deduplicates, and saves documents to JSONL.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from processor.deduplicator import Deduplicator
from processor.validator import DisasterDocument
from scraper.api_scraper import APIClient
from scraper.base_scraper import HTMLScraper
from scraper.rss_scraper import RSSScraper
from scraper.tavily_scraper import TavilyScraper

logger = logging.getLogger(__name__)


def load_sources(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_jsonl(docs: List[DisasterDocument], output_path: Path, append: bool = True) -> int:
    """
    Save documents to a JSONL file.
    Returns the number of documents written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"

    # If appending to an existing non-empty file, ensure it ends with a newline
    if append and output_path.exists() and output_path.stat().st_size > 0:
        try:
            with output_path.open("rb+") as f:
                f.seek(-1, 2)
                last_char = f.read(1)
                if last_char not in (b"\n", b"\r"):
                    f.write(b"\n")
        except Exception:
            pass

    written = 0
    with output_path.open(mode, encoding="utf-8") as f:
        for doc in docs:
            line = doc.model_dump_json()
            f.write(line + "\n")
            written += 1
    return written


class ScraperPipeline:
    """
    Orchestrates all scraper types and produces a clean JSONL output.

    Usage::

        pipeline = ScraperPipeline(
            config_path=Path("config/sources.json"),
            output_path=Path("data/raw_documents.jsonl"),
        )
        docs = pipeline.run()
    """

    def __init__(
        self,
        config_path: Path,
        output_path: Path,
        append: bool = True,
    ):
        self.config_path = config_path
        self.output_path = output_path
        self.append = append
        self.stats: Dict[str, int] = {}

    def run(self) -> List[DisasterDocument]:
        logger.info("═" * 60)
        logger.info("Scraper Pipeline Starting")
        logger.info("Config: %s", self.config_path)
        logger.info("Output: %s", self.output_path)
        logger.info("═" * 60)

        config = load_sources(self.config_path)
        settings = config.get("settings", {})

        # Load deduplication state from existing JSONL
        dedup = Deduplicator.from_jsonl(self.output_path)

        all_docs: List[DisasterDocument] = []

        # ── HTML scraper ──────────────────────────────────────────────────────
        html_sources = config.get("html_sources", [])
        if html_sources:
            logger.info("── HTML Sources (%d configured) ──", len(html_sources))
            html_scraper = HTMLScraper(settings)
            html_docs = html_scraper.scrape_sources(html_sources)
            all_docs.extend(html_docs)

        # ── RSS scraper ───────────────────────────────────────────────────────
        rss_sources = config.get("rss_sources", [])
        if rss_sources:
            logger.info("── RSS Sources (%d configured) ──", len(rss_sources))
            rss_scraper = RSSScraper(settings)
            rss_docs = rss_scraper.scrape_sources(rss_sources)
            all_docs.extend(rss_docs)

        # ── API sources ───────────────────────────────────────────────────────
        api_sources = config.get("api_sources", [])
        if api_sources:
            logger.info("── API Sources (%d configured) ──", len(api_sources))
            api_client = APIClient(settings)
            api_docs = api_client.scrape_sources(api_sources)
            all_docs.extend(api_docs)

        # ── Tavily (optional) ─────────────────────────────────────────────────
        tavily_queries = config.get("tavily_queries", [])
        if any(q.get("enabled") for q in tavily_queries):
            logger.info("── Tavily Queries ──")
            tavily = TavilyScraper(settings)
            tavily_docs = tavily.scrape_queries(tavily_queries)
            all_docs.extend(tavily_docs)

        logger.info("Total raw documents collected: %d", len(all_docs))

        # ── Deduplicate ───────────────────────────────────────────────────────
        new_docs = dedup.filter_new(all_docs)
        self.stats = dedup.stats

        logger.info(
            "Diagnostic Counts: %d genuinely new | %d URL duplicates | "
            "%d content-hash duplicates | %d invalid",
            self.stats["genuinely_new"],
            self.stats["url_duplicates"],
            self.stats["hash_duplicates"],
            self.stats["invalid_documents"],
        )

        # ── Save ──────────────────────────────────────────────────────────────
        if new_docs:
            written = save_jsonl(new_docs, self.output_path, append=self.append)
            logger.info("Saved %d new documents → %s", written, self.output_path)
        else:
            logger.info("No new documents to save.")

        logger.info("═" * 60)
        logger.info("Scraper Pipeline Complete. New documents: %d", len(new_docs))
        logger.info("═" * 60)
        return new_docs
