"""
Core service for integrating the Tavily Search API.
Provides modular search capabilities, disaster entity extraction, source quality filtering,
multi-source cross-verification, and transparent reporting.
"""

from __future__ import annotations

import logging
import textwrap
import time
from typing import Optional

from tavily import (
    BadRequestError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    TavilyClient,
    UsageLimitExceededError,
)

from src.config import ConfigurationError, TavilyConfig, get_config, mask_api_key
from src.models import (
    CrossVerificationReport,
    DisasterEventMetadata,
    SearchResponse,
    SearchResult,
)
from src.query_parser import parse_disaster_query
from src.verification import (
    process_and_filter_results,
    perform_cross_verification,
    synthesize_incident_summary,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Custom Exception Hierarchy
# ------------------------------------------------------------------------------
class TavilySearchError(Exception):
    """Base exception for all Tavily search operations."""
    pass


class MissingKeyError(TavilySearchError):
    """Raised when an API key is not provided or not configured in .env."""
    pass


class AuthenticationError(TavilySearchError):
    """Raised when an API key is invalid or rejected by Tavily."""
    pass


class RateLimitError(TavilySearchError):
    """Raised when Tavily usage or rate limits are exceeded."""
    pass


class InvalidQueryError(TavilySearchError):
    """Raised when a search query is empty, whitespace, or invalid."""
    pass


class NetworkOrAPIError(TavilySearchError):
    """Raised when an unexpected network error or Tavily API failure occurs."""
    pass


def sanitize_text(text: Optional[str]) -> str:
    """
    Sanitize text to prevent terminal formatting glitches caused by raw carriage returns,
    unsupported Unicode spaces (e.g. \u2009, \u00a0), or non-printable control characters.
    """
    if not text:
        return ""
    # Normalize carriage returns and unicode whitespace variants
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2009", " ")
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
        .replace("\u200b", "")
    )
    # Retain standard characters, spaces, tabs, and newlines
    cleaned = "".join(
        ch for ch in normalized
        if ch in ("\n", "\t") or (ord(ch) >= 32 and ord(ch) != 127)
    )
    return cleaned.strip()


# ------------------------------------------------------------------------------
# Tavily Search Service
# ------------------------------------------------------------------------------
class TavilySearchService:
    """
    Modular wrapper around the Tavily Search SDK.
    Integrates:
      - Disaster query entity identification (incident type, location, event date)
      - Query optimization while preserving raw query
      - Source credibility evaluation and low-value noise filtering
      - Temporal relation categorization (contemporaneous vs. retrospective)
      - Multi-source cross-verification and transparent limitation reporting
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[TavilyConfig] = None,
    ):
        """
        Initialize the TavilySearchService.
        
        Args:
            api_key: Optional Tavily API key. If omitted, loaded from config / .env.
            config: Optional pre-initialized TavilyConfig.
        """
        self.config = config or get_config()
        if api_key is not None:
            self.config.api_key = api_key.strip() if api_key else None

        # Check configuration
        try:
            self.config.validate()
        except ConfigurationError as err:
            raise MissingKeyError(str(err)) from err

        # Initialize official TavilyClient
        try:
            self._client = TavilyClient(api_key=self.config.api_key)
        except MissingAPIKeyError as err:
            raise MissingKeyError(
                "TavilyClient initialization failed: missing API key."
            ) from err
        except Exception as err:
            raise NetworkOrAPIError(
                f"Failed to initialize TavilyClient: {err}"
            ) from err

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        search_depth: Optional[str] = None,
        topic: Optional[str] = None,
        include_answer: bool = False,
        optimize_query: bool = True,
    ) -> SearchResponse:
        """
        Execute a search query against Tavily, filter and verify results, and return
        a structured SearchResponse with cross-verification analytics.

        Args:
            query: Disaster-related search query string (e.g., 'Kerala floods August 2018').
            max_results: Number of results to return (default from config, typically 5).
            search_depth: 'basic' or 'advanced' (default from config).
            topic: 'general' or 'news' (default from config).
            include_answer: If True, requests a synthesized direct summary from Tavily.
            optimize_query: If True, constructs a targeted incident query while preserving original.

        Returns:
            SearchResponse: Strongly-typed response containing verified and filtered SearchResult items.

        Raises:
            InvalidQueryError: If query is blank or invalid.
            AuthenticationError: If API key is rejected.
            RateLimitError: If account limit is reached.
            NetworkOrAPIError: On unexpected API or connection issues.
        """
        # Validate query
        if not query or not isinstance(query, str):
            raise InvalidQueryError("Search query must be a non-empty string.")

        cleaned_query = query.strip()
        if not cleaned_query:
            raise InvalidQueryError("Search query cannot be empty or only whitespace.")

        if len(cleaned_query) < 2:
            raise InvalidQueryError("Search query is too short. Please provide a more descriptive query.")

        # 1. Parse natural-language disaster query into structured entities
        parsed_query_info = parse_disaster_query(cleaned_query)
        event_metadata = DisasterEventMetadata(
            original_query=parsed_query_info.original_query,
            disaster_type=parsed_query_info.disaster_type,
            location=parsed_query_info.location,
            event_year=parsed_query_info.event_year,
            event_month=parsed_query_info.event_month,
            event_date_str=parsed_query_info.event_date_str,
            optimized_search_query=parsed_query_info.optimized_search_query,
        )

        query_to_send = (
            parsed_query_info.optimized_search_query
            if optimize_query and parsed_query_info.optimized_search_query
            else cleaned_query
        )

        # Determine effective parameters
        depth = search_depth or self.config.search_depth
        limit = max_results or self.config.max_results
        search_topic = topic or self.config.topic

        logger.info(
            "Executing Tavily search [original=%r, effective=%r, depth=%s, limit=%s, topic=%s, include_answer=%s]",
            cleaned_query,
            query_to_send,
            depth,
            limit,
            search_topic,
            include_answer,
        )

        start_time = time.perf_counter()

        try:
            raw_response = self._client.search(
                query=query_to_send,
                search_depth=depth,
                max_results=limit,
                topic=search_topic,
                include_answer=include_answer,
                timeout=self.config.timeout,
            )
        except InvalidAPIKeyError as err:
            logger.error("Tavily authentication failed: invalid API key.")
            raise AuthenticationError(
                "Invalid Tavily API key. Please check your credentials in the .env file."
            ) from err
        except UsageLimitExceededError as err:
            logger.error("Tavily usage limit exceeded.")
            raise RateLimitError(
                "Tavily API quota or rate limit exceeded. Please check your account balance."
            ) from err
        except BadRequestError as err:
            logger.error("Tavily bad request error: %s", err)
            raise InvalidQueryError(f"Tavily rejected the search query or parameters: {err}") from err
        except Exception as err:
            err_msg = str(err)
            # Mask potential secret leaks if error messages reflect key
            if self.config.api_key and self.config.api_key in err_msg:
                err_msg = err_msg.replace(self.config.api_key, mask_api_key(self.config.api_key))
            logger.error("Tavily search API error: %s", err_msg)
            raise NetworkOrAPIError(f"Tavily API request failed: {err_msg}") from err

        elapsed = time.perf_counter() - start_time

        # 2. Parse raw dictionary response into initial SearchResponse
        initial_response = SearchResponse.from_tavily_payload(
            query=cleaned_query,
            payload=raw_response,
            response_time=round(elapsed, 3),
            actual_search_query=query_to_send,
            event_info=event_metadata,
        )

        # Sanitize text in parsed items
        sanitized_results = []
        for r in initial_response.results:
            sanitized_results.append(
                r.model_copy(
                    update={
                        "title": sanitize_text(r.title),
                        "content": sanitize_text(r.content),
                    }
                )
            )

        # 3. Apply Quality Filtering, Deduplication & Temporal Categorization
        retained_results, filtered_results = process_and_filter_results(
            sanitized_results,
            parsed_query_info,
        )

        # 4. Multi-Source Cross-Verification
        verification_report = perform_cross_verification(
            retained_results,
            parsed_query_info,
        )

        # 5. Synthesize Evidence-Based Summary
        incident_summary = synthesize_incident_summary(
            parsed_query_info,
            retained_results,
            verification_report,
        )

        # Sanitize optional answer
        sanitized_answer = sanitize_text(initial_response.answer) if initial_response.answer else None

        # Build final enriched SearchResponse
        final_response = SearchResponse(
            query=cleaned_query,
            actual_search_query=query_to_send,
            event_info=event_metadata,
            results=sanitized_results,
            retained_results=retained_results,
            filtered_results=filtered_results,
            total_results=len(sanitized_results),
            total_retained=len(retained_results),
            total_filtered=len(filtered_results),
            verification_report=verification_report,
            synthesized_incident_summary=incident_summary,
            response_time=round(elapsed, 3),
            answer=sanitized_answer,
            is_verified_ground_truth=False,
            disclaimer=initial_response.disclaimer,
        )

        return final_response

    @staticmethod
    def format_results_for_display(response: SearchResponse) -> str:
        """
        Format a SearchResponse into a clean, human-readable terminal output.
        Displays incident identification, actual search query, curated sources,
        cross-source verification report, and incident summary.
        """
        lines = []
        divider = "=" * 80
        thin_divider = "-" * 80

        lines.append(divider)
        lines.append(" DISASTER INTELLIGENCE & SOURCE VERIFICATION REPORT")
        lines.append(divider)
        lines.append(f" Original Query       : {response.query}")
        if response.actual_search_query and response.actual_search_query != response.query:
            lines.append(f" Actual Search Query  : {response.actual_search_query}")

        if response.event_info:
            ev = response.event_info
            lines.append(f" Identified Incident  : {ev.disaster_type or 'Unknown disaster type'}")
            lines.append(f" Identified Location  : {ev.location or 'Unknown location'}")
            lines.append(f" Identified Date      : {ev.event_date_str or 'Unknown / unspecified'}")

        # Count breakdown
        contemp = sum(1 for r in response.retained_results if r.temporal_category == "contemporaneous")
        retrospect = sum(1 for r in response.retained_results if r.temporal_category == "retrospective")
        unknown_t = sum(1 for r in response.retained_results if r.temporal_category == "unknown")

        lines.append(
            f" Results Summary      : {response.total_results} retrieved | "
            f"{response.total_retained} retained ({contemp} contemporaneous, {retrospect} retrospective"
            + (f", {unknown_t} unknown date" if unknown_t else "")
            + f") | {response.total_filtered} filtered"
        )
        if response.response_time is not None:
            lines.append(f" Response Time        : {response.response_time:.2f}s")
        
        # Wrapped notice
        wrapped_notice = textwrap.fill(
            response.disclaimer,
            width=76,
            initial_indent=" Notice               : ",
            subsequent_indent="                        ",
        )
        lines.append(wrapped_notice)
        lines.append(divider)

        # 1. Synthesized Direct Answer (if requested)
        if response.answer:
            lines.append(" TAVILY SYNTHESIZED OVERVIEW: [API-generated AI summary - NOT verified ground truth]")
            lines.append("   Notice: The following summary is generated by Tavily's synthesis model and reflects unverified")
            lines.append("   AI compilation. It is NOT counted as independent verification evidence unless corroborated")
            lines.append("   by retrieved source content below.")
            lines.append("")
            wrapped_answer = textwrap.fill(
                response.answer.strip(),
                width=76,
                initial_indent="   ",
                subsequent_indent="   ",
            )
            lines.append(wrapped_answer)
            lines.append(divider)

        # 2. Incident Summary based on Evidence
        if response.synthesized_incident_summary:
            lines.append(" EVIDENCE-BASED INCIDENT SUMMARY:")
            for s_line in response.synthesized_incident_summary.split("\n"):
                wrapped_s = textwrap.fill(
                    s_line,
                    width=76,
                    initial_indent="   ",
                    subsequent_indent="     ",
                )
                lines.append(wrapped_s)
            lines.append(divider)

        # 3. Multi-Source Cross-Verification
        if response.verification_report:
            vr = response.verification_report
            lines.append(" MULTI-SOURCE CROSS-VERIFICATION ANALYSIS:")

            # Detailed Claim-by-Claim Evidence Evaluation
            if vr.verified_claims:
                lines.append("\n [Claim-by-Claim Evidence Evaluation]:")
                for c_idx, c_item in enumerate(vr.verified_claims, start=1):
                    status_tag = c_item.status.upper().replace("_", "-")
                    lines.append(f"  ({c_idx}) [{status_tag}] Topic: {c_item.topic}")
                    lines.append(f"      Claim    : {c_item.claim}")
                    lines.append(f"      Evidence : {c_item.evidence_explanation}")
                    if c_item.sources:
                        lines.append("      Sources  :")
                        for src in c_item.sources:
                            src_dom = src.get("domain", "source")
                            src_url = src.get("url", "")
                            src_quote = src.get("quote", "")
                            lines.append(f"        * {src_dom} ({src_url})")
                            if src_quote:
                                lines.append(f"          Excerpt: \"{src_quote}\"")
                    else:
                        lines.append("      Sources  : None (insufficient content in retrieved snippets)")
                    lines.append("")

            if vr.corroborated_facts:
                lines.append(" [Corroborated Facts (Supported by 2+ Independent Sources)]:")
                for fact in vr.corroborated_facts:
                    lines.append(textwrap.fill(f"  [+] {fact}", width=76, subsequent_indent="      "))
            else:
                lines.append(" [Corroborated Facts]: None confirmed across independent sources.")

            if vr.single_source_claims:
                lines.append("\n [Single-Source Claims (Awaiting Cross-Source Confirmation)]:")
                for claim in vr.single_source_claims:
                    lines.append(textwrap.fill(f"  [-] {claim}", width=76, subsequent_indent="      "))

            if vr.conflicting_claims:
                lines.append("\n [Conflicting / Discrepant Information]:")
                for conf in vr.conflicting_claims:
                    lines.append(textwrap.fill(f"  [!] {conf}", width=76, subsequent_indent="      "))

            if vr.limitations:
                lines.append("\n [Verification Limitations]:")
                for lim in vr.limitations:
                    lines.append(textwrap.fill(f"  ! {lim}", width=76, subsequent_indent="    "))

            lines.append(divider)

        # 4. Retained Results Listing
        if not response.retained_results:
            lines.append("")
            lines.append("  [!] No retained search results available for this query.")
            lines.append("      All results were either duplicate, irrelevant, or low-value.")
            lines.append("")
        else:
            lines.append(f" RETAINED SOURCES ({len(response.retained_results)}):")
            for idx, result in enumerate(response.retained_results, start=1):
                temp_tag = result.temporal_category.upper()
                cred_tag = result.source_credibility.replace("_", " ").upper()

                lines.append(f"\n[Result {idx}/{len(response.retained_results)}] [{temp_tag}] [{cred_tag}]")
                lines.append(f" Title   : {result.title}")
                lines.append(f" URL     : {result.url}")
                lines.append(f" Domain  : {result.domain}")
                if result.published_date:
                    lines.append(f" Date    : {result.published_date}")
                else:
                    lines.append(" Date    : Unknown (Not provided by source)")

                if result.score is not None:
                    lines.append(f" Search Relevance Score : {result.score:.4f} (Retrieval metric - not factual confidence)")

                if result.relevance_explanation:
                    wrapped_expl = textwrap.fill(
                        result.relevance_explanation,
                        width=76,
                        initial_indent=" Assessment : ",
                        subsequent_indent="              ",
                    )
                    lines.append(wrapped_expl)

                lines.append(" Content :")
                paragraphs = result.content.strip().split("\n")
                for para in paragraphs:
                    para_clean = para.strip()
                    if not para_clean:
                        continue
                    wrapped_para = textwrap.fill(
                        para_clean,
                        width=76,
                        initial_indent="   ",
                        subsequent_indent="   ",
                    )
                    lines.append(wrapped_para)
                lines.append(thin_divider)

        # 5. Filtered Results Summary (if any)
        if response.filtered_results:
            lines.append("")
            lines.append(f" FILTERED / EXCLUDED SOURCES ({len(response.filtered_results)}):")
            for f_idx, f_item in enumerate(response.filtered_results, start=1):
                lines.append(f"  {f_idx}. [{f_item.domain}] {f_item.title}")
                lines.append(f"     URL   : {f_item.url}")
                lines.append(f"     Reason: {f_item.filter_reason or 'Excluded by quality filter'}")
            lines.append(divider)

        return "\n".join(lines)
