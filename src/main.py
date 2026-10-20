"""
Main entry point and CLI runner for Phase 1: Tavily Search Integration.
Accepts disaster search queries, queries Tavily, and displays results.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure project root is in sys.path for direct script execution ('python src/main.py')
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.config import ConfigurationError
from src.tavily_client import (
    AuthenticationError,
    InvalidQueryError,
    MissingKeyError,
    NetworkOrAPIError,
    RateLimitError,
    TavilySearchError,
    TavilySearchService,
)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Phase 1: Tavily Search Integration for Rapid Post-Disaster Intelligence",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Disaster-related search query (e.g. 'Kerala floods August 2018'). "
             "If omitted, prompts interactively.",
    )
    parser.add_argument(
        "-q", "--query-flag",
        dest="flag_query",
        default=None,
        help="Explicit search query flag (alternative to positional argument).",
    )
    parser.add_argument(
        "-n", "--max-results",
        type=int,
        default=5,
        help="Maximum number of search results to retrieve.",
    )
    parser.add_argument(
        "-d", "--depth",
        choices=["basic", "advanced"],
        default="advanced",
        help="Tavily search depth. 'advanced' performs deeper multi-source extraction.",
    )
    parser.add_argument(
        "-t", "--topic",
        choices=["general", "news"],
        default="news",
        help="Tavily search topic. 'news' is optimized for recent and historical disaster events.",
    )
    parser.add_argument(
        "-a", "--answer",
        action="store_true",
        help="Request a synthesized direct disaster overview from Tavily.",
    )
    parser.add_argument(
        "--no-optimize",
        action="store_true",
        help="Disable automatic disaster query entity extraction and optimization.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response instead of human-readable report (for downstream pipelines).",
    )
    parser.add_argument(
        "--unified", "--pipeline",
        dest="unified",
        action="store_true",
        help="Run the Unified Disaster Intelligence Pipeline (aggregating Tavily, USGS, GDACS, ReliefWeb, and NASA FIRMS).",
    )
    return parser.parse_args()


def run_search(
    service: TavilySearchService,
    query: str,
    max_results: int,
    depth: str,
    topic: str,
    include_answer: bool = False,
    optimize_query: bool = True,
    as_json: bool = False,
) -> int:
    """
    Executes a single search and prints formatted output.
    Returns 0 on success, 1 on error.
    """
    try:
        response = service.search(
            query=query,
            max_results=max_results,
            search_depth=depth,
            topic=topic,
            include_answer=include_answer,
            optimize_query=optimize_query,
        )

        if as_json:
            print(response.model_dump_json(indent=2))
        else:
            print(service.format_results_for_display(response))

        return 0

    except InvalidQueryError as err:
        print(f"\n[Validation Error] {err}", file=sys.stderr)
        return 1
    except AuthenticationError as err:
        print(f"\n[Authentication Error] {err}", file=sys.stderr)
        print("Please verify the TAVILY_API_KEY in your .env file.", file=sys.stderr)
        return 1
    except RateLimitError as err:
        print(f"\n[Rate Limit Exceeded] {err}", file=sys.stderr)
        return 1
    except NetworkOrAPIError as err:
        print(f"\n[API / Network Error] {err}", file=sys.stderr)
        return 1
    except TavilySearchError as err:
        print(f"\n[Search Error] {err}", file=sys.stderr)
        return 1


def main() -> int:
    """Main CLI execution flow."""
    args = parse_arguments()

    # Determine query: positional arg, flag, or interactive prompt
    query = args.query or args.flag_query

    # Initialize service (handles missing key detection)
    try:
        service = TavilySearchService()
    except MissingKeyError as err:
        print("\n" + "=" * 70, file=sys.stderr)
        print(" [!] CONFIGURATION ERROR: TAVILY API KEY NOT CONFIGURED", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(f" Details: {err}\n", file=sys.stderr)
        print(" How to fix:", file=sys.stderr)
        print("   1. Create a .env file in the project root:", file=sys.stderr)
        print("      copy .env.example .env", file=sys.stderr)
        print("   2. Open .env and set your real Tavily API key:", file=sys.stderr)
        print("      TAVILY_API_KEY=tvly-xxxxxxxxxxxx", file=sys.stderr)
        print("   3. Get a key at https://app.tavily.com if you do not have one.\n", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        return 1

    # If query was provided via CLI argument, run once and exit
    if query:
        if args.unified:
            from src.pipeline import DisasterPipeline
            pipeline = DisasterPipeline(tavily_service=service)
            report = pipeline.process_query(
                query=query,
                tavily_max_results=args.max_results,
            )
            if args.json:
                print(report.model_dump_json(indent=2))
            else:
                print(DisasterPipeline.format_unified_report_for_display(report))
            return 0

        return run_search(
            service=service,
            query=query,
            max_results=args.max_results,
            depth=args.depth,
            topic=args.topic,
            include_answer=args.answer,
            optimize_query=not args.no_optimize,
            as_json=args.json,
        )

    # Otherwise run in interactive loop
    print("=" * 70)
    print(" Rapid Post-Disaster Intelligence - Phase 1: Tavily Search")
    print("=" * 70)
    print(" Enter a disaster search query (or type 'exit' / 'quit' to stop):")
    print(" Example: 'Kerala floods August 2018' or 'Turkey earthquake February 2023'")
    print("-" * 70)

    try:
        while True:
            try:
                user_input = input("\nDisaster Query > ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "q"}:
                print("Exiting search service. Goodbye!")
                break

            run_search(
                service=service,
                query=user_input,
                max_results=args.max_results,
                depth=args.depth,
                topic=args.topic,
                include_answer=args.answer,
                optimize_query=not args.no_optimize,
                as_json=args.json,
            )

    except KeyboardInterrupt:
        print("\nSearch interrupted by user. Goodbye!")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
