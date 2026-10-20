"""
Official ReliefWeb API (v2) client integration for humanitarian disaster intelligence.
Retrieves and normalizes humanitarian situation reports, disaster impact assessments,
and post-disaster needs assessments published by UN OCHA, national governments, NGOs, and the Red Cross.

A service of the United Nations Office for the Coordination of Humanitarian Affairs (UN OCHA).
Requires an 'appname' parameter in query URLs per ReliefWeb API v2 requirements.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import logging
import re
import socket
import sys
from typing import Any, Dict, List, Optional, Set, Union
import urllib.error
import urllib.parse
import urllib.request

from src.config import ReliefWebConfig, get_reliefweb_config
from src.models import ReliefWebReport, ReliefWebQueryResponse

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------
class ReliefWebClientError(Exception):
    """Base exception for all ReliefWeb API client errors."""
    pass


class ReliefWebInvalidParameterError(ReliefWebClientError):
    """Raised when query parameters (dates, limits, query string) are invalid."""
    pass


class ReliefWebTimeoutError(ReliefWebClientError):
    """Raised when an API request to ReliefWeb times out."""
    pass


class ReliefWebHTTPError(ReliefWebClientError):
    """Raised when the ReliefWeb API responds with an HTTP 4xx or 5xx status code."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ReliefWebParsingError(ReliefWebClientError):
    """Raised when ReliefWeb response data is malformed or cannot be parsed as valid JSON."""
    pass


class ReliefWebNetworkError(ReliefWebClientError):
    """Raised on socket/DNS connection failures when contacting ReliefWeb."""
    pass


# ------------------------------------------------------------------------------
# Sample Offline Fixture for Kerala Floods August 2018
# ------------------------------------------------------------------------------
SAMPLE_KERALA_FLOODS_PAYLOAD: Dict[str, Any] = {
    "time": 25,
    "href": "https://api.reliefweb.int/v2/reports?appname=demo",
    "totalCount": 3,
    "count": 3,
    "data": [
        {
            "id": "2754629",
            "score": 1.0,
            "fields": {
                "id": "2754629",
                "title": "India: Floods in Kerala - Situation Report No. 1 (as of 19 August 2018)",
                "url": "https://reliefweb.int/report/india/india-floods-kerala-situation-report-no-1-19-august-2018",
                "date": {
                    "created": "2018-08-19T14:30:00+00:00",
                    "original": "2018-08-19T00:00:00+00:00",
                    "changed": "2018-08-20T08:00:00+00:00",
                },
                "source": [
                    {
                        "id": 1241,
                        "name": "UN Children's Fund",
                        "shortname": "UNICEF",
                    },
                    {
                        "id": 2984,
                        "name": "Government of India",
                        "shortname": "Govt. India",
                    },
                ],
                "format": [
                    {
                        "id": 10,
                        "name": "Situation Report",
                    }
                ],
                "theme": [
                    {"name": "Disaster Management"},
                    {"name": "Water Sanitation Hygiene"},
                    {"name": "Health"},
                ],
                "primary_country": {
                    "id": 119,
                    "name": "India",
                    "iso3": "ind",
                },
                "country": [
                    {
                        "id": 119,
                        "name": "India",
                        "iso3": "ind",
                    }
                ],
                "disaster": [
                    {
                        "id": 46194,
                        "name": "India: Floods - Aug 2018",
                        "glide": "FL-2018-000130-IND",
                    }
                ],
                "disaster_type": [
                    {
                        "id": 4611,
                        "name": "Flood",
                    }
                ],
                "body": (
                    "Severe monsoon rainfall in Kerala has led to unprecedented flooding across all 14 districts. "
                    "Over 800,000 displaced persons are currently accommodated in more than 4,000 relief camps. "
                    "State emergency operations and disaster response forces are coordinating water, sanitation, "
                    "and child protection interventions."
                ),
            },
        },
        {
            "id": "2759884",
            "score": 0.95,
            "fields": {
                "id": "2759884",
                "title": "India: Monsoon Floods 2018 - Emergency Plan of Action (EPoA) DREF Operation MDRIN022",
                "url": "https://reliefweb.int/report/india/india-monsoon-floods-2018-emergency-plan-action-epoa-dref-operation-n-mdrin022",
                "date": {
                    "created": "2018-08-24T11:15:00+00:00",
                    "original": "2018-08-23T00:00:00+00:00",
                    "changed": "2018-08-24T12:00:00+00:00",
                },
                "source": [
                    {
                        "id": 1243,
                        "name": "International Federation of Red Cross And Red Crescent Societies",
                        "shortname": "IFRC",
                    }
                ],
                "format": [
                    {
                        "id": 1,
                        "name": "Assessment",
                    }
                ],
                "theme": [
                    {"name": "Disaster Management"},
                    {"name": "Shelter and Non-Food Items"},
                ],
                "primary_country": {
                    "id": 119,
                    "name": "India",
                    "iso3": "ind",
                },
                "country": [
                    {
                        "id": 119,
                        "name": "India",
                        "iso3": "ind",
                    }
                ],
                "disaster": [
                    {
                        "id": 46194,
                        "name": "India: Floods - Aug 2018",
                        "glide": "FL-2018-000130-IND",
                    }
                ],
                "disaster_type": [
                    {
                        "id": 4611,
                        "name": "Flood",
                    }
                ],
                "body": (
                    "Torrential rains from 8 August caused dams to open sluice gates across Kerala. "
                    "Initial rapid assessments indicate over 1.4 million people have been directly affected, "
                    "with severe infrastructure damage to road networks and residential housing."
                ),
            },
        },
        {
            "id": "2835119",
            "score": 0.88,
            "fields": {
                "id": "2835119",
                "title": "Kerala Post Disaster Needs Assessment (PDNA): Floods and Landslides - August 2018",
                "url": "https://reliefweb.int/report/india/kerala-post-disaster-needs-assessment-floods-and-landslides-august-2018",
                "date": {
                    "created": "2018-10-25T16:00:00+00:00",
                    "original": "2018-10-25T00:00:00+00:00",
                    "changed": "2018-10-26T09:30:00+00:00",
                },
                "source": [
                    {
                        "id": 2984,
                        "name": "Government of Kerala",
                        "shortname": "Govt. Kerala",
                    },
                    {
                        "id": 1242,
                        "name": "UN Development Programme",
                        "shortname": "UNDP",
                    },
                ],
                "format": [
                    {
                        "id": 1,
                        "name": "Assessment",
                    }
                ],
                "theme": [
                    {"name": "Recovery and Reconstruction"},
                    {"name": "Disaster Management"},
                ],
                "primary_country": {
                    "id": 119,
                    "name": "India",
                    "iso3": "ind",
                },
                "country": [
                    {
                        "id": 119,
                        "name": "India",
                        "iso3": "ind",
                    }
                ],
                "disaster": [
                    {
                        "id": 46194,
                        "name": "India: Floods - Aug 2018",
                        "glide": "FL-2018-000130-IND",
                    }
                ],
                "disaster_type": [
                    {
                        "id": 4611,
                        "name": "Flood",
                    }
                ],
                "body": (
                    "A comprehensive Post Disaster Needs Assessment conducted jointly by the Government of Kerala, "
                    "the United Nations, the World Bank, and the Asian Development Bank. The assessment estimates "
                    "total recovery and reconstruction requirements at approximately INR 31,000 crore (USD 4.4 billion)."
                ),
            },
        },
    ],
}


# ------------------------------------------------------------------------------
# ReliefWeb Client Implementation
# ------------------------------------------------------------------------------
class ReliefWebClient:
    """
    Client for interacting with the public ReliefWeb Reports API (v2).
    Provides methods to search humanitarian situation reports and assessments
    by keyword query, country, date range, and format.
    """

    SUPPORTED_FORMATS: Set[str] = {
        "Situation Report",
        "Assessment",
        "Evaluation",
        "News and Press Release",
        "Infographic",
        "Map",
        "Manual and Guideline",
    }

    def __init__(
        self,
        config: Optional[ReliefWebConfig] = None,
        timeout: Optional[int] = None,
    ):
        self.config = config or get_reliefweb_config()
        self.timeout = timeout if timeout is not None else self.config.timeout

    def query_reports(
        self,
        query: Optional[str] = None,
        country: Optional[str] = None,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
        disaster_types: Optional[Union[str, List[str]]] = None,
        formats: Optional[Union[str, List[str]]] = None,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "date.created:desc",
        appname: Optional[str] = None,
    ) -> ReliefWebQueryResponse:
        """
        Queries humanitarian reports from the ReliefWeb Reports API (v2).

        Args:
            query: Free-text search terms (e.g. 'Kerala floods', 'Turkey earthquake').
            country: Country name or ISO3 code (e.g. 'India', 'TUR').
            from_date: Start of publication date range (date.created).
            to_date: End of publication date range (date.created).
            disaster_types: Disaster hazard type(s) (e.g. 'Flood', 'Earthquake').
            formats: Content format(s) (e.g. 'Situation Report', 'Assessment').
            limit: Maximum reports to retrieve (1 to 1000, default 10).
            offset: Pagination offset (default 0).
            sort_by: Sort expression (default 'date.created:desc').
            appname: Override appname identifier.

        Returns:
            ReliefWebQueryResponse with parsed ReliefWebReport objects.

        Raises:
            ReliefWebInvalidParameterError: If parameters are invalid.
            ReliefWebTimeoutError: If the request times out.
            ReliefWebHTTPError: If the server returns an HTTP error code.
            ReliefWebParsingError: If response data cannot be parsed.
            ReliefWebNetworkError: If a network connection error occurs.
        """
        # Validate limit and offset
        if limit < 1 or limit > 1000:
            raise ReliefWebInvalidParameterError(f"limit ({limit}) must be between 1 and 1000.")
        if offset < 0:
            raise ReliefWebInvalidParameterError(f"offset ({offset}) cannot be negative.")

        # Build POST payload
        payload: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "fields": {
                "include": [
                    "title",
                    "url",
                    "date",
                    "source",
                    "format",
                    "theme",
                    "country",
                    "primary_country",
                    "disaster",
                    "disaster_type",
                    "body",
                    "headline",
                ]
            },
        }

        if sort_by:
            payload["sort"] = [sort_by]

        if query and query.strip():
            payload["query"] = {"value": query.strip()}

        # Filter conditions
        conditions: List[Dict[str, Any]] = []

        if country and country.strip():
            conditions.append({"field": "country", "value": country.strip()})

        if from_date or to_date:
            date_filter: Dict[str, str] = {}
            if from_date:
                date_filter["from"] = self._format_date(from_date, is_end=False)
            if to_date:
                date_filter["to"] = self._format_date(to_date, is_end=True)
            conditions.append({"field": "date.created", "value": date_filter})

        if formats:
            fmt_list = [formats] if isinstance(formats, str) else list(formats)
            valid_fmts = [f.strip() for f in fmt_list if f and f.strip()]
            if valid_fmts:
                conditions.append({"field": "format.name", "value": valid_fmts, "operator": "OR"})

        if disaster_types:
            dt_list = [disaster_types] if isinstance(disaster_types, str) else list(disaster_types)
            valid_dts = [d.strip() for d in dt_list if d and d.strip()]
            if valid_dts:
                conditions.append({"field": "disaster_type.name", "value": valid_dts, "operator": "OR"})

        if conditions:
            if len(conditions) == 1:
                payload["filter"] = conditions[0]
            else:
                payload["filter"] = {
                    "operator": "AND",
                    "conditions": conditions,
                }

        # Build URL with appname query parameter
        effective_appname = (
            appname
            or self.config.appname
            or "DisasterIntelligencePipeline-Dev-x7k9"
        ).strip()

        base_url = self.config.base_url.rstrip("/")
        sep = "&" if "?" in base_url else "?"
        query_url = f"{base_url}{sep}appname={urllib.parse.quote_plus(effective_appname)}"

        raw_json = self._execute_request(query_url, payload=payload)
        return ReliefWebQueryResponse.from_api_payload(
            payload=raw_json,
            query_params=payload,
            api_url=query_url,
        )

    def get_report_by_id(
        self,
        report_id: Union[str, int],
        appname: Optional[str] = None,
    ) -> Optional[ReliefWebReport]:
        """
        Retrieves a single report by its unique ID.
        Returns None if not found (HTTP 404).
        """
        clean_id = str(report_id).strip()
        if not clean_id:
            raise ReliefWebInvalidParameterError("Report ID cannot be empty.")

        effective_appname = (
            appname
            or self.config.appname
            or "DisasterIntelligencePipeline-Dev-x7k9"
        ).strip()

        base_url = self.config.base_url.rstrip("/")
        query_url = f"{base_url}/{clean_id}?appname={urllib.parse.quote_plus(effective_appname)}"

        try:
            raw_json = self._execute_request(query_url, payload=None)
            data = raw_json.get("data", [])
            if data and isinstance(data, list) and isinstance(data[0], dict):
                return ReliefWebReport.from_api_item(data[0])
            return None
        except ReliefWebHTTPError as err:
            if err.status_code == 404:
                return None
            raise

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------
    def _execute_request(self, url: str, payload: Optional[dict] = None) -> dict:
        """
        Executes HTTP request to ReliefWeb API and parses JSON response.
        Uses POST when payload is provided, otherwise GET.
        """
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
        }

        data_bytes = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=data_bytes, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = resp.status
                raw_bytes = resp.read()

        except urllib.error.HTTPError as http_err:
            status_code = http_err.code
            error_body = ""
            try:
                error_body = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if status_code == 403:
                raise ReliefWebHTTPError(
                    f"ReliefWeb API HTTP 403 Forbidden: Approved appname required by ReliefWeb API v2. "
                    f"Register a pre-approved appname at https://apidoc.reliefweb.int/parameters#appname and "
                    f"configure RELIEFWEB_APPNAME in your .env file. (Details: {error_body.strip()})",
                    status_code=403,
                )
            if status_code == 400:
                raise ReliefWebInvalidParameterError(
                    f"ReliefWeb API HTTP 400 Bad Request: {error_body.strip()}"
                )
            raise ReliefWebHTTPError(
                f"ReliefWeb API HTTP {status_code}: {error_body.strip()}",
                status_code=status_code,
            )

        except (socket.timeout, TimeoutError):
            raise ReliefWebTimeoutError(
                f"ReliefWeb API request timed out after {self.timeout}s: {url}"
            )
        except urllib.error.URLError as url_err:
            reason = getattr(url_err, "reason", str(url_err))
            if isinstance(reason, socket.timeout):
                raise ReliefWebTimeoutError(
                    f"ReliefWeb API request timed out after {self.timeout}s: {url}"
                )
            raise ReliefWebNetworkError(
                f"Failed to connect to ReliefWeb API at {url}: {reason}"
            )
        except Exception as exc:
            raise ReliefWebNetworkError(
                f"Unexpected network or connection error contacting ReliefWeb: {exc}"
            )

        if not raw_bytes or not raw_bytes.strip():
            return {}

        try:
            return json.loads(raw_bytes.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as json_err:
            raise ReliefWebParsingError(
                f"Malformed JSON returned by ReliefWeb API: {json_err}"
            )

    @staticmethod
    def _format_date(val: Union[str, date, datetime], is_end: bool = False) -> str:
        """Normalizes date into full ISO-8601 string with time and UTC timezone for ReliefWeb."""
        if isinstance(val, datetime):
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc).isoformat()
        if isinstance(val, date):
            t = (23, 59, 59) if is_end else (0, 0, 0)
            return datetime(val.year, val.month, val.day, *t, tzinfo=timezone.utc).isoformat()
        if isinstance(val, str):
            cleaned = val.strip()
            if not cleaned:
                raise ReliefWebInvalidParameterError("Date parameter string cannot be blank.")
            # If plain date YYYY-MM-DD
            if re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
                time_str = "T23:59:59+00:00" if is_end else "T00:00:00+00:00"
                return f"{cleaned}{time_str}"
            # If already has time but missing timezone
            if "T" in cleaned and ("+" not in cleaned and not cleaned.endswith("Z")):
                return f"{cleaned}+00:00"
            return cleaned
        raise ReliefWebInvalidParameterError(f"Unsupported date type: {type(val).__name__}")

    # --------------------------------------------------------------------------
    # Output Formatting for Display
    # --------------------------------------------------------------------------
    @staticmethod
    def format_reports_for_display(
        response: ReliefWebQueryResponse,
        max_reports: int = 5,
    ) -> str:
        """
        Formats ReliefWeb query response as a clean, human-readable terminal report.
        Strictly labels publication date vs disaster date and includes operational estimate disclaimers.
        """
        lines = []
        lines.append("=" * 80)
        lines.append("RELIEFWEB HUMANITARIAN SITUATION REPORTS & ASSESSMENTS (UN OCHA)")
        lines.append("=" * 80)
        lines.append(f"Total Reports Matching: {response.total_count}")
        lines.append(f"Reports Retrieved     : {response.count}")
        lines.append(f"API Endpoint          : {response.api_url or 'N/A'}")
        lines.append(f"Provenance Disclaimer : {response.disclaimer}")
        lines.append("-" * 80)

        if not response.reports:
            lines.append("No humanitarian reports matched the specified criteria.")
            lines.append("=" * 80)
            return "\n".join(lines)

        shown = response.reports[:max_reports]
        for idx, rep in enumerate(shown, 1):
            lines.append(f"[{idx}] {rep.title}")
            lines.append(f"    Source/Org      : {', '.join(rep.sources) if rep.sources else 'Unknown'}")
            lines.append(f"    Format          : {rep.format or 'Humanitarian Report'}")
            lines.append(f"    Publication Date: {rep.publication_date or 'Unknown'} (Report Publication Date, NOT Incident Date)")
            if rep.disaster_names:
                lines.append(f"    Disaster Tag    : {', '.join(rep.disaster_names)}")
            if rep.glide_numbers:
                lines.append(f"    GLIDE Number    : {', '.join(rep.glide_numbers)}")
            lines.append(f"    Report URL      : {rep.url}")
            if rep.body_snippet:
                snippet = rep.body_snippet[:200] + "..." if len(rep.body_snippet) > 200 else rep.body_snippet
                lines.append(f"    Excerpt         : \"{snippet}\"")
            lines.append(f"    Data Status     : [Humanitarian Field Estimate - NOT Verified Ground Truth]")
            lines.append("")

        if len(response.reports) > max_reports:
            lines.append(f"... and {len(response.reports) - max_reports} more humanitarian reports.")

        lines.append("-" * 80)
        lines.append("CAVEAT: Figures in situation reports represent operational agency estimates at time of publication.")
        lines.append("=" * 80)
        return "\n".join(lines)


# ------------------------------------------------------------------------------
# Standalone CLI Runner
# ------------------------------------------------------------------------------
def main() -> None:
    """Command-line runner for interactive ReliefWeb disaster queries."""
    parser = argparse.ArgumentParser(
        description="Query the ReliefWeb Reports API for humanitarian situation reports.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--query",
        "-q",
        default="Kerala floods",
        help="Search query for humanitarian reports (e.g. 'Kerala floods', 'Turkey earthquake').",
    )
    parser.add_argument(
        "--country",
        "-c",
        default=None,
        help="Country name or ISO code filter (e.g. 'India', 'TUR').",
    )
    parser.add_argument(
        "--start-date",
        "-s",
        default=None,
        help="Publication start date in YYYY-MM-DD or ISO format.",
    )
    parser.add_argument(
        "--end-date",
        "-e",
        default=None,
        help="Publication end date in YYYY-MM-DD or ISO format.",
    )
    parser.add_argument(
        "--format",
        "-f",
        default=None,
        help="Report format filter (e.g. 'Situation Report', 'Assessment').",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=5,
        help="Maximum reports to display.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use built-in authentic Kerala floods August 2018 sample data for demonstration.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response.",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.sample:
        resp = ReliefWebQueryResponse.from_api_payload(
            SAMPLE_KERALA_FLOODS_PAYLOAD,
            query_params={"sample": True},
            api_url="https://api.reliefweb.int/v2/reports?sample=true",
        )
        if args.json:
            print(resp.model_dump_json(indent=2))
        else:
            print(ReliefWebClient.format_reports_for_display(resp))
        return

    client = ReliefWebClient()
    try:
        response = client.query_reports(
            query=args.query,
            country=args.country,
            from_date=args.start_date,
            to_date=args.end_date,
            formats=args.format,
            limit=args.limit,
        )
        if args.json:
            print(response.model_dump_json(indent=2))
        else:
            print(ReliefWebClient.format_reports_for_display(response))

    except ReliefWebClientError as err:
        print(f"\n[ReliefWeb Error] {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
