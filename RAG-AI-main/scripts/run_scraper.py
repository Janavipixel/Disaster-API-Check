#!/usr/bin/env python3
"""
CLI Script: Run the scraper pipeline.

Usage:
    python scripts/run_scraper.py
    python scripts/run_scraper.py --config config/sources.json --output data/raw_documents.jsonl
    python scripts/run_scraper.py --fresh          # overwrite existing output
    python scripts/run_scraper.py --fixtures-only  # use offline test fixtures (no network)
    python scripts/run_scraper.py --index          # automatically index new docs into ChromaDB

This script must be run from the project root directory.
"""

import argparse
import logging
import sys
from pathlib import Path

# Fix Windows console encoding for Unicode/emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_scraper")


def main():
    parser = argparse.ArgumentParser(
        description="Disaster Intelligence Web Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="config/sources.json",
        help="Path to sources configuration file (default: config/sources.json)",
    )
    parser.add_argument(
        "--output",
        default="data/raw_documents.jsonl",
        help="Output JSONL file path (default: data/raw_documents.jsonl)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Overwrite existing output (default: append/deduplicate)",
    )
    parser.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Use offline test fixtures instead of live scraping",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Automatically index new documents into ChromaDB after scraping",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    output_path = Path(args.output)

    if args.fixtures_only:
        logger.info("Using offline fixtures ...")
        _load_fixtures(output_path)
        if args.index:
            _index_documents(output_path)
        return

    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    from scraper.pipeline import ScraperPipeline

    pipeline = ScraperPipeline(
        config_path=config_path,
        output_path=output_path,
        append=not args.fresh,
    )
    docs = pipeline.run()
    logger.info("Done. %d new documents saved to %s", len(docs), output_path)

    # Optional automatic RAG indexing
    if args.index:
        _index_documents(output_path)


def _load_fixtures(output_path: Path):
    """Copy fixture documents to the output path."""
    import shutil

    fixture_path = Path("data/fixtures/test_documents.jsonl")
    if not fixture_path.exists():
        logger.error(
            "Fixture file not found: %s\n"
            "Run: python scripts/build_index.py --create-fixtures",
            fixture_path,
        )
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_path, output_path)
    count = sum(1 for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip())
    logger.info("Loaded %d fixture documents → %s", count, output_path)


def _index_documents(input_path: Path):
    """Index documents from input_path into ChromaDB."""
    logger.info("Passing documents into ChromaDB vector index ...")
    from rag.chunker import chunk_documents
    from rag.embedder import Embedder
    from rag.vector_store import VectorStore
    from scripts.build_index import load_jsonl

    docs = load_jsonl(input_path)
    if not docs:
        logger.warning("No documents to index.")
        return

    chunks = chunk_documents(docs)
    embedder = Embedder()
    store = VectorStore(embedder=embedder)
    added = store.add_chunks(chunks)
    logger.info("ChromaDB index updated: %d chunks added (Total in store: %d)", added, store.count())


if __name__ == "__main__":
    main()
