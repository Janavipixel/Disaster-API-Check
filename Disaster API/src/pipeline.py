"""
Unified Disaster Intelligence Pipeline Orchestrator.
Coordinates and integrates three multi-source intelligence feeds:
  1. Tavily Search API (open web news, reports, and cross-source verification)
  2. USGS Earthquake Catalog API (authoritative seismic parameters and epicenters)
  3. GDACS API (multi-hazard alert levels, scores, centroids, and GLIDE IDs)

Ensures:
  - Incident-consistent date range and location alignment
  - Conservative, explicit cross-source incident matching
  - Resilient partial-failure execution
  - Clear data boundary enforcement (verified sensor vs. modeled alert vs. media reports)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project root is in sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.firms_client import FIRMSClient, FIRMSClientError
from src.clients.gdacs_client import GDACSClient, GDACSClientError
from src.clients.reliefweb_client import ReliefWebClient, ReliefWebClientError
from src.clients.usgs_client import USGSClient, USGSClientError
from src.config import ConfigurationError
from src.models import (
    ActiveFireDetection,
    ClaimEvidence,
    EarthquakeEvent,
    GDACSEvent,
    IncidentCoordinates,
    ReliefWebReport,
    SearchResult,
    UnifiedFIRMSData,
    UnifiedGDACSData,
    UnifiedIncidentReport,
    UnifiedReliefWebData,
    UnifiedTavilyData,
    UnifiedUSGSData,
)
from src.query_parser import (
    DisasterQueryInfo,
    derive_incident_date_range,
    parse_disaster_query,
)
from src.tavily_client import TavilySearchError, TavilySearchService
from src.verification import (
    perform_cross_verification,
    process_and_filter_results,
    synthesize_incident_summary,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Geographic & Jurisdiction Alias Mappings for Conservative Matching
# ------------------------------------------------------------------------------
LOCATION_SYNONYMS: Dict[str, Set[str]] = {
    "turkey": {"turkey", "türkiye", "turquia", "tur", "gaziantep", "kahramanmaras", "hatay", "anatolian"},
    "türkiye": {"turkey", "türkiye", "turquia", "tur", "gaziantep", "kahramanmaras", "hatay", "anatolian"},
    "syria": {"syria", "syr", "syrian", "aleppo", "damascus", "idlib"},
    "india": {"india", "ind", "bharat"},
    "kerala": {"kerala", "cochin", "kochi", "thiruvananthapuram", "wayanad", "idukki", "alappuzha", "ernakulam"},
    "lucknow": {"lucknow", "uttar pradesh", "gomti", "up"},
    "mumbai": {"mumbai", "bombay"},
    "united states": {"united states", "usa", "us", "u.s.", "america"},
    "california": {"california", "ca"},
    "japan": {"japan", "jpn", "tokyo", "fukushima", "tohoku", "honshu"},
    "greece": {"greece", "grc", "hellenic", "athens", "attica", "evia", "rhodes"},
    "nigeria": {"nigeria", "nga", "lagos", "abuja", "kogi"},
    "pakistan": {"pakistan", "pak", "sindh", "balochistan", "punjab"},
    "china": {"china", "chn", "sichuan", "wuhan", "beijing", "henan"},
    "indonesia": {"indonesia", "idn", "sumatra", "java", "bali", "sulawesi", "jakarta"},
    "italy": {"italy", "ita", "rome", "sicily", "emilia-romagna"},
    "new zealand": {"new zealand", "nzl", "nz", "wellington", "christchurch", "auckland"},
}

SUBNATIONAL_PARENTS: Dict[str, str] = {
    "kerala": "india",
    "lucknow": "india",
    "mumbai": "india",
    "california": "united states",
}

REGION_BOUNDING_BOXES: Dict[str, Tuple[float, float, float, float]] = {
    # (min_lat, max_lat, min_lon, max_lon)
    "kerala": (8.0, 13.0, 74.5, 77.8),
    "lucknow": (26.75, 26.95, 80.85, 81.05),
    "mumbai": (18.8, 19.5, 72.7, 73.2),
    "california": (32.5, 42.0, -124.5, -114.0),
    "united states": (24.5, 49.5, -125.0, -66.5),
    "usa": (24.5, 49.5, -125.0, -66.5),
    "turkey": (35.5, 42.5, 25.5, 45.0),
    "türkiye": (35.5, 42.5, 25.5, 45.0),
    "syria": (32.0, 37.5, 35.5, 42.5),
    "japan": (30.0, 46.0, 128.0, 146.0),
    "india": (8.0, 37.0, 68.0, 97.5),
    "greece": (34.8, 41.8, 19.3, 28.3),
    "australia": (-44.0, -10.0, 112.0, 154.0),
    "canada": (41.5, 70.0, -141.0, -52.5),
}

COUNTRY_ISO3_MAP: Dict[str, str] = {
    "united states": "USA",
    "usa": "USA",
    "us": "USA",
    "america": "USA",
    "india": "IND",
    "turkey": "TUR",
    "türkiye": "TUR",
    "syria": "SYR",
    "greece": "GRC",
    "canada": "CAN",
    "australia": "AUS",
    "japan": "JPN",
    "indonesia": "IDN",
    "italy": "ITA",
    "spain": "ESP",
    "portugal": "PRT",
    "brazil": "BRA",
    "chile": "CHL",
    "nigeria": "NGA",
    "pakistan": "PAK",
    "china": "CHN",
    "new zealand": "NZL",
}

GDACS_SUPPORTED_HAZARDS = {"earthquake", "floods", "cyclone", "volcano", "drought", "wildfire"}


def evaluate_event_location(
    target_location: Optional[str],
    event_texts: List[Optional[str]],
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Tuple[bool, str]:
    """
    Evaluates whether an event record matches a target disaster location.
    Distinguishes:
      - Direct subnational or national text match
      - Parent-country match verified by regional coordinates
      - Rejection due to divergent country or out-of-bounds coordinates
    Returns (is_match, reason).
    """
    if not target_location or not target_location.strip():
        return False, "Target location is unspecified."

    target_norm = target_location.strip().lower()

    # 1. Direct lexical/synonym match
    target_synonyms = set(LOCATION_SYNONYMS.get(target_norm, {target_norm}))
    for text in event_texts:
        if not text:
            continue
        text_lower = text.lower()
        for syn in target_synonyms:
            if re.search(r"\b" + re.escape(syn) + r"\b", text_lower):
                return True, f"Explicit text match for '{syn}' in event record."

    # 2. Check if target is a sub-national region under a parent country
    parent_country = SUBNATIONAL_PARENTS.get(target_norm)
    if parent_country:
        parent_synonyms = set(LOCATION_SYNONYMS.get(parent_country, {parent_country}))
        has_parent_text = False
        for text in event_texts:
            if not text:
                continue
            text_lower = text.lower()
            if any(re.search(r"\b" + re.escape(ps) + r"\b", text_lower) for ps in parent_synonyms):
                has_parent_text = True
                break

        if has_parent_text:
            bbox = REGION_BOUNDING_BOXES.get(target_norm)
            if latitude is not None and longitude is not None and bbox:
                min_lat, max_lat, min_lon, max_lon = bbox
                if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
                    return True, (
                        f"Centroid (Lat {latitude:.4f}, Lon {longitude:.4f}) is within "
                        f"regional bounds for '{target_location}' (Parent national alert '{parent_country.title()}')."
                    )
                else:
                    return False, (
                        f"Event is in parent country '{parent_country.title()}' but centroid "
                        f"(Lat {latitude:.4f}, Lon {longitude:.4f}) falls outside regional bounds for '{target_location}'."
                    )
            elif latitude is None or longitude is None:
                return True, f"Event matched at national level for parent country '{parent_country.title()}' (lacks regional coordinates)."

    # 3. Check bounding box match if target is country with bbox
    if latitude is not None and longitude is not None:
        target_bbox = REGION_BOUNDING_BOXES.get(target_norm)
        if target_bbox:
            min_lat, max_lat, min_lon, max_lon = target_bbox
            if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
                return True, f"Centroid (Lat {latitude:.4f}, Lon {longitude:.4f}) falls within bounding box for '{target_location}'."

    sample_loc = next((t for t in event_texts if t and t.strip()), "Unknown")
    return False, f"Event location '{sample_loc}' does not match target location '{target_location}'."


def matches_location(
    target_location: Optional[str],
    event_texts: List[Optional[str]],
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> bool:
    """
    Conservatively checks if an event matches a target incident location.
    Does not assume identity without explicit lexical or jurisdiction correlation.
    """
    is_match, _ = evaluate_event_location(target_location, event_texts, latitude, longitude)
    return is_match


# ------------------------------------------------------------------------------
# Unified Disaster Pipeline
# ------------------------------------------------------------------------------
class DisasterPipeline:
    """
    Orchestrates disaster intelligence across Tavily, USGS, GDACS, and ReliefWeb feeds.
    """

    def __init__(
        self,
        tavily_service: Optional[TavilySearchService] = None,
        usgs_client: Optional[USGSClient] = None,
        gdacs_client: Optional[GDACSClient] = None,
        reliefweb_client: Optional[ReliefWebClient] = None,
        firms_client: Optional[FIRMSClient] = None,
    ):
        # Allow dependency injection for testing, or lazily initialize
        if tavily_service is not None:
            self.tavily_service = tavily_service
        else:
            try:
                self.tavily_service = TavilySearchService()
            except (ConfigurationError, Exception) as err:
                logger.warning("Tavily service could not be initialized: %s", err)
                self.tavily_service = None

        self.usgs_client = usgs_client or USGSClient()
        self.gdacs_client = gdacs_client or GDACSClient()
        self.reliefweb_client = reliefweb_client or ReliefWebClient()
        self.firms_client = firms_client or FIRMSClient()

    def process_query(
        self,
        query: str,
        enable_tavily: bool = True,
        enable_usgs: bool = True,
        enable_gdacs: bool = True,
        enable_reliefweb: bool = True,
        enable_firms: bool = True,
        tavily_max_results: int = 5,
        usgs_limit: int = 20,
        gdacs_limit: int = 20,
        reliefweb_limit: int = 5,
        firms_limit: int = 20,
    ) -> UnifiedIncidentReport:
        """
        Executes unified query routing, execution, conservative matching, and normalization.
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("Query string cannot be empty.")

        # 1. Natural-Language Entity Extraction
        query_info: DisasterQueryInfo = parse_disaster_query(cleaned_query)
        start_date, end_date = derive_incident_date_range(query_info)

        sources_queried: List[str] = []
        sources_succeeded: List[str] = []
        sources_failed: Dict[str, str] = {}

        # 2. USGS Earthquake Catalog Execution
        usgs_data = UnifiedUSGSData()
        is_seismic = (
            query_info.disaster_type in {"earthquake", "quake", "tremor"}
            or "earthquake" in cleaned_query.lower()
            or "quake" in cleaned_query.lower()
        )

        if enable_usgs and is_seismic:
            sources_queried.append("USGS Earthquake Catalog")
            usgs_data = self._query_usgs(
                query_info=query_info,
                start_date=start_date,
                end_date=end_date,
                limit=usgs_limit,
            )
            if usgs_data.status in {"success", "no_matching_events"}:
                sources_succeeded.append("USGS Earthquake Catalog")
            else:
                sources_failed["USGS Earthquake Catalog"] = usgs_data.error_message or "USGS query failed"
        elif not is_seismic:
            usgs_data = UnifiedUSGSData(
                queried=False,
                status="not_applicable",
                error_message="USGS Earthquake Catalog is specialized for seismic hazards; skipped for this disaster type.",
            )

        # 3. GDACS Disaster Alerts Execution
        gdacs_data = UnifiedGDACSData()
        is_gdacs_applicable = (
            query_info.disaster_type is None
            or query_info.disaster_type in GDACS_SUPPORTED_HAZARDS
        )

        if enable_gdacs and is_gdacs_applicable:
            sources_queried.append("GDACS Disaster Alerts")
            gdacs_data = self._query_gdacs(
                query_info=query_info,
                start_date=start_date,
                end_date=end_date,
                limit=gdacs_limit,
            )
            if gdacs_data.status in {"success", "no_matching_events"}:
                sources_succeeded.append("GDACS Disaster Alerts")
            else:
                sources_failed["GDACS Disaster Alerts"] = gdacs_data.error_message or "GDACS query failed"
        elif not is_gdacs_applicable:
            gdacs_data = UnifiedGDACSData(
                queried=False,
                status="not_applicable",
                error_message=f"Disaster type '{query_info.disaster_type}' is not monitored in GDACS feeds; skipped.",
            )

        # 4. ReliefWeb Humanitarian Reports Execution
        reliefweb_data = UnifiedReliefWebData()
        if enable_reliefweb:
            sources_queried.append("ReliefWeb Humanitarian Reports")
            reliefweb_data = self._query_reliefweb(
                query_info=query_info,
                start_date=start_date,
                end_date=end_date,
                limit=reliefweb_limit,
            )
            if reliefweb_data.status in {"success", "no_matching_reports"}:
                sources_succeeded.append("ReliefWeb Humanitarian Reports")
            else:
                sources_failed["ReliefWeb Humanitarian Reports"] = reliefweb_data.error_message or "ReliefWeb query failed"

        # 5. NASA FIRMS Active Fire Execution
        firms_data = UnifiedFIRMSData()
        is_fire = (
            query_info.disaster_type in {"wildfire", "fire", "bushfire", "forest fire"}
            or "wildfire" in cleaned_query.lower()
            or "bushfire" in cleaned_query.lower()
            or "forest fire" in cleaned_query.lower()
            or (
                "fire" in cleaned_query.lower()
                and not any(w in cleaned_query.lower() for w in ["fire department", "crossfire", "ceasefire"])
            )
        )

        if enable_firms and is_fire:
            sources_queried.append("NASA FIRMS Active Fire")
            if not self.firms_client.config.is_configured:
                firms_data = UnifiedFIRMSData(
                    queried=True,
                    status="unconfigured",
                    error_message=(
                        "NASA FIRMS MAP_KEY is not configured. Request a free 32-character MAP_KEY at "
                        "https://firms.modaps.eosdis.nasa.gov/api/map_key and configure FIRMS_MAP_KEY in your .env file."
                    ),
                    satellite_source=self.firms_client.config.default_source,
                )
                sources_failed["NASA FIRMS Active Fire"] = firms_data.error_message
            else:
                firms_data = self._query_firms(
                    query_info=query_info,
                    start_date=start_date,
                    end_date=end_date,
                    limit=firms_limit,
                )
                if firms_data.status in {"success", "no_detections"}:
                    sources_succeeded.append("NASA FIRMS Active Fire")
                else:
                    sources_failed["NASA FIRMS Active Fire"] = firms_data.error_message or "FIRMS query failed"
        elif not is_fire:
            firms_data = UnifiedFIRMSData(
                queried=False,
                status="not_applicable",
                error_message="NASA FIRMS Active Fire is specialized for thermal anomaly and fire monitoring; skipped for this disaster type.",
            )

        # 6. Tavily Web Intelligence Execution
        tavily_data = UnifiedTavilyData()
        if enable_tavily:
            sources_queried.append("Tavily Web Intelligence")
            tavily_data = self._query_tavily(
                query_info=query_info,
                max_results=tavily_max_results,
            )
            if tavily_data.status in {"success", "empty_results"}:
                sources_succeeded.append("Tavily Web Intelligence")
            else:
                sources_failed["Tavily Web Intelligence"] = tavily_data.error_message or "Tavily search failed"

        # 7. Primary Geographic Coordinates Resolution
        primary_coords = self._resolve_coordinates(usgs_data, gdacs_data, firms_data)

        # 8. Build Source Attribution Map & Transparency Boundaries
        attributions, limitations, unavailable = self._build_provenance_and_limitations(
            query_info=query_info,
            usgs_data=usgs_data,
            gdacs_data=gdacs_data,
            reliefweb_data=reliefweb_data,
            firms_data=firms_data,
            tavily_data=tavily_data,
            primary_coords=primary_coords,
        )

        # 9. Spatial AOI Bounding Box Resolution & Benchmark Satellite Linkage
        loc_clean = (query_info.location or "").strip().lower()
        query_lower = cleaned_query.lower()
        resolved_bbox = None
        is_bm = False
        bm_run_id = None

        if "kerala" in loc_clean or "kerala" in query_lower or "cochin" in loc_clean or "kochi" in loc_clean:
            resolved_bbox = [76.2, 9.8, 76.6, 10.2]
            is_bm = True
            bm_run_id = "kerala_2018-08-10"
        elif "lucknow" in loc_clean or "lucknow" in query_lower or "gomti" in loc_clean:
            resolved_bbox = [80.85, 26.75, 81.05, 26.95]
            is_bm = True
            bm_run_id = "lucknow_2026-10-01"
        elif loc_clean in REGION_BOUNDING_BOXES:
            min_lat, max_lat, min_lon, max_lon = REGION_BOUNDING_BOXES[loc_clean]
            resolved_bbox = [min_lon, min_lat, max_lon, max_lat]
        elif primary_coords is not None:
            c_lat = primary_coords.latitude
            c_lon = primary_coords.longitude
            resolved_bbox = [round(c_lon - 0.2, 4), round(c_lat - 0.2, 4), round(c_lon + 0.2, 4), round(c_lat + 0.2, 4)]

        return UnifiedIncidentReport(
            original_query=cleaned_query,
            disaster_type=query_info.disaster_type,
            location=query_info.location,
            incident_date_str=query_info.event_date_str,
            query_window_start=start_date,
            query_window_end=end_date,
            primary_coordinates=primary_coords,
            sources_queried=sources_queried,
            sources_succeeded=sources_succeeded,
            sources_failed=sources_failed,
            usgs=usgs_data,
            gdacs=gdacs_data,
            reliefweb=reliefweb_data,
            firms=firms_data,
            tavily=tavily_data,
            source_attributions=attributions,
            data_limitations=limitations,
            unavailable_fields=unavailable,
            bbox=resolved_bbox,
            is_benchmark=is_bm,
            benchmark_run_id=bm_run_id,
        )

    # --------------------------------------------------------------------------
    # Subsystem Query Handlers
    # --------------------------------------------------------------------------
    def _query_usgs(
        self,
        query_info: DisasterQueryInfo,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> UnifiedUSGSData:
        """Queries USGS Earthquake Catalog and performs conservative location matching."""
        try:
            resp = self.usgs_client.query_earthquakes(
                start_time=start_date,
                end_time=end_date,
                limit=limit,
                order_by="magnitude",
            )

            matched: List[EarthquakeEvent] = []
            unmatched_diagnostics: List[str] = []
            unmatched_count = 0

            for ev in resp.events:
                is_match, reason = evaluate_event_location(
                    target_location=query_info.location,
                    event_texts=[ev.place],
                    latitude=ev.latitude,
                    longitude=ev.longitude,
                )
                if is_match:
                    matched.append(ev)
                else:
                    unmatched_count += 1
                    unmatched_diagnostics.append(
                        f"Event {ev.event_id} ('{ev.place}') [Centroid: Lat {ev.latitude}, Lon {ev.longitude}]: {reason}"
                    )

            status = "success" if matched else "no_matching_events"
            return UnifiedUSGSData(
                queried=True,
                status=status,
                matched_events=matched,
                unmatched_events_count=unmatched_count,
                unmatched_diagnostics=unmatched_diagnostics,
                total_catalog_events=resp.count,
                source_url=resp.api_url,
            )

        except (USGSClientError, Exception) as err:
            logger.error("USGS API execution failed: %s", err)
            return UnifiedUSGSData(
                queried=True,
                status="failed",
                error_message=str(err),
            )

    def _query_gdacs(
        self,
        query_info: DisasterQueryInfo,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> UnifiedGDACSData:
        """Queries GDACS alerts and performs conservative location matching."""
        try:
            type_code = None
            if query_info.disaster_type:
                type_map = {
                    "floods": "FL",
                    "earthquake": "EQ",
                    "cyclone": "TC",
                    "volcano": "VO",
                    "drought": "DR",
                    "wildfire": "WF",
                }
                type_code = type_map.get(query_info.disaster_type.lower())

            resp = self.gdacs_client.query_events(
                event_types=type_code,
                from_date=start_date,
                to_date=end_date,
                page_size=limit,
            )

            matched: List[GDACSEvent] = []
            unmatched_diagnostics: List[str] = []
            unmatched_count = 0

            for ev in resp.events:
                candidate_texts = [ev.country, ev.iso3, ev.name, ev.description]
                for c in ev.affected_countries:
                    candidate_texts.append(c.get("countryname"))
                    candidate_texts.append(c.get("iso3"))

                is_match, reason = evaluate_event_location(
                    target_location=query_info.location,
                    event_texts=candidate_texts,
                    latitude=ev.latitude,
                    longitude=ev.longitude,
                )

                if is_match:
                    matched.append(ev)
                else:
                    unmatched_count += 1
                    unmatched_diagnostics.append(
                        f"Event {ev.event_id} ('{ev.name}') [Country: {ev.country or 'Unknown'}, Centroid: Lat {ev.latitude}, Lon {ev.longitude}]: {reason}"
                    )

            status = "success" if matched else "no_matching_events"
            return UnifiedGDACSData(
                queried=True,
                status=status,
                matched_events=matched,
                unmatched_events_count=unmatched_count,
                unmatched_diagnostics=unmatched_diagnostics,
                total_alerts_found=resp.count,
                source_url=resp.api_url,
            )

        except (GDACSClientError, Exception) as err:
            logger.error("GDACS API execution failed: %s", err)
            return UnifiedGDACSData(
                queried=True,
                status="failed",
                error_message=str(err),
            )

    def _query_reliefweb(
        self,
        query_info: DisasterQueryInfo,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> UnifiedReliefWebData:
        """
        Queries ReliefWeb Reports API (v2) for humanitarian situation reports,
        impact assessments, and evaluations. Performs conservative location and date matching.
        """
        query_terms = []
        if query_info.location:
            query_terms.append(query_info.location)
        if query_info.disaster_type:
            query_terms.append(query_info.disaster_type)
        search_query = " ".join(query_terms) if query_terms else query_info.original_query

        # Map parent country if target is subnational
        country_filter = None
        if query_info.location:
            loc_norm = query_info.location.strip().lower()
            if loc_norm in SUBNATIONAL_PARENTS:
                country_filter = SUBNATIONAL_PARENTS[loc_norm].capitalize()
            elif loc_norm in LOCATION_SYNONYMS:
                country_filter = query_info.location

        try:
            resp = self.reliefweb_client.query_reports(
                query=search_query,
                country=country_filter,
                from_date=start_date,
                to_date=end_date,
                limit=max(limit, 10),
            )

            matched: List[ReliefWebReport] = []
            unmatched_diagnostics: List[str] = []
            unmatched_count = 0

            for rep in resp.reports:
                event_texts = [
                    rep.title,
                    rep.primary_country,
                    " ".join(rep.countries),
                    " ".join(rep.disaster_names),
                    rep.body_snippet,
                ]

                is_match, reason = evaluate_event_location(
                    target_location=query_info.location,
                    event_texts=event_texts,
                )

                if is_match:
                    temp_rel = "unknown"
                    if rep.publication_date_dt and query_info.event_year:
                        rep_year = rep.publication_date_dt.year
                        rep_month = rep.publication_date_dt.month
                        if query_info.event_month:
                            month_diff = (rep_year - query_info.event_year) * 12 + (rep_month - query_info.event_month)
                            if 0 <= month_diff <= 3:
                                temp_rel = "contemporaneous"
                            elif month_diff > 3:
                                temp_rel = "retrospective"
                        else:
                            if rep_year == query_info.event_year:
                                temp_rel = "contemporaneous"
                            elif rep_year > query_info.event_year:
                                temp_rel = "retrospective"

                    updated_rep = rep.model_copy(update={"temporal_relation": temp_rel})
                    matched.append(updated_rep)
                else:
                    unmatched_count += 1
                    unmatched_diagnostics.append(
                        f"Report {rep.report_id} ('{rep.title}') [Country: {rep.primary_country or 'N/A'}]: {reason}"
                    )

            status = "success" if matched else "no_matching_reports"
            return UnifiedReliefWebData(
                queried=True,
                status=status,
                matched_reports=matched,
                unmatched_reports_count=unmatched_count,
                unmatched_diagnostics=unmatched_diagnostics,
                total_reports_found=resp.total_count,
                source_url=resp.api_url,
            )

        except (ReliefWebClientError, Exception) as err:
            logger.error("ReliefWeb API execution failed: %s", err)
            return UnifiedReliefWebData(
                queried=True,
                status="failed",
                error_message=str(err),
            )

    def _query_tavily(
        self,
        query_info: DisasterQueryInfo,
        max_results: int,
    ) -> UnifiedTavilyData:
        """Queries Tavily Search API and processes verification evidence."""
        if self.tavily_service is None:
            return UnifiedTavilyData(
                queried=True,
                status="failed",
                error_message="Tavily service is unconfigured (TAVILY_API_KEY missing or placeholder).",
            )

        try:
            search_query = query_info.optimized_search_query or query_info.original_query
            search_resp = self.tavily_service.search(
                query=search_query,
                max_results=max_results,
                include_answer=True,
                optimize_query=False,  # Already pre-optimized by query_parser
            )

            raw_results = getattr(search_resp, "results", [])
            articles = [r for r in raw_results if isinstance(r, SearchResult)]

            if not articles:
                return UnifiedTavilyData(
                    queried=True,
                    status="empty_results",
                    article_count=0,
                )

            v_report = getattr(search_resp, "verification_report", None)

            # Build grounded claim-traceable summary from verification report
            if v_report is not None:
                synthesis = synthesize_incident_summary(query_info, articles, v_report)
            else:
                raw_synth = getattr(search_resp, "synthesized_summary", None)
                raw_ans = getattr(search_resp, "answer", None)
                if isinstance(raw_synth, str) and raw_synth.strip():
                    synthesis = raw_synth.strip()
                elif isinstance(raw_ans, str) and raw_ans.strip():
                    synthesis = raw_ans.strip()
                else:
                    synthesis = None

            verified_claims = [c for c in getattr(v_report, "verified_claims", []) if isinstance(c, ClaimEvidence)]
            corroborated_facts = [str(f) for f in getattr(v_report, "corroborated_facts", []) if isinstance(f, str)]
            conflicting_claims = [str(c) for c in getattr(v_report, "conflicting_claims", []) if isinstance(c, str)]
            single_source_claims = [str(s) for s in getattr(v_report, "single_source_claims", []) if isinstance(s, str)]

            return UnifiedTavilyData(
                queried=True,
                status="success",
                article_count=len(articles),
                articles=articles,
                synthesized_summary=synthesis,
                verified_claims=verified_claims,
                corroborated_facts=corroborated_facts,
                conflicting_claims=conflicting_claims,
                single_source_claims=single_source_claims,
            )

        except (TavilySearchError, ConfigurationError, Exception) as err:
            logger.error("Tavily search execution failed: %s", err)
            return UnifiedTavilyData(
                queried=True,
                status="failed",
                error_message=str(err),
            )

    def _query_firms(
        self,
        query_info: DisasterQueryInfo,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int = 20,
    ) -> UnifiedFIRMSData:
        """
        Queries NASA FIRMS Active Fire API for thermal anomaly detections within the
        incident region and relevant time window.
        Distinguishes satellite thermal detections from ground-verified wildfires.
        """
        loc_norm = query_info.location.strip().lower() if query_info.location else ""
        bbox = None
        country_code = None

        if loc_norm in REGION_BOUNDING_BOXES:
            min_lat, max_lat, min_lon, max_lon = REGION_BOUNDING_BOXES[loc_norm]
            # NASA FIRMS bbox order: west, south, east, north
            bbox = (min_lon, min_lat, max_lon, max_lat)
        elif loc_norm in SUBNATIONAL_PARENTS:
            parent = SUBNATIONAL_PARENTS[loc_norm]
            if parent in REGION_BOUNDING_BOXES:
                min_lat, max_lat, min_lon, max_lon = REGION_BOUNDING_BOXES[parent]
                bbox = (min_lon, min_lat, max_lon, max_lat)
            elif parent in COUNTRY_ISO3_MAP:
                country_code = COUNTRY_ISO3_MAP[parent]
        elif loc_norm in COUNTRY_ISO3_MAP:
            country_code = COUNTRY_ISO3_MAP[loc_norm]

        if not bbox and not country_code:
            return UnifiedFIRMSData(
                queried=True,
                status="no_geographic_bounds",
                error_message=f"No geographic bounding box or country code resolved for location '{query_info.location or 'Unspecified'}'.",
                satellite_source=self.firms_client.config.default_source,
            )

        # Date window handling: FIRMS area API takes day_range (1 to 10) and date (YYYY-MM-DD)
        # When start_date is None, omitting target_date allows FIRMS to return the latest near-real-time observations
        target_date = start_date
        day_range = 1
        if start_date and end_date:
            try:
                d1 = datetime.fromisoformat(start_date)
                d2 = datetime.fromisoformat(end_date)
                diff = abs((d2 - d1).days) + 1
                day_range = min(max(diff, 1), 10)
            except Exception:
                day_range = 1

        try:
            if bbox:
                resp = self.firms_client.query_area(
                    bbox=bbox,
                    day_range=day_range,
                    date_str=target_date,
                )
            else:
                resp = self.firms_client.query_country(
                    country_code=country_code,
                    day_range=day_range,
                    date_str=target_date,
                )

            detections = resp.detections[:limit]
            status = "success" if detections else "no_detections"

            return UnifiedFIRMSData(
                queried=True,
                status=status,
                matched_detections=detections,
                total_detections_found=resp.total_count,
                source_url=resp.api_url,
                satellite_source=resp.source_name,
            )

        except (FIRMSClientError, Exception) as err:
            logger.error("NASA FIRMS API execution failed: %s", err)
            return UnifiedFIRMSData(
                queried=True,
                status="failed",
                error_message=str(err),
                satellite_source=self.firms_client.config.default_source,
            )

    # --------------------------------------------------------------------------
    # Geographic & Provenance Helpers
    # --------------------------------------------------------------------------
    @staticmethod
    def _resolve_coordinates(
        usgs: UnifiedUSGSData,
        gdacs: UnifiedGDACSData,
        firms: Optional[UnifiedFIRMSData] = None,
    ) -> Optional[IncidentCoordinates]:
        """Resolves primary coordinates from authoritative sensor or alert centroids."""
        # Prefer USGS epicenter for seismic events if matched
        if usgs.matched_events:
            ev = usgs.matched_events[0]
            if ev.latitude is not None and ev.longitude is not None:
                return IncidentCoordinates(
                    latitude=ev.latitude,
                    longitude=ev.longitude,
                    depth_km=ev.depth_km,
                    coordinate_type="epicenter",
                    coordinate_label="USGS Earthquake Epicenter",
                    source=f"USGS Earthquake Catalog ({ev.place})",
                )

        # Fallback to GDACS alert centroid if matched
        if gdacs.matched_events:
            ev = gdacs.matched_events[0]
            if ev.latitude is not None and ev.longitude is not None:
                return IncidentCoordinates(
                    latitude=ev.latitude,
                    longitude=ev.longitude,
                    coordinate_type="centroid",
                    coordinate_label="GDACS Event Centroid",
                    source=f"GDACS Alert Centroid ({ev.name})",
                )

        # Fallback to FIRMS thermal anomaly detection point if wildfire
        if firms and firms.matched_detections:
            first_det = firms.matched_detections[0]
            sat_inst = f"{first_det.satellite or 'Satellite'} {first_det.instrument or 'Sensor'}"
            return IncidentCoordinates(
                latitude=first_det.latitude,
                longitude=first_det.longitude,
                coordinate_type="thermal_hotspot",
                coordinate_label="NASA FIRMS Thermal Hotspot",
                source=f"NASA FIRMS ({sat_inst})",
                disclaimer="Point satellite thermal detection; does not define wildfire perimeter, burn scar boundary, or active fireline.",
            )

        return None

    @staticmethod
    def _build_provenance_and_limitations(
        query_info: DisasterQueryInfo,
        usgs_data: UnifiedUSGSData,
        gdacs_data: UnifiedGDACSData,
        reliefweb_data: UnifiedReliefWebData,
        firms_data: UnifiedFIRMSData,
        tavily_data: UnifiedTavilyData,
        primary_coords: Optional[IncidentCoordinates],
    ) -> Tuple[Dict[str, str], List[str], List[str]]:
        """Constructs explicit source attribution and data boundary limitations."""
        attributions: Dict[str, str] = {}
        limitations: List[str] = []
        unavailable: List[str] = [
            "Official ground-truth casualty census (fatalities/injuries not certified by USGS or GDACS)",
            "Structural damage census and private property economic loss",
            "Pre/post-disaster satellite imagery and optical/SAR change detection",
            "In-situ ground sensor meteorological observations (precipitation gauges/anemometers)",
            "Cadastral boundary and street-level geocoded addresses",
        ]

        # Source attributions
        if primary_coords:
            attributions["incident_coordinates"] = primary_coords.source

        if usgs_data.matched_events:
            ev = usgs_data.matched_events[0]
            mag_str = f"M {ev.magnitude:.1f}" if ev.magnitude is not None else "Magnitude"
            attributions["seismic_magnitude_and_time"] = (
                f"USGS Earthquake Catalog ({mag_str}, ID: {ev.event_id})"
            )

        if gdacs_data.matched_events:
            gev = gdacs_data.matched_events[0]
            glide_str = f" (GLIDE: {gev.glide})" if gev.glide else ""
            attributions["disaster_alert_level_and_score"] = (
                f"GDACS / UN OCHA ({gev.alert_level} Alert, Score: {gev.alert_score}{glide_str})"
            )

        if reliefweb_data.matched_reports:
            attributions["humanitarian_situation_reports"] = (
                f"ReliefWeb / UN OCHA ({len(reliefweb_data.matched_reports)} situation reports & assessments)"
            )

        if firms_data.matched_detections:
            first_det = firms_data.matched_detections[0]
            sat_inst = f"{first_det.satellite or 'Satellite'} / {first_det.instrument or 'Sensor'}"
            attributions["active_fire_thermal_detections"] = (
                f"NASA FIRMS ({len(firms_data.matched_detections)} thermal anomaly pixels via {sat_inst})"
            )
            limitations.append(
                "NASA FIRMS detections represent satellite radiometer thermal anomalies (heat signatures). They do not define wildfire perimeters or ground truth without corroborating incident reports."
            )

        if tavily_data.articles:
            attributions["web_news_and_situational_reporting"] = (
                f"Tavily Search Engine ({len(tavily_data.articles)} independent web articles)"
            )

        # Limitations & transparency notices
        limitations.append(
            "GDACS event centroids and USGS epicenters are single-point approximations and must NOT be treated as the geographic perimeter, flood inundation boundary, or disaster footprint."
        )
        limitations.append(
            "GDACS alert scores reflect algorithmic severity and humanitarian exposure models, not confirmed ground destruction."
        )
        limitations.append(
            "USGS Earthquake Catalog records physical seismic sensor telemetry; shake impact and casualty models are preliminary."
        )
        limitations.append(
            "ReliefWeb situation reports provide organizational humanitarian assessments and operational estimates. Casualty and displacement figures represent agency-reported emergency estimates, NOT independently verified census data or ground truth."
        )
        limitations.append(
            "Casualty counts and operational updates originate from journalistic media reports; official government confirmation is required."
        )
        limitations.append(
            "Heuristic cross-source corroboration across web news reports is provisional (heuristic text comparison) and does not replace official ground sensor or administrative censuses."
        )

        if usgs_data.unmatched_events_count > 0:
            limitations.append(
                f"{usgs_data.unmatched_events_count} seismic event(s) occurred in the temporal window but did not match the queried location '{query_info.location}'."
            )

        if gdacs_data.unmatched_events_count > 0:
            limitations.append(
                f"{gdacs_data.unmatched_events_count} active GDACS alert(s) in the query window were excluded (outside '{query_info.location}')."
            )

        if reliefweb_data.unmatched_reports_count > 0:
            limitations.append(
                f"{reliefweb_data.unmatched_reports_count} ReliefWeb report(s) in the query window were excluded (outside '{query_info.location}')."
            )

        return attributions, limitations, unavailable

    # --------------------------------------------------------------------------
    # Human-Readable Display Formatting
    # --------------------------------------------------------------------------
    @staticmethod
    def format_unified_report_for_display(report: UnifiedIncidentReport) -> str:
        """Formats the UnifiedIncidentReport into a structured terminal report."""
        lines = []
        d_thick = "=" * 80
        d_thin = "-" * 80

        lines.append(d_thick)
        lines.append(" UNIFIED DISASTER INTELLIGENCE PIPELINE REPORT")
        lines.append(d_thick)
        lines.append(f" Query                  : {report.original_query}")
        lines.append(f" Hazard Category        : {report.disaster_type or 'General / Multi-Hazard'}")
        lines.append(f" Target Location        : {report.location or 'Unspecified'}")
        lines.append(f" Incident Date / Window : {report.incident_date_str or 'Unspecified'} ({report.query_window_start or 'N/A'} to {report.query_window_end or 'N/A'})")

        if report.primary_coordinates:
            pc = report.primary_coordinates
            depth_str = f", Depth: {pc.depth_km:.1f} km" if pc.depth_km is not None else ""
            if pc.coordinate_type == "centroid":
                lines.append(f" GDACS Event Centroid   : Lat {pc.latitude:.4f}, Lon {pc.longitude:.4f} (Point Estimate)")
                lines.append(f" Coordinate Source      : {pc.source}")
                lines.append(" Spatial Footprint Note : Point centroid does NOT represent the spatial disaster boundary or inundation extent.")
            elif pc.coordinate_type == "epicenter":
                lines.append(f" USGS Earthquake Epicenter: Lat {pc.latitude:.4f}, Lon {pc.longitude:.4f} (Point Sensor Telemetry{depth_str})")
                lines.append(f" Coordinate Source      : {pc.source}")
                lines.append(" Spatial Footprint Note : Point epicenter does NOT represent the full fault rupture zone or ground shake area.")
            else:
                lines.append(f" {pc.coordinate_label:<23}: Lat {pc.latitude:.4f}, Lon {pc.longitude:.4f}")
                lines.append(f" Coordinate Source      : {pc.source}")
        else:
            lines.append(" Incident Coordinates   : Unavailable from queried authoritative sensor/alert feeds")

        # Sources Execution Summary
        lines.append(f"\n{d_thin}")
        lines.append(" SOURCES EXECUTION SUMMARY")
        lines.append(d_thin)
        for src in report.sources_queried:
            if src in report.sources_succeeded:
                lines.append(f"  [+] {src:<28} : SUCCESS")
            else:
                err = report.sources_failed.get(src, "Failed")
                lines.append(f"  [!] {src:<28} : FAILED ({err})")

        # 1. USGS Seismic Intelligence
        if report.usgs.queried:
            lines.append(f"\n{d_thin}")
            lines.append(" 1. USGS EARTHQUAKE CATALOG (Seismic Telemetry)")
            lines.append(d_thin)
            if report.usgs.matched_events:
                for idx, ev in enumerate(report.usgs.matched_events, start=1):
                    mag_str = f"M {ev.magnitude:.1f} ({ev.magnitude_type})" if ev.magnitude is not None else "M Unknown"
                    lines.append(f"  * [Match {idx}] {mag_str} - {ev.place}")
                    lines.append(f"    Event ID     : {ev.event_id}")
                    lines.append(f"    Origin Time  : {ev.origin_time_str or 'Unknown'}")
                    lines.append(f"    Coordinates  : Lat {ev.latitude:.4f}, Lon {ev.longitude:.4f}, Depth: {ev.depth_km or 'N/A'} km")
                    if ev.alert_level:
                        lines.append(f"    PAGER Alert  : {ev.alert_level.upper()}")
                    if ev.url:
                        lines.append(f"    Catalog URL  : {ev.url}")
            elif report.usgs.status == "no_matching_events":
                lines.append(f"  [!] No earthquakes found matching '{report.location}' during the incident window.")
                if report.usgs.unmatched_events_count > 0:
                    lines.append(f"      (Note: {report.usgs.unmatched_events_count} earthquakes occurred elsewhere globally in this window).")
            elif report.usgs.status == "failed":
                lines.append(f"  [!] USGS Query Failed: {report.usgs.error_message}")

            if report.usgs.unmatched_diagnostics:
                lines.append(f"\n  Excluded Seismic Events ({len(report.usgs.unmatched_diagnostics)}):")
                for diag in report.usgs.unmatched_diagnostics[:3]:
                    lines.append(f"    [x] {diag}")
        else:
            lines.append(f"\n{d_thin}")
            lines.append(" 1. USGS EARTHQUAKE CATALOG: Not Applicable (Non-seismic disaster)")

        # 2. GDACS Disaster Alerts
        if report.gdacs.queried:
            lines.append(f"\n{d_thin}")
            lines.append(" 2. GDACS DISASTER ALERTS (UN OCHA / European Commission)")
            lines.append(d_thin)
            if report.gdacs.matched_events:
                for idx, ev in enumerate(report.gdacs.matched_events, start=1):
                    lines.append(f"  * [Match {idx}] [{ev.alert_level.upper()} ALERT] {ev.name}")
                    lines.append(f"    Event ID     : {ev.event_id} (Episode {ev.episode_id or 'N/A'})")
                    lines.append(f"    GLIDE Number : {ev.glide or 'Not Assigned'}")
                    lines.append(f"    Alert Score  : {ev.alert_score or 'N/A'}")
                    lines.append(f"    Duration     : {ev.from_date_str or 'Unknown'} to {ev.to_date_str or 'Ongoing'}")
                    if ev.latitude is not None and ev.longitude is not None:
                        lines.append(f"    Centroid     : Lat {ev.latitude:.4f}, Lon {ev.longitude:.4f}")
                    if ev.severity_text:
                        lines.append(f"    Severity     : {ev.severity_text}")
                    if ev.report_url:
                        lines.append(f"    Report URL   : {ev.report_url}")
            elif report.gdacs.status == "no_matching_events":
                lines.append(f"  [!] No GDACS alerts found matching '{report.location}' during the incident window.")
                if report.gdacs.unmatched_events_count > 0:
                    lines.append(f"      (Note: {report.gdacs.unmatched_events_count} alerts were active in other regions during this window).")
            elif report.gdacs.status == "failed":
                lines.append(f"  [!] GDACS Query Failed: {report.gdacs.error_message}")

            if report.gdacs.unmatched_diagnostics:
                lines.append(f"\n  Excluded Unmatched Alerts ({len(report.gdacs.unmatched_diagnostics)}):")
                for diag in report.gdacs.unmatched_diagnostics[:5]:
                    lines.append(f"    [x] {diag}")
        else:
            lines.append(f"\n{d_thin}")
            lines.append(" 2. GDACS DISASTER ALERTS: Not Applicable / Skipped")

        # 3. ReliefWeb Humanitarian Reports
        if report.reliefweb.queried:
            lines.append(f"\n{d_thin}")
            lines.append(" 3. RELIEFWEB HUMANITARIAN SITUATION REPORTS (UN OCHA)")
            lines.append(d_thin)
            if report.reliefweb.matched_reports:
                for idx, rep in enumerate(report.reliefweb.matched_reports, start=1):
                    sources_str = ", ".join(rep.sources) if rep.sources else "Unknown"
                    lines.append(f"  * [Report {idx}] {rep.title}")
                    lines.append(f"    Source/Org      : {sources_str}")
                    lines.append(f"    Format          : {rep.format or 'Humanitarian Report'}")
                    lines.append(f"    Publication Date: {rep.publication_date or 'Unknown'} (Report Publication Date, NOT Incident Date)")
                    lines.append(f"    Temporal Class  : {rep.temporal_relation.upper()}")
                    if rep.disaster_names:
                        lines.append(f"    Disaster Tag    : {', '.join(rep.disaster_names)}")
                    if rep.glide_numbers:
                        lines.append(f"    GLIDE Number    : {', '.join(rep.glide_numbers)}")
                    lines.append(f"    Report URL      : {rep.url}")
                    if rep.body_snippet:
                        snippet = rep.body_snippet[:180] + "..." if len(rep.body_snippet) > 180 else rep.body_snippet
                        lines.append(f"    Excerpt         : \"{snippet}\"")
                    lines.append("    Data Status     : [Reported Humanitarian Estimate - NOT Verified Ground Truth]")
            elif report.reliefweb.status == "no_matching_reports":
                lines.append(f"  [!] No ReliefWeb reports found matching '{report.location}' during the incident window.")
                if report.reliefweb.unmatched_reports_count > 0:
                    lines.append(f"      (Note: {report.reliefweb.unmatched_reports_count} reports occurred elsewhere in the date window).")
            elif report.reliefweb.status == "failed":
                lines.append(f"  [!] ReliefWeb Query Notice: {report.reliefweb.error_message}")

            if report.reliefweb.unmatched_diagnostics:
                lines.append(f"\n  Excluded Humanitarian Reports ({len(report.reliefweb.unmatched_diagnostics)}):")
                for diag in report.reliefweb.unmatched_diagnostics[:3]:
                    lines.append(f"    [x] {diag}")
        else:
            lines.append(f"\n{d_thin}")
            lines.append(" 3. RELIEFWEB HUMANITARIAN REPORTS: Skipped / Not Enabled")

        # 4. NASA FIRMS Active Fire Detections
        if report.firms.queried:
            lines.append(f"\n{d_thin}")
            lines.append(" 4. NASA FIRMS ACTIVE FIRE / THERMAL ANOMALIES (MODIS / VIIRS)")
            lines.append(d_thin)
            if report.firms.matched_detections:
                lines.append(f"  Feed Source         : {report.firms.satellite_source or 'VIIRS/MODIS'}")
                lines.append(f"  Detections Found    : {len(report.firms.matched_detections)} (Total in Window: {report.firms.total_detections_found})")
                lines.append("\n  Detected Fire Pixels (Thermal Anomalies):")
                for idx, det in enumerate(report.firms.matched_detections[:5], start=1):
                    dt_str = f"{det.acq_date} {det.acq_time or 'N/A'}"
                    sat_inst = f"{det.satellite or 'Sat'} ({det.instrument or 'Sensor'})"
                    bright = f"{det.brightness:.1f} K" if det.brightness is not None else "N/A"
                    frp = f"{det.frp:.1f} MW" if det.frp is not None else "N/A"
                    lines.append(f"  * [Pixel {idx}] Lat {det.latitude:.4f}, Lon {det.longitude:.4f} | {dt_str} | {sat_inst}")
                    lines.append(f"    Confidence: {(det.confidence or 'N/A').upper()} | Brightness: {bright} | FRP: {frp}")
                if len(report.firms.matched_detections) > 5:
                    lines.append(f"    ... and {len(report.firms.matched_detections) - 5} additional fire detections.")
                lines.append("\n  Data Status         : [Satellite Thermal Anomaly - NOT Confirmed Ground Wildfire]")
            elif report.firms.status == "no_detections":
                lines.append(f"  [!] No active fire thermal anomalies detected in '{report.location}' during the query window.")
            elif report.firms.status == "unconfigured":
                lines.append("  [!] NASA FIRMS MAP_KEY is not configured.")
                lines.append("      Obtain a free 32-character key at https://firms.modaps.eosdis.nasa.gov/api/map_key and configure FIRMS_MAP_KEY in .env.")
            elif report.firms.status == "failed":
                lines.append(f"  [!] NASA FIRMS Query Notice: {report.firms.error_message}")
            else:
                lines.append(f"  [!] NASA FIRMS Status: {report.firms.status} ({report.firms.error_message or 'No data'})")

            lines.append("\n  Scientific Notice:")
            lines.append("    Satellite fire detections represent thermal anomalies/heat signatures. Detections")
            lines.append("    can include agricultural burning or industrial flaring and should not be treated")
            lines.append("    as definitive proof of a wildfire without corroborating ground context.")
        else:
            lines.append(f"\n{d_thin}")
            lines.append(" 4. NASA FIRMS ACTIVE FIRE: Not Applicable (Non-fire disaster)")

        # 5. Tavily Web Intelligence & Verification
        lines.append(f"\n{d_thin}")
        lines.append(" 5. TAVILY WEB INTELLIGENCE & CORROBORATION")
        lines.append(d_thin)
        if report.tavily.articles:
            lines.append(f"  Retrieved Articles : {len(report.tavily.articles)}")
            if report.tavily.synthesized_summary:
                lines.append(f"\n  Synthesized Overview (Claim-Traceable Summary):\n    {report.tavily.synthesized_summary}")

            # Evidence-Traced Claim Assessment Table
            if report.tavily.verified_claims:
                lines.append("\n  Evidence-Traced Claim Assessment:")
                for claim in report.tavily.verified_claims:
                    lines.append(f"    * [{claim.status.upper()}] {claim.topic}: {claim.claim}")
                    if claim.sources:
                        for s in claim.sources[:2]:
                            lines.append(f"      - Source: {s.get('domain')} ({s.get('url')})")
                            lines.append(f"        Excerpt: \"{s.get('quote')}\"")
                    lines.append(f"      Evaluation: {claim.evidence_explanation}")

            if report.tavily.corroborated_facts:
                lines.append("\n  Corroborated Multi-Source Facts:")
                for fact in report.tavily.corroborated_facts[:5]:
                    lines.append(f"    [+] {fact}")

            if report.tavily.conflicting_claims:
                lines.append("\n  Conflicting / Divergent Media Claims:")
                for conf in report.tavily.conflicting_claims[:3]:
                    lines.append(f"    [~] {conf}")

            lines.append("\n  Key Web Sources:")
            for art in report.tavily.articles[:4]:
                pub = f" (Pub: {art.published_date})" if art.published_date else ""
                lines.append(f"    - [{art.source_credibility.upper()}] {art.title}{pub}")
                lines.append(f"      URL: {art.url}")
        elif report.tavily.status == "failed":
            lines.append(f"  [!] Tavily Search Failed: {report.tavily.error_message}")
        else:
            lines.append("  [!] No web intelligence articles retrieved for this incident.")

        # 6. Source Attributions
        lines.append(f"\n{d_thin}")
        lines.append(" 6. FACTUAL SOURCE ATTRIBUTIONS")
        lines.append(d_thin)
        for key, src_val in report.source_attributions.items():
            formatted_key = key.replace("_", " ").title()
            lines.append(f"  * {formatted_key:<30}: {src_val}")

        # 7. Data Limitations & Missing Data
        lines.append(f"\n{d_thin}")
        lines.append(" 7. DATA BOUNDARIES & UNAVAILABLE FIELDS")
        lines.append(d_thin)
        lines.append("  Known Limitations:")
        for lim in report.data_limitations:
            lines.append(f"    - {lim}")

        lines.append("\n  Fields Currently Unavailable (Pending Future Integrations):")
        for unav in report.unavailable_fields:
            lines.append(f"    - {unav}")

        lines.append(f"\n{d_thick}")
        return "\n".join(lines)


# ------------------------------------------------------------------------------
# CLI Runner
# ------------------------------------------------------------------------------
def main() -> int:
    """Command-line interface for the unified disaster intelligence pipeline."""
    parser = argparse.ArgumentParser(
        description="Unified Disaster Intelligence Pipeline (Tavily, USGS, GDACS, ReliefWeb, NASA FIRMS)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Disaster incident query (e.g. 'Turkey earthquake on February 6, 2023' or 'Kerala floods August 2018')",
    )
    parser.add_argument(
        "-q", "--query-flag",
        dest="flag_query",
        default=None,
        help="Explicit query flag (alternative to positional argument).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON incident report instead of human-readable text.",
    )
    parser.add_argument(
        "--no-tavily",
        action="store_true",
        help="Skip Tavily web intelligence query.",
    )
    parser.add_argument(
        "--no-usgs",
        action="store_true",
        help="Skip USGS Earthquake Catalog query.",
    )
    parser.add_argument(
        "--no-gdacs",
        action="store_true",
        help="Skip GDACS disaster alert query.",
    )
    parser.add_argument(
        "--no-reliefweb",
        action="store_true",
        help="Skip ReliefWeb humanitarian situation reports query.",
    )
    parser.add_argument(
        "--no-firms",
        action="store_true",
        help="Skip NASA FIRMS active fire query.",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=10,
        help="Maximum results per subsystem feed.",
    )

    args = parser.parse_args()

    # UTF-8 stdout configuration for Windows consoles
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    target_query = (args.query or args.flag_query or "").strip()
    if not target_query:
        print("[!] Error: Please provide a disaster incident query.", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    pipeline = DisasterPipeline()
    report = pipeline.process_query(
        query=target_query,
        enable_tavily=not args.no_tavily,
        enable_usgs=not args.no_usgs,
        enable_gdacs=not args.no_gdacs,
        enable_reliefweb=not args.no_reliefweb,
        enable_firms=not args.no_firms,
        tavily_max_results=min(args.limit, 10),
        usgs_limit=args.limit,
        gdacs_limit=args.limit,
        reliefweb_limit=min(args.limit, 10),
        firms_limit=args.limit,
    )

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(DisasterPipeline.format_unified_report_for_display(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
