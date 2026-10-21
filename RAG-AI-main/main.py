#!/usr/bin/env python3
"""
End-to-end demo of the Disaster Intelligence Scraper + RAG pipeline.

Demonstrates the full flow:
  1. Creates offline fixture documents (no network required)
  2. Builds the vector index
  3. Runs 5 sample questions through the RAG system
  4. Prints answers with source citations

Run from the project root:
    python main.py
    python main.py --live   # also run the live scraper
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

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

DEMO_QUESTIONS = [
    "How does Sentinel-1 SAR data detect flood inundation?",
    "What were the impacts of the 2023 Turkey-Syria earthquake?",
    "How can Google Earth Engine be used for disaster change detection?",
    "What NASA datasets are useful for wildfire monitoring?",
    "What was the impact of Cyclone Mocha on Myanmar?",
]


def run_demo(live_scrape: bool = False):
    print("\n" + "═" * 70)
    print("  🛰️  DISASTER INTELLIGENCE — Scraper + RAG Pipeline Demo")
    print("═" * 70 + "\n")

    # ── Step 1: Create fixtures ───────────────────────────────────────────────
    print("STEP 1: Creating offline fixture documents ...")
    from scripts.build_index import create_fixtures
    fixture_path = create_fixtures()
    print(f"  ✅ Fixtures ready → {fixture_path}\n")

    # ── Step 2 (optional): Live scraping ─────────────────────────────────────
    if live_scrape:
        print("STEP 2: Running live scraper ...")
        from scraper.pipeline import ScraperPipeline
        pipeline = ScraperPipeline(
            config_path=Path("config/sources.json"),
            output_path=Path("data/raw_documents.jsonl"),
            append=True,
        )
        docs = pipeline.run()
        print(f"  ✅ Scraped {len(docs)} new documents\n")
        jsonl_path = Path("data/raw_documents.jsonl")
    else:
        print("STEP 2: Skipping live scraper (using fixtures). Use --live to enable.\n")
        jsonl_path = fixture_path

    # ── Step 3: Build index ───────────────────────────────────────────────────
    print("STEP 3: Building vector index ...")
    from scripts.build_index import load_jsonl
    from rag.chunker import chunk_documents
    from rag.embedder import Embedder
    from rag.vector_store import VectorStore

    docs = load_jsonl(jsonl_path)
    chunks = chunk_documents(docs, chunk_size=512, overlap=64)
    print(f"  📄 {len(docs)} documents → {len(chunks)} chunks")

    embedder = Embedder()
    store = VectorStore(embedder=embedder, persist_dir="data/chroma_db")
    added = store.add_chunks(chunks)
    print(f"  ✅ {added} chunks indexed. Total in store: {store.count()}\n")

    # ── Step 4: RAG Q&A ───────────────────────────────────────────────────────
    print("STEP 4: Running RAG question-answering ...\n")
    from rag.retriever import Retriever
    from rag.generator import Generator

    retriever = Retriever(vector_store=store, top_k=10, final_k=4)
    generator = Generator()

    for i, question in enumerate(DEMO_QUESTIONS, 1):
        print(f"[{i}/{len(DEMO_QUESTIONS)}] Processing question ...")
        chunks_retrieved = retriever.retrieve(question)
        context = retriever.format_context(chunks_retrieved)
        response = generator.generate(
            question=question,
            chunks=chunks_retrieved,
            context=context,
        )
        print(response.display())

    print("\n" + "═" * 70)
    print("  ✅ Demo complete!")
    print("  💡 Next steps:")
    print("     • Set GOOGLE_API_KEY or OPENAI_API_KEY in .env for AI answers")
    print("     • Run live scraper: python scripts/run_scraper.py")
    print("     • Interactive Q&A: python scripts/query_rag.py --interactive")
    print("═" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Disaster Intelligence RAG Demo")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run the live web scraper in addition to fixtures",
    )
    args = parser.parse_args()
    run_demo(live_scrape=args.live)


if __name__ == "__main__":
    main()
