#!/usr/bin/env python3
"""
CLI Script: Query the RAG system with a question.

Usage:
    python scripts/query_rag.py "How does Sentinel-1 detect floods?"
    python scripts/query_rag.py "What happened during the Turkey earthquake?" --top-k 8
    python scripts/query_rag.py "Cyclone impact on Bangladesh" --region Bangladesh
    python scripts/query_rag.py --interactive    # continuous Q&A session

This script must be run from the project root directory.
Requires the vector index to be built first: python scripts/build_index.py
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,  # Keep output clean for users
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("query_rag")


def build_rag(persist_dir: str, top_k: int, final_k: int, model: str | None = None):
    from rag.pipeline import DisasterRAGPipeline

    pipeline = DisasterRAGPipeline(
        persist_dir=persist_dir,
        top_k=top_k,
        final_k=final_k,
        model=model,
    )

    if pipeline.store.count() == 0:
        print(
            "\n❌ Vector index is empty!\n"
            "   Build the index first:\n"
            "   python scripts/build_index.py --create-fixtures\n"
        )
        sys.exit(1)

    return pipeline


def ask(
    pipeline,
    question: str,
    region_filter: str | None = None,
    hazard_filter: str | None = None,
    disaster_context: dict | None = None,
    json_output: bool = False,
):
    import json

    result = pipeline.query(
        question=question,
        disaster_context=disaster_context,
        region_filter=region_filter,
        hazard_filter=hazard_filter,
    )

    if json_output:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.display())


def main():
    import json

    parser = argparse.ArgumentParser(
        description="Query the Disaster Intelligence RAG system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/query_rag.py "How is Sentinel-1 used for flood detection?"
  python scripts/query_rag.py "What is the impact of cyclone Mocha?" --top-k 8
  python scripts/query_rag.py "What floods occurred in Mexico?" --region Mexico --hazard flood
  python scripts/query_rag.py "Recent disaster summary" --json
  python scripts/query_rag.py --interactive
        """,
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Question to answer (omit for --interactive mode)",
    )
    parser.add_argument(
        "--persist-dir",
        default="data/chroma_db",
        help="ChromaDB directory (default: data/chroma_db)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model override (e.g. gemini-1.5-pro, gpt-4o, gpt-4o-mini)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of candidate chunks to retrieve (default: 10)",
    )
    parser.add_argument(
        "--final-k",
        type=int,
        default=5,
        help="Number of chunks after re-ranking (default: 5)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Optional region/country filter (e.g. 'Mexico', 'Spain', 'Turkey')",
    )
    parser.add_argument(
        "--hazard",
        default=None,
        help="Optional hazard filter (e.g. 'flood', 'earthquake', 'wildfire', 'cyclone')",
    )
    parser.add_argument(
        "--context",
        default=None,
        help="Operational disaster context JSON string (e.g. '{\"hazard\": \"flood\", \"location\": \"Valencia\"}')",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON (ideal for backend API / Copernicus integration)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run an interactive Q&A session",
    )
    args = parser.parse_args()

    if not args.question and not args.interactive:
        parser.print_help()
        sys.exit(0)

    disaster_context = None
    if args.context:
        context_str = args.context
        context_path = Path(context_str)
        if context_path.exists() and context_path.is_file():
            try:
                disaster_context = json.loads(context_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to read context file %s: %s", context_path, exc)
                sys.exit(1)
        else:
            try:
                disaster_context = json.loads(context_str)
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse --context JSON: %s", exc)
                sys.exit(1)

    if not args.json:
        print("⏳ Loading RAG system (first run downloads embedding model ~90 MB) ...")
    pipeline = build_rag(args.persist_dir, args.top_k, args.final_k, model=args.model)
    if not args.json:
        print(f"✅ Index loaded ({pipeline.store.count()} chunks)\n")

    if args.interactive:
        print("🛰️  Disaster Intelligence RAG — Interactive Mode")
        print("   Type your question and press Enter. Type 'exit' to quit.\n")
        while True:
            try:
                question = input("❓ Question: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break
            if question.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
            if not question:
                continue
            ask(
                pipeline,
                question,
                region_filter=args.region,
                hazard_filter=args.hazard,
                disaster_context=disaster_context,
                json_output=args.json,
            )
    else:
        ask(
            pipeline,
            args.question,
            region_filter=args.region,
            hazard_filter=args.hazard,
            disaster_context=disaster_context,
            json_output=args.json,
        )


if __name__ == "__main__":
    main()
