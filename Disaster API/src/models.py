"""
Data models for Tavily search results, disaster intelligence queries, and source verification.
Uses Pydantic for strong typing, validation, and JSON serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field


class DisasterEventMetadata(BaseModel):
    """
    Metadata extracted from natural-language disaster queries.
    """
    model_config = ConfigDict(frozen=True)

    original_query: str = Field(..., description="Original user search query")
    disaster_type: Optional[str] = Field(default=None, description="Identified disaster hazard type (e.g. floods, earthquake)")
    location: Optional[str] = Field(default=None, description="Identified incident location or jurisdiction")
    event_year: Optional[int] = Field(default=None, description="Identified incident year")
    event_month: Optional[int] = Field(default=None, description="Identified incident month number (1-12)")
    event_date_str: Optional[str] = Field(default=None, description="Human-readable event date string (e.g. 'July 2005')")
    optimized_search_query: str = Field(..., description="Targeted query constructed for Tavily Search")


class ClaimEvidence(BaseModel):
    """
    Detailed evidence and source citations for an individual factual claim.
    """
    model_config = ConfigDict(frozen=True)

    topic: str = Field(..., description="Domain/topic (e.g. 'Event Date', 'Rainfall', 'Casualties', 'Displacement')")
    claim: str = Field(..., description="Summary of the specific incident fact or figure")
    status: str = Field(..., description="Status: 'corroborated', 'single_source', 'conflicting', or 'unverified'")
    sources: List[dict] = Field(
        default_factory=list,
        description="List of supporting sources containing 'domain', 'url', and 'quote'.",
    )
    evidence_explanation: str = Field(..., description="Transparent evaluation of source consensus or discrepancy.")


class CrossVerificationReport(BaseModel):
    """
    Results of comparing factual claims across independent retrieved sources.
    """
    model_config = ConfigDict(frozen=True)

    verified_claims: List[ClaimEvidence] = Field(
        default_factory=list,
        description="Structured claim-by-claim verification evidence with source URLs.",
    )
    corroborated_facts: List[str] = Field(
        default_factory=list,
        description="Factual claims corroborated by 2 or more independent sources.",
    )
    single_source_claims: List[str] = Field(
        default_factory=list,
        description="Operational details or claims supported by only a single source.",
    )
    conflicting_claims: List[str] = Field(
        default_factory=list,
        description="Conflicting, divergent, or unverified claims (e.g. differing casualty counts).",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Explicit limitations and caveats regarding evidence sufficiency.",
    )


class SearchResult(BaseModel):
    """
    Represents an individual search result item returned by Tavily,
    augmented with source credibility, temporal classification, and filtering metadata.
    """
    model_config = ConfigDict(frozen=True)

    title: str = Field(..., description="Title of the webpage or news article")
    url: str = Field(..., description="Source URL of the article")
    content: str = Field(..., description="Extracted relevant text snippet or summary")
    score: Optional[float] = Field(
        default=None,
        description="Search Relevance Score: Algorithmic keyword match score from Tavily (NOT factual confidence).",
    )
    published_date: Optional[str] = Field(
        default=None,
        description="Web publication timestamp of the source article (NOT the actual disaster event date).",
    )
    raw_content: Optional[str] = Field(default=None, description="Raw content if requested")

    # Source credibility & temporal metadata
    domain: str = Field(default="unknown", description="Normalized source domain name")
    source_credibility: str = Field(
        default="general_web",
        description="Credibility classification: 'official_or_academic', 'established_news', 'low_value', 'general_web'.",
    )
    temporal_category: str = Field(
        default="unknown",
        description="Temporal classification relative to event date: 'contemporaneous', 'retrospective', or 'unknown'.",
    )
    relevance_explanation: Optional[str] = Field(
        default=None,
        description="Explanation of why this result was retained, categorized, or downgraded.",
    )
    is_duplicate: bool = Field(default=False, description="True if marked as a duplicate of an earlier result.")
    is_filtered: bool = Field(default=False, description="True if excluded from final retained intelligence.")
    filter_reason: Optional[str] = Field(default=None, description="Reason for exclusion if filtered.")


class SearchResponse(BaseModel):
    """
    Aggregated search response for a disaster query with full verification analytics.
    """
    query: str = Field(..., description="Original query string searched")
    actual_search_query: Optional[str] = Field(default=None, description="Actual query string executed against Tavily")
    event_info: Optional[DisasterEventMetadata] = Field(default=None, description="Extracted disaster event metadata")

    results: List[SearchResult] = Field(default_factory=list, description="All raw search result items retrieved")
    retained_results: List[SearchResult] = Field(default_factory=list, description="Curated, verified, non-duplicate results")
    filtered_results: List[SearchResult] = Field(default_factory=list, description="Filtered, low-value, or duplicate results")

    total_results: int = Field(default=0, description="Total count of results retrieved from Tavily")
    total_retained: int = Field(default=0, description="Count of results retained after filtering")
    total_filtered: int = Field(default=0, description="Count of results filtered out")

    verification_report: Optional[CrossVerificationReport] = Field(default=None, description="Multi-source cross-verification analysis")
    synthesized_incident_summary: Optional[str] = Field(default=None, description="Evidence-based incident summary")

    response_time: Optional[float] = Field(default=None, description="Time taken by Tavily API in seconds")
    answer: Optional[str] = Field(
        default=None,
        description="Synthesized direct answer or overview generated by Tavily if requested.",
    )
    
    # Boundary guard: News reports are preliminary web intelligence, NOT verified ground truth.
    is_verified_ground_truth: bool = Field(
        default=False,
        description="Explicit flag: News/web results are unverified reports, not ground truth."
    )
    disclaimer: str = Field(
        default="Web intelligence retrieved via Tavily Search API. News reports provide initial context and must not be assumed as verified ground truth without satellite data confirmation.",
        description="Standard disclaimer regarding web intelligence reliability."
    )

    @classmethod
    def from_tavily_payload(
        cls,
        query: str,
        payload: dict,
        response_time: Optional[float] = None,
        actual_search_query: Optional[str] = None,
        event_info: Optional[DisasterEventMetadata] = None,
    ) -> "SearchResponse":
        """
        Parses raw dictionary response from Tavily Python SDK into strongly-typed SearchResponse.
        """
        raw_results = payload.get("results", []) or []
        parsed_results: List[SearchResult] = []

        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip() or "Untitled"
            url = (item.get("url") or "").strip()
            content = (item.get("content") or "").strip()

            # Handle optional score
            score = item.get("score")
            if score is not None:
                try:
                    score = float(score)
                except (ValueError, TypeError):
                    score = None

            published_date = item.get("published_date") or item.get("publishedDate")
            raw_content = item.get("raw_content")

            # Extract basic domain
            domain = "unknown"
            if url:
                try:
                    p = urlparse(url)
                    d = p.netloc.lower()
                    domain = d[4:] if d.startswith("www.") else d
                except Exception:
                    domain = "unknown"

            parsed_results.append(
                SearchResult(
                    title=title,
                    url=url,
                    content=content,
                    score=score,
                    published_date=published_date,
                    raw_content=raw_content,
                    domain=domain,
                )
            )

        raw_answer = payload.get("answer")
        answer = raw_answer.strip() if isinstance(raw_answer, str) and raw_answer.strip() else None

        return cls(
            query=query,
            actual_search_query=actual_search_query or query,
            event_info=event_info,
            results=parsed_results,
            retained_results=parsed_results,
            total_results=len(parsed_results),
            total_retained=len(parsed_results),
            total_filtered=0,
            response_time=response_time,
            answer=answer,
        )


class GeoBounds(BaseModel):
    """
    Geographic bounding box for spatial filtering and API queries.
    """
    model_config = ConfigDict(frozen=True)

    min_latitude: float = Field(..., ge=-90.0, le=90.0, description="Minimum latitude (-90 to 90)")
    max_latitude: float = Field(..., ge=-90.0, le=90.0, description="Maximum latitude (-90 to 90)")
    min_longitude: float = Field(..., ge=-180.0, le=180.0, description="Minimum longitude (-180 to 180)")
    max_longitude: float = Field(..., ge=-180.0, le=180.0, description="Maximum longitude (-180 to 180)")


class EarthquakeEvent(BaseModel):
    """
    Represents a normalized seismic event record retrieved from the USGS Earthquake API.
    """
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="Unique USGS event identifier (e.g. 'us6000jllz')")
    magnitude: Optional[float] = Field(default=None, description="Primary earthquake magnitude")
    magnitude_type: Optional[str] = Field(default=None, description="Magnitude scale/type (e.g. 'mww', 'ml', 'mb')")
    place: str = Field(default="Unknown location", description="Geographic description of the epicenter location")
    origin_time: Optional[datetime] = Field(default=None, description="Origin time of the seismic rupture (UTC)")
    origin_time_str: Optional[str] = Field(default=None, description="ISO-8601 formatted origin time string")
    longitude: Optional[float] = Field(default=None, description="Epicenter longitude (-180 to 180)")
    latitude: Optional[float] = Field(default=None, description="Epicenter latitude (-90 to 90)")
    depth_km: Optional[float] = Field(default=None, description="Focal depth in kilometers")
    url: Optional[str] = Field(default=None, description="Official USGS event page URL")

    # Optional secondary seismological metadata
    alert_level: Optional[str] = Field(default=None, description="PAGER alert level: 'green', 'yellow', 'orange', 'red'")
    mmi: Optional[float] = Field(default=None, description="Maximum Modified Mercalli Intensity")
    felt_reports: Optional[int] = Field(default=None, description="Number of Did You Feel It? (DYFI) citizen responses")
    significance: Optional[int] = Field(default=None, description="USGS event significance score (0 to 1000+)")
    event_type: str = Field(default="earthquake", description="Event type classification (typically 'earthquake')")
    status: Optional[str] = Field(default=None, description="Review status: 'automatic' or 'reviewed'")

    @classmethod
    def from_geojson_feature(cls, feature: dict) -> "EarthquakeEvent":
        """
        Parses an individual GeoJSON Feature dictionary from USGS into a normalized EarthquakeEvent.
        """
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []

        lon = float(coords[0]) if len(coords) >= 1 and coords[0] is not None else None
        lat = float(coords[1]) if len(coords) >= 2 and coords[1] is not None else None
        depth = float(coords[2]) if len(coords) >= 3 and coords[2] is not None else None

        raw_mag = props.get("mag")
        mag = None
        if raw_mag is not None:
            try:
                mag = float(raw_mag)
            except (ValueError, TypeError):
                mag = None

        raw_time = props.get("time")
        origin_dt = None
        origin_str = None
        if raw_time is not None:
            try:
                # USGS timestamps are in milliseconds since epoch
                origin_dt = datetime.fromtimestamp(float(raw_time) / 1000.0, tz=timezone.utc)
                origin_str = origin_dt.isoformat()
            except (ValueError, TypeError, OSError):
                origin_dt = None
                origin_str = None

        event_id = str(feature.get("id") or props.get("code") or "unknown").strip()
        place = str(props.get("place") or "Unknown location").strip()
        mag_type = props.get("magType")
        url = props.get("url")

        raw_mmi = props.get("mmi")
        mmi = None
        if raw_mmi is not None:
            try:
                mmi = float(raw_mmi)
            except (ValueError, TypeError):
                mmi = None

        raw_felt = props.get("felt")
        felt = None
        if raw_felt is not None:
            try:
                felt = int(raw_felt)
            except (ValueError, TypeError):
                felt = None

        raw_sig = props.get("sig")
        sig = None
        if raw_sig is not None:
            try:
                sig = int(raw_sig)
            except (ValueError, TypeError):
                sig = None

        return cls(
            event_id=event_id,
            magnitude=mag,
            magnitude_type=str(mag_type) if mag_type else None,
            place=place,
            origin_time=origin_dt,
            origin_time_str=origin_str,
            longitude=lon,
            latitude=lat,
            depth_km=depth,
            url=str(url) if url else None,
            alert_level=props.get("alert"),
            mmi=mmi,
            felt_reports=felt,
            significance=sig,
            event_type=str(props.get("type") or "earthquake"),
            status=props.get("status"),
        )


class EarthquakeQueryResponse(BaseModel):
    """
    Aggregated response from querying the USGS Earthquake API.
    """
    model_config = ConfigDict(frozen=True)

    count: int = Field(default=0, description="Total number of seismic events matching query criteria")
    events: List[EarthquakeEvent] = Field(default_factory=list, description="List of normalized earthquake events")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters used for the query")
    api_url: Optional[str] = Field(default=None, description="USGS query URL executed")
    disclaimer: str = Field(
        default="Official earthquake catalog data retrieved from USGS Earthquake Hazards Program.",
        description="Data provenance notice"
    )

    @classmethod
    def from_geojson(
        cls,
        payload: dict,
        query_params: Optional[dict] = None,
        api_url: Optional[str] = None,
    ) -> "EarthquakeQueryResponse":
        """
        Parses a USGS GeoJSON FeatureCollection dictionary into an EarthquakeQueryResponse.
        """
        features = payload.get("features", []) or []
        events: List[EarthquakeEvent] = []
        for feat in features:
            if isinstance(feat, dict):
                try:
                    events.append(EarthquakeEvent.from_geojson_feature(feat))
                except Exception:
                    continue

        metadata = payload.get("metadata") or {}
        count = metadata.get("count", len(events))
        try:
            count = int(count)
        except (ValueError, TypeError):
            count = len(events)

        return cls(
            count=count,
            events=events,
            query_params=query_params or {},
            api_url=api_url,
        )


class GDACSEvent(BaseModel):
    """
    Represents a normalized disaster alert event record from the Global Disaster Alert and Coordination System (GDACS).
    """
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="Unique GDACS event identifier")
    episode_id: Optional[str] = Field(default=None, description="GDACS episode identifier")
    event_type: str = Field(..., description="Two-letter hazard type code (e.g. 'EQ', 'TC', 'FL', 'VO', 'DR', 'WF')")
    event_type_name: str = Field(..., description="Full disaster type name (e.g. 'Earthquake', 'Flood')")
    name: str = Field(default="Unknown disaster event", description="Title or headline description of the event")
    description: Optional[str] = Field(default=None, description="Detailed event summary")
    htmldescription: Optional[str] = Field(default=None, description="Formatted HTML description snippet")
    glide: Optional[str] = Field(default=None, description="Official GLIDE disaster identifier (e.g. 'EQ-2023-000015-TUR')")
    alert_level: str = Field(default="Unknown", description="GDACS alert severity level: 'Red', 'Orange', 'Green'")
    alert_score: Optional[float] = Field(default=None, description="GDACS overall alert score (0 to 3+)")
    episode_alert_level: Optional[str] = Field(default=None, description="Episode-specific alert level")
    episode_alert_score: Optional[float] = Field(default=None, description="Episode-specific alert score")
    country: Optional[str] = Field(default=None, description="Primary affected country name")
    iso3: Optional[str] = Field(default=None, description="Three-letter ISO country code")
    from_date: Optional[datetime] = Field(default=None, description="Incident start timestamp (UTC)")
    from_date_str: Optional[str] = Field(default=None, description="ISO-8601 formatted start timestamp")
    to_date: Optional[datetime] = Field(default=None, description="Incident end or latest reported timestamp (UTC)")
    to_date_str: Optional[str] = Field(default=None, description="ISO-8601 formatted end timestamp")
    longitude: Optional[float] = Field(default=None, description="Centroid longitude (-180 to 180)")
    latitude: Optional[float] = Field(default=None, description="Centroid latitude (-90 to 90)")
    bbox: Optional[List[float]] = Field(default=None, description="Bounding box [min_lon, min_lat, max_lon, max_lat]")
    report_url: Optional[str] = Field(default=None, description="Official GDACS public situation report URL")
    details_url: Optional[str] = Field(default=None, description="GDACS API event data URL")
    geometry_url: Optional[str] = Field(default=None, description="GDACS API polygon geometry URL")
    severity: Optional[float] = Field(default=None, description="Physical severity metric value (magnitude, wind speed, etc.)")
    severity_unit: Optional[str] = Field(default=None, description="Unit for physical severity (e.g. 'M', 'km/h')")
    severity_text: Optional[str] = Field(default=None, description="Textual description of physical severity")
    affected_countries: List[Dict[str, Any]] = Field(default_factory=list, description="List of affected countries with iso codes")
    impacts: List[Dict[str, Any]] = Field(default_factory=list, description="Available impact assessment references or impact metrics from GDACS")
    is_current: bool = Field(default=False, description="True if the alert is currently active")

    @classmethod
    def from_geojson_feature(cls, feature: dict) -> "GDACSEvent":
        """
        Parses a GeoJSON Feature from GDACS into a normalized GDACSEvent.
        """
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []

        lon = None
        lat = None
        if isinstance(coords, (list, tuple)):
            if len(coords) >= 1 and coords[0] is not None:
                try:
                    lon = float(coords[0])
                except (ValueError, TypeError):
                    lon = None
            if len(coords) >= 2 and coords[1] is not None:
                try:
                    lat = float(coords[1])
                except (ValueError, TypeError):
                    lat = None

        raw_bbox = feature.get("bbox")
        bbox_list = None
        if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
            try:
                bbox_list = [float(b) for b in raw_bbox]
            except (ValueError, TypeError):
                bbox_list = None

        # Event type mapping
        type_code = str(props.get("eventtype") or "Unknown").upper().strip()
        type_map = {
            "EQ": "Earthquake",
            "TC": "Tropical Cyclone",
            "FL": "Flood",
            "VO": "Volcano",
            "DR": "Drought",
            "WF": "Wildfire",
        }
        type_name = type_map.get(type_code, type_code.capitalize())

        raw_id = props.get("eventid") or feature.get("id") or "unknown"
        event_id = str(raw_id).strip()

        raw_ep_id = props.get("episodeid")
        episode_id = str(raw_ep_id).strip() if raw_ep_id is not None else None

        name = str(props.get("name") or props.get("eventname") or props.get("description") or f"{type_name} Event").strip()
        desc = props.get("description")
        html_desc = props.get("htmldescription")
        glide = props.get("glide")

        # Alert level & scores
        alert_lvl = str(props.get("alertlevel") or "Unknown").capitalize().strip()
        raw_score = props.get("alertscore")
        alert_score = None
        if raw_score is not None:
            try:
                alert_score = float(raw_score)
            except (ValueError, TypeError):
                alert_score = None

        ep_alert_lvl = str(props.get("episodealertlevel")).capitalize().strip() if props.get("episodealertlevel") else None
        raw_ep_score = props.get("episodealertscore")
        ep_alert_score = None
        if raw_ep_score is not None:
            try:
                ep_alert_score = float(raw_ep_score)
            except (ValueError, TypeError):
                ep_alert_score = None

        # Timestamps
        from_dt = None
        from_str = None
        if props.get("fromdate"):
            try:
                dt_raw = datetime.fromisoformat(str(props["fromdate"]))
                from_dt = dt_raw if dt_raw.tzinfo else dt_raw.replace(tzinfo=timezone.utc)
                from_str = from_dt.isoformat()
            except (ValueError, TypeError):
                from_dt = None
                from_str = str(props["fromdate"])

        to_dt = None
        to_str = None
        if props.get("todate"):
            try:
                dt_raw = datetime.fromisoformat(str(props["todate"]))
                to_dt = dt_raw if dt_raw.tzinfo else dt_raw.replace(tzinfo=timezone.utc)
                to_str = to_dt.isoformat()
            except (ValueError, TypeError):
                to_dt = None
                to_str = str(props["todate"])

        # URLs
        url_info = props.get("url") or {}
        report_url = None
        details_url = None
        geom_url = None
        if isinstance(url_info, dict):
            report_url = url_info.get("report")
            details_url = url_info.get("details")
            geom_url = url_info.get("geometry")
        elif isinstance(url_info, str):
            report_url = url_info

        # Physical severity
        sev_data = props.get("severitydata") or {}
        severity = None
        sev_unit = None
        sev_text = None
        if isinstance(sev_data, dict):
            raw_sev = sev_data.get("severity")
            if raw_sev is not None:
                try:
                    severity = float(raw_sev)
                except (ValueError, TypeError):
                    severity = None
            sev_unit = sev_data.get("severityunit")
            sev_text = sev_data.get("severitytext")

        # Affected countries and impacts
        aff_countries = props.get("affectedcountries") or []
        countries_list = [c for c in aff_countries if isinstance(c, dict)]

        raw_impacts = props.get("impacts") or []
        impacts_list = [i for i in raw_impacts if isinstance(i, dict)] if isinstance(raw_impacts, list) else []

        # Status
        is_cur = str(props.get("iscurrent", "")).lower() == "true"

        return cls(
            event_id=event_id,
            episode_id=episode_id,
            event_type=type_code,
            event_type_name=type_name,
            name=name,
            description=str(desc).strip() if desc else None,
            htmldescription=str(html_desc).strip() if html_desc else None,
            glide=str(glide).strip() if glide else None,
            alert_level=alert_lvl,
            alert_score=alert_score,
            episode_alert_level=ep_alert_lvl,
            episode_alert_score=ep_alert_score,
            country=str(props.get("country")).strip() if props.get("country") else None,
            iso3=str(props.get("iso3")).strip() if props.get("iso3") else None,
            from_date=from_dt,
            from_date_str=from_str,
            to_date=to_dt,
            to_date_str=to_str,
            longitude=lon,
            latitude=lat,
            bbox=bbox_list,
            report_url=str(report_url) if report_url else None,
            details_url=str(details_url) if details_url else None,
            geometry_url=str(geom_url) if geom_url else None,
            severity=severity,
            severity_unit=str(sev_unit).strip() if sev_unit else None,
            severity_text=str(sev_text).strip() if sev_text else None,
            affected_countries=countries_list,
            impacts=impacts_list,
            is_current=is_cur,
        )


class GDACSQueryResponse(BaseModel):
    """
    Aggregated response from querying the GDACS Search API.
    """
    model_config = ConfigDict(frozen=True)

    count: int = Field(default=0, description="Total number of GDACS alerts matching query criteria")
    events: List[GDACSEvent] = Field(default_factory=list, description="List of normalized GDACS disaster alert events")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters used for the query")
    api_url: Optional[str] = Field(default=None, description="GDACS query URL executed")
    disclaimer: str = Field(
        default="Disaster alert data retrieved from the Global Disaster Alert and Coordination System (GDACS).",
        description="Data provenance notice"
    )

    @classmethod
    def from_geojson(
        cls,
        payload: dict,
        query_params: Optional[dict] = None,
        api_url: Optional[str] = None,
    ) -> "GDACSQueryResponse":
        """
        Parses a GDACS GeoJSON FeatureCollection dictionary into a GDACSQueryResponse.
        """
        features = payload.get("features", []) or []
        events: List[GDACSEvent] = []
        for feat in features:
            if isinstance(feat, dict):
                try:
                    events.append(GDACSEvent.from_geojson_feature(feat))
                except Exception:
                    continue

        return cls(
            count=len(events),
            events=events,
            query_params=query_params or {},
            api_url=api_url,
        )


class IncidentCoordinates(BaseModel):
    """
    Standardized geographic coordinates for the incident.
    Represents a point estimate (epicenter or centroid); does NOT define the spatial
    perimeter, inundation footprint, or full disaster boundary.
    """
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(..., description="Latitude (-90 to 90)")
    longitude: float = Field(..., description="Longitude (-180 to 180)")
    source: str = Field(..., description="Authoritative source providing coordinates")
    coordinate_type: str = Field(default="epicenter_or_centroid", description="Type of coordinate: 'epicenter', 'centroid', etc.")
    coordinate_label: str = Field(default="Incident Coordinate", description="Accurate semantic label (e.g. 'GDACS Event Centroid', 'USGS Earthquake Epicenter')")
    depth_km: Optional[float] = Field(default=None, description="Focal depth in kilometers for seismic events")
    disclaimer: str = Field(
        default="Point estimate only; does not define spatial perimeter, flood inundation boundary, or disaster footprint.",
        description="Spatial footprint caveat"
    )


class UnifiedUSGSData(BaseModel):
    """
    Seismic catalog data retrieved from the official USGS Earthquake Catalog API.
    """
    model_config = ConfigDict(frozen=True)

    queried: bool = Field(default=False, description="Whether USGS was selected and queried for this disaster type")
    status: str = Field(default="not_queried", description="Query execution status: 'success', 'no_matching_events', 'failed', 'not_applicable'")
    matched_events: List[EarthquakeEvent] = Field(default_factory=list, description="Seismic events matching both the incident location and date window")
    unmatched_events_count: int = Field(default=0, description="Events retrieved within the time window that did not match the incident location")
    unmatched_diagnostics: List[str] = Field(default_factory=list, description="Explicit diagnostics describing why unmatched events were excluded")
    total_catalog_events: int = Field(default=0, description="Total events returned by USGS catalog query")
    error_message: Optional[str] = Field(default=None, description="Error message if USGS query failed")
    source_url: Optional[str] = Field(default=None, description="USGS API query URL executed")


class UnifiedGDACSData(BaseModel):
    """
    Multi-hazard disaster alert data retrieved from the official GDACS API.
    """
    model_config = ConfigDict(frozen=True)

    queried: bool = Field(default=False, description="Whether GDACS was selected and queried for this disaster type")
    status: str = Field(default="not_queried", description="Query execution status: 'success', 'no_matching_events', 'failed', 'not_applicable'")
    matched_events: List[GDACSEvent] = Field(default_factory=list, description="Disaster alerts matching both the incident location and date window")
    unmatched_events_count: int = Field(default=0, description="Alerts retrieved within the time window that did not match the incident location")
    unmatched_diagnostics: List[str] = Field(default_factory=list, description="Explicit diagnostics describing why unmatched alerts were excluded")
    total_alerts_found: int = Field(default=0, description="Total alerts returned by GDACS search query")
    error_message: Optional[str] = Field(default=None, description="Error message if GDACS query failed")
    source_url: Optional[str] = Field(default=None, description="GDACS API query URL executed")


class UnifiedTavilyData(BaseModel):
    """
    Open web disaster intelligence and news reporting retrieved from Tavily Search.
    """
    model_config = ConfigDict(frozen=True)

    queried: bool = Field(default=False, description="Whether Tavily web search was queried")
    status: str = Field(default="not_queried", description="Query execution status: 'success', 'empty_results', 'failed', 'skipped'")
    article_count: int = Field(default=0, description="Number of retrieved web articles")
    articles: List[SearchResult] = Field(default_factory=list, description="Curated and evaluated web articles")
    synthesized_summary: Optional[str] = Field(default=None, description="Synthesized multi-source incident overview")
    verified_claims: List[ClaimEvidence] = Field(default_factory=list, description="Structured factual claim evidence")
    corroborated_facts: List[str] = Field(default_factory=list, description="Claims corroborated across independent sources")
    conflicting_claims: List[str] = Field(default_factory=list, description="Conflicting or divergent claims (e.g. differing casualty figures)")
    single_source_claims: List[str] = Field(default_factory=list, description="Claims attested by only a single source")
    error_message: Optional[str] = Field(default=None, description="Error message if Tavily query failed")


class ReliefWebReport(BaseModel):
    """
    Normalized humanitarian situation report, assessment, or evaluation from ReliefWeb (UN OCHA).
    Maintains explicit distinction between report publication date and disaster incident date.
    All casualty and displacement figures represent organizational field estimates, not census ground truth.
    """
    model_config = ConfigDict(frozen=True)

    report_id: str = Field(..., description="Unique ReliefWeb report identifier")
    title: str = Field(..., description="Title of the humanitarian situation report or assessment")
    url: str = Field(..., description="Canonical ReliefWeb URL of the report")

    # Dates: Strictly separated publication date from disaster event date
    publication_date: Optional[str] = Field(
        default=None,
        description="Publication date of the report (date.created or date.original). NOT the disaster occurrence date.",
    )
    publication_date_dt: Optional[datetime] = Field(default=None, description="Parsed publication timestamp")
    disaster_occurrence_date: Optional[str] = Field(
        default=None,
        description="Disaster incident date or period if identified in disaster taxonomy (e.g. 'Aug 2018').",
    )
    temporal_relation: str = Field(
        default="unknown",
        description="Temporal category: 'contemporaneous', 'retrospective', or 'unknown' relative to incident.",
    )

    # Source & Format
    sources: List[str] = Field(
        default_factory=list,
        description="Authoring or publishing organizations (e.g. 'Government of India', 'UNICEF', 'IFRC').",
    )
    format: Optional[str] = Field(
        default=None,
        description="Content format taxonomy (e.g. 'Situation Report', 'Assessment', 'News and Press Release').",
    )
    themes: List[str] = Field(default_factory=list, description="Humanitarian themes (e.g. 'Disaster Management', 'Health')")
    countries: List[str] = Field(default_factory=list, description="Associated countries from taxonomy")
    primary_country: Optional[str] = Field(default=None, description="Primary focus country")
    disaster_names: List[str] = Field(default_factory=list, description="Disaster names tagged to the report")
    glide_numbers: List[str] = Field(default_factory=list, description="GLIDE emergency numbers (e.g. 'FL-2018-000130-IND')")

    body_snippet: Optional[str] = Field(default=None, description="Summary or excerpt from report body")
    headline: Optional[str] = Field(default=None, description="Executive headline if present")

    # Data boundaries & disclaimers
    is_verified_ground_truth: bool = Field(
        default=False,
        description="Humanitarian situation reports are operational field estimates, NOT census ground truth.",
    )
    disclaimer: str = Field(
        default="ReliefWeb situation reports provide organizational humanitarian assessments and operational estimates. Casualty and displacement figures represent agency-reported emergency estimates, NOT independently verified census data or ground truth.",
        description="Operational estimate disclaimer",
    )

    @classmethod
    def from_api_item(cls, item: dict) -> "ReliefWebReport":
        """
        Parses a single report item from the ReliefWeb v2 API response data array.
        """
        report_id = str(item.get("id") or item.get("fields", {}).get("id") or "")
        fields = item.get("fields", {}) or {}

        title = str(fields.get("title") or "").strip()
        url = str(fields.get("url") or f"https://reliefweb.int/node/{report_id}").strip()

        # Dates
        raw_date = fields.get("date") or {}
        pub_str = None
        pub_dt = None
        if isinstance(raw_date, dict):
            pub_raw = raw_date.get("original") or raw_date.get("created")
            if pub_raw:
                pub_str = str(pub_raw).strip()
                try:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except Exception:
                    pub_dt = None

        # Sources
        sources_list = []
        for s in fields.get("source", []) or []:
            if isinstance(s, dict):
                name = s.get("name") or s.get("shortname")
                if name:
                    sources_list.append(str(name).strip())
            elif isinstance(s, str):
                sources_list.append(s.strip())

        # Format
        fmt = None
        raw_fmt = fields.get("format")
        if isinstance(raw_fmt, list) and raw_fmt:
            first_fmt = raw_fmt[0]
            if isinstance(first_fmt, dict):
                fmt = first_fmt.get("name")
            elif isinstance(first_fmt, str):
                fmt = first_fmt
        elif isinstance(raw_fmt, dict):
            fmt = raw_fmt.get("name")

        # Themes
        themes = []
        for t in fields.get("theme", []) or []:
            if isinstance(t, dict) and t.get("name"):
                themes.append(str(t["name"]).strip())
            elif isinstance(t, str):
                themes.append(t.strip())

        # Countries
        countries = []
        for c in fields.get("country", []) or []:
            if isinstance(c, dict) and c.get("name"):
                countries.append(str(c["name"]).strip())
            elif isinstance(c, str):
                countries.append(c.strip())

        prim_country = None
        raw_pc = fields.get("primary_country")
        if isinstance(raw_pc, dict):
            prim_country = raw_pc.get("name")
        elif isinstance(raw_pc, str):
            prim_country = raw_pc

        # Disasters & GLIDEs
        disasters = []
        glides = []
        for d in fields.get("disaster", []) or []:
            if isinstance(d, dict):
                d_name = d.get("name")
                if d_name:
                    disasters.append(str(d_name).strip())
                g = d.get("glide")
                if g:
                    glides.append(str(g).strip())
            elif isinstance(d, str):
                disasters.append(d.strip())

        # Body snippet
        body_snippet = None
        raw_body = fields.get("body")
        if raw_body and isinstance(raw_body, str):
            clean_body = re.sub(r"\s+", " ", raw_body).strip()
            body_snippet = clean_body[:500] if len(clean_body) > 500 else clean_body

        headline = fields.get("headline", {}).get("title") if isinstance(fields.get("headline"), dict) else None

        return cls(
            report_id=report_id,
            title=title,
            url=url,
            publication_date=pub_str,
            publication_date_dt=pub_dt,
            sources=sources_list,
            format=fmt,
            themes=themes,
            countries=countries,
            primary_country=prim_country,
            disaster_names=disasters,
            glide_numbers=glides,
            body_snippet=body_snippet,
            headline=headline,
        )


class ReliefWebQueryResponse(BaseModel):
    """
    Aggregated response from querying the ReliefWeb Reports API.
    """
    model_config = ConfigDict(frozen=True)

    total_count: int = Field(default=0, description="Total reports matching query on ReliefWeb")
    count: int = Field(default=0, description="Number of reports returned in this response")
    reports: List[ReliefWebReport] = Field(default_factory=list, description="Parsed humanitarian reports")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters sent in the query")
    api_url: Optional[str] = Field(default=None, description="API URL called")
    disclaimer: str = Field(
        default="Humanitarian situation reports retrieved from ReliefWeb (UN OCHA). Operational estimates, not census ground truth.",
        description="Data provenance notice",
    )

    @classmethod
    def from_api_payload(
        cls,
        payload: dict,
        query_params: Optional[dict] = None,
        api_url: Optional[str] = None,
    ) -> "ReliefWebQueryResponse":
        total_count = int(payload.get("totalCount") or payload.get("count") or 0)
        data = payload.get("data", []) or []
        reports: List[ReliefWebReport] = []
        for item in data:
            if isinstance(item, dict):
                try:
                    reports.append(ReliefWebReport.from_api_item(item))
                except Exception:
                    continue
        return cls(
            total_count=total_count,
            count=len(reports),
            reports=reports,
            query_params=query_params or {},
            api_url=api_url,
        )


class UnifiedReliefWebData(BaseModel):
    """
    Humanitarian situation reports and impact assessments retrieved from ReliefWeb (UN OCHA).
    """
    model_config = ConfigDict(frozen=True)

    queried: bool = Field(default=False, description="Whether ReliefWeb was queried for this incident")
    status: str = Field(default="not_queried", description="Query execution status: 'success', 'no_matching_reports', 'empty_results', 'failed', 'not_applicable'")
    matched_reports: List[ReliefWebReport] = Field(default_factory=list, description="Humanitarian reports matching incident location and date")
    unmatched_reports_count: int = Field(default=0, description="Reports retrieved that did not match the incident location")
    unmatched_diagnostics: List[str] = Field(default_factory=list, description="Diagnostics explaining why unmatched reports were excluded")
    total_reports_found: int = Field(default=0, description="Total reports returned by ReliefWeb API")
    error_message: Optional[str] = Field(default=None, description="Error message if ReliefWeb query failed")
    source_url: Optional[str] = Field(default=None, description="ReliefWeb API query URL executed")
    disclaimer: str = Field(
        default="ReliefWeb situation reports provide organizational humanitarian assessments and operational estimates. Casualty and displacement figures represent agency-reported emergency estimates, NOT independently verified census data or ground truth.",
        description="Operational estimate disclaimer",
    )


class ActiveFireDetection(BaseModel):
    """
    Represents an individual active fire / thermal anomaly detection retrieved from NASA FIRMS.
    Detections originate from satellite sensors (MODIS on Terra/Aqua or VIIRS on Suomi NPP / NOAA-20 / NOAA-21).
    Thermal anomalies indicate high-temperature pixels and are NOT definitive ground proof of an active wildfire without context.
    """
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Center latitude of the fire pixel (WGS84)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Center longitude of the fire pixel (WGS84)")
    acq_date: str = Field(..., description="Acquisition date (YYYY-MM-DD)")
    acq_time: Optional[str] = Field(default=None, description="Acquisition time in UTC (hhmm or hh:mm)")
    satellite: Optional[str] = Field(default=None, description="Satellite identifier (e.g. 'Suomi NPP', 'NOAA-20', 'Terra', 'Aqua')")
    instrument: Optional[str] = Field(default=None, description="Sensor instrument (e.g. 'VIIRS', 'MODIS')")
    confidence: Optional[str] = Field(default=None, description="Detection quality/confidence: 'low', 'nominal', 'high' (VIIRS) or percentage (MODIS)")
    brightness: Optional[float] = Field(default=None, description="Brightness temperature (Kelvin) from primary channel (bright_ti4 for VIIRS or channel 21/22 for MODIS)")
    bright_t31: Optional[float] = Field(default=None, description="Thermal IR brightness temperature (Kelvin) from secondary channel (bright_ti5 for VIIRS or channel 31 for MODIS)")
    frp: Optional[float] = Field(default=None, description="Fire Radiative Power (MW)")
    daynight: Optional[str] = Field(default=None, description="'D' for Day, 'N' for Night observation")
    is_verified_wildfire: bool = Field(
        default=False,
        description="Thermal anomalies indicate heat signatures, NOT confirmed ground wildfires without corroborating context.",
    )
    disclaimer: str = Field(
        default="Thermal anomaly detected by satellite radiometer. Fire detections indicate high temperature pixels, which can include wildfires, prescribed agricultural burns, industrial flaring, or false positives, and do not constitute independent ground proof of an active wildfire without context.",
        description="Thermal anomaly caveat",
    )

    @classmethod
    def from_csv_row(cls, row: Dict[str, Any]) -> "ActiveFireDetection":
        """
        Parses a single row dictionary from NASA FIRMS CSV output into an ActiveFireDetection.
        Supports both MODIS and VIIRS schema variants.
        """
        lat_raw = row.get("latitude")
        lon_raw = row.get("longitude")
        if lat_raw is None or lon_raw is None:
            raise ValueError("Row missing required latitude or longitude")
        lat = float(str(lat_raw).strip())
        lon = float(str(lon_raw).strip())

        acq_date = str(row.get("acq_date") or "").strip()
        raw_time = str(row.get("acq_time") or "").strip()
        acq_time = None
        if raw_time:
            clean_time = raw_time.replace(":", "")
            if len(clean_time) == 4 and clean_time.isdigit():
                acq_time = f"{clean_time[:2]}:{clean_time[2:]} UTC"
            elif clean_time.isdigit():
                acq_time = f"{clean_time.zfill(4)[:2]}:{clean_time.zfill(4)[2:]} UTC"
            else:
                acq_time = raw_time

        raw_sat = str(row.get("satellite") or "").strip()
        sat_map = {
            "N": "Suomi NPP",
            "NPP": "Suomi NPP",
            "1": "NOAA-20",
            "2": "NOAA-21",
            "T": "Terra",
            "A": "Aqua",
        }
        satellite = sat_map.get(raw_sat, raw_sat if raw_sat else None)

        raw_inst = str(row.get("instrument") or "").strip()
        instrument = raw_inst if raw_inst else ("VIIRS" if "bright_ti4" in row else "MODIS")

        raw_conf = str(row.get("confidence") or "").strip().lower()
        conf_map = {
            "l": "low",
            "n": "nominal",
            "h": "high",
        }
        confidence = conf_map.get(raw_conf, raw_conf if raw_conf else None)
        if confidence and confidence.isdigit():
            confidence = f"{confidence}%"

        brightness = None
        raw_bright = row.get("bright_ti4") or row.get("brightness")
        if raw_bright is not None:
            try:
                brightness = float(str(raw_bright).strip())
            except (ValueError, TypeError):
                brightness = None

        bright_t31 = None
        raw_b31 = row.get("bright_ti5") or row.get("bright_t31")
        if raw_b31 is not None:
            try:
                bright_t31 = float(str(raw_b31).strip())
            except (ValueError, TypeError):
                bright_t31 = None

        frp = None
        raw_frp = row.get("frp")
        if raw_frp is not None:
            try:
                frp = float(str(raw_frp).strip())
            except (ValueError, TypeError):
                frp = None

        raw_dn = str(row.get("daynight") or "").strip().upper()
        daynight = raw_dn if raw_dn in {"D", "N"} else None

        return cls(
            latitude=lat,
            longitude=lon,
            acq_date=acq_date,
            acq_time=acq_time,
            satellite=satellite,
            instrument=instrument,
            confidence=confidence,
            brightness=brightness,
            bright_t31=bright_t31,
            frp=frp,
            daynight=daynight,
        )


class FIRMSQueryResponse(BaseModel):
    """
    Aggregated response from querying the NASA FIRMS Active Fire API.
    """
    model_config = ConfigDict(frozen=True)

    total_count: int = Field(default=0, description="Total active fire detections returned")
    count: int = Field(default=0, description="Number of parsed fire detections")
    detections: List[ActiveFireDetection] = Field(default_factory=list, description="Parsed active fire detections")
    source_name: str = Field(default="VIIRS_SNPP_NRT", description="FIRMS sensor feed name queried")
    area_or_country: str = Field(default="", description="Geographic area or country queried")
    api_url: Optional[str] = Field(default=None, description="API URL called (with MAP_KEY masked)")
    disclaimer: str = Field(
        default="NASA FIRMS active fire data represents thermal anomalies detected by satellite sensors (MODIS/VIIRS). Satellite thermal detections indicate heat signatures (including biomass burning, agricultural clearing, industrial flares, or hot surfaces) and must not be conflated with confirmed wildfire boundaries or ground truth without corroborating incident context.",
        description="Data provenance notice",
    )


class UnifiedFIRMSData(BaseModel):
    """
    NASA FIRMS active fire satellite detections integrated into the unified incident intelligence report.
    Enforces strict distinction between raw satellite thermal anomalies and confirmed wildfire ground truth.
    """
    model_config = ConfigDict(frozen=True)

    queried: bool = Field(default=False, description="Whether NASA FIRMS was queried for this incident")
    status: str = Field(default="not_queried", description="Query execution status: 'success', 'no_detections', 'unconfigured', 'failed', 'not_applicable'")
    matched_detections: List[ActiveFireDetection] = Field(default_factory=list, description="Active fire detections matching incident region and time window")
    unmatched_detections_count: int = 0
    unmatched_diagnostics: List[str] = Field(default_factory=list, description="Diagnostics explaining why detections were excluded")
    total_detections_found: int = 0
    error_message: Optional[str] = Field(default=None, description="Error message if FIRMS query failed or key unconfigured")
    source_url: Optional[str] = Field(default=None, description="NASA FIRMS API query URL executed (with key masked)")
    satellite_source: Optional[str] = Field(default=None, description="Sensor feed queried (e.g. VIIRS_SNPP_NRT, MODIS_NRT)")
    disclaimer: str = Field(
        default="NASA FIRMS active fire data represents thermal anomalies detected by satellite sensors (MODIS/VIIRS). Satellite thermal detections indicate heat signatures (including biomass burning, agricultural clearing, industrial flares, or hot surfaces) and must not be conflated with confirmed wildfire boundaries or ground truth without corroborating incident context.",
        description="Thermal anomaly distinction disclaimer",
    )


class UnifiedIncidentReport(BaseModel):
    """
    Unified incident intelligence report aggregating Tavily, USGS, GDACS, ReliefWeb, and NASA FIRMS.
    Maintains rigorous provenance, source attribution, and explicit data boundaries.
    """
    model_config = ConfigDict(frozen=True)

    original_query: str = Field(..., description="User disaster incident query")
    disaster_type: Optional[str] = Field(default=None, description="Normalized hazard category (e.g. 'earthquake', 'floods')")
    location: Optional[str] = Field(default=None, description="Identified incident location or jurisdiction")
    incident_date_str: Optional[str] = Field(default=None, description="Normalized human-readable event date")
    query_window_start: Optional[str] = Field(default=None, description="ISO start date used for catalog and alert queries")
    query_window_end: Optional[str] = Field(default=None, description="ISO end date used for catalog and alert queries")
    primary_coordinates: Optional[IncidentCoordinates] = Field(default=None, description="Best available verified coordinates from authoritative sensor or alert feeds")

    # Source execution tracking
    sources_queried: List[str] = Field(default_factory=list, description="List of source services queried for this incident")
    sources_succeeded: List[str] = Field(default_factory=list, description="List of source services that succeeded")
    sources_failed: Dict[str, str] = Field(default_factory=dict, description="Failed source services mapped to their error message")

    # Source-specific normalized payloads
    usgs: UnifiedUSGSData = Field(default_factory=UnifiedUSGSData, description="USGS Earthquake Catalog results")
    gdacs: UnifiedGDACSData = Field(default_factory=UnifiedGDACSData, description="GDACS disaster alert results")
    reliefweb: UnifiedReliefWebData = Field(default_factory=UnifiedReliefWebData, description="ReliefWeb humanitarian situation reports and assessments")
    firms: UnifiedFIRMSData = Field(default_factory=UnifiedFIRMSData, description="NASA FIRMS active fire satellite detections")
    tavily: UnifiedTavilyData = Field(default_factory=UnifiedTavilyData, description="Tavily web intelligence and verification results")

    # Provenance and boundary tracking
    source_attributions: Dict[str, str] = Field(default_factory=dict, description="Explicit attribution mapping for key facts")
    data_limitations: List[str] = Field(default_factory=list, description="Explicit limitations and caveats for this incident")
    unavailable_fields: List[str] = Field(default_factory=list, description="Fields explicitly recognized as unavailable from queried feeds")

    # Spatial AOI and Satellite Integration
    bbox: Optional[List[float]] = Field(default=None, description="AOI bounding box [west, south, east, north]")
    is_benchmark: bool = Field(default=False, description="Whether this incident has pre-verified satellite benchmark runs available")
    benchmark_run_id: Optional[str] = Field(default=None, description="Pre-computed run identifier if available (e.g. 'kerala_2018-08-10', 'lucknow_2026-10-01')")




