"""
Official GDACS (Global Disaster Alert and Coordination System) API integration.
Retrieves and normalizes multi-hazard disaster alerts and event intelligence via GeoJSON feeds.
Covers earthquakes (EQ), tropical cyclones (TC), floods (FL), volcanoes (VO), droughts (DR), and wildfires (WF).
A joint initiative of the United Nations (UN OCHA) and the European Commission (DG ECHO / JRC).
Requires no API key (public domain service).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import logging
import math
import socket
import sys
from typing import Any, Dict, List, Optional, Set, Union
import urllib.error
import urllib.parse
import urllib.request

from src.config import GDACSConfig, get_gdacs_config
from src.models import GDACSEvent, GDACSQueryResponse, GeoBounds

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------
class GDACSClientError(Exception):
    """Base exception for all GDACS client errors."""
    pass


class GDACSInvalidParameterError(GDACSClientError):
    """Raised when query parameters (dates, event types, alert levels, page sizes) are invalid."""
    pass


class GDACSTimeoutError(GDACSClientError):
    """Raised when an API request to the GDACS service times out."""
    pass


class GDACSHTTPError(GDACSClientError):
    """Raised when the GDACS API responds with an HTTP 4xx or 5xx status code."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GDACSParsingError(GDACSClientError):
    """Raised when GDACS response data is malformed or cannot be parsed as valid GeoJSON."""
    pass


class GDACSNetworkError(GDACSClientError):
    """Raised on socket/DNS connection failures when contacting GDACS."""
    pass


# ------------------------------------------------------------------------------
# GDACS Client Implementation
# ------------------------------------------------------------------------------
class GDACSClient:
    """
    Client for interacting with the public GDACS REST and GeoJSON API.
    Provides methods to search multi-hazard alerts by event type, date range,
    alert level, country, and spatial bounds.
    """

    # Official two-letter hazard codes recognized by GDACS API
    SUPPORTED_EVENT_TYPES: Set[str] = {"EQ", "TC", "FL", "VO", "DR", "WF"}

    # Human-friendly aliases mapped to official codes
    EVENT_TYPE_ALIASES: Dict[str, str] = {
        "earthquake": "EQ",
        "earthquakes": "EQ",
        "seismic": "EQ",
        "tropical cyclone": "TC",
        "cyclone": "TC",
        "cyclones": "TC",
        "hurricane": "TC",
        "hurricanes": "TC",
        "typhoon": "TC",
        "typhoons": "TC",
        "flood": "FL",
        "floods": "FL",
        "flooding": "FL",
        "inundation": "FL",
        "volcano": "VO",
        "volcanoes": "VO",
        "volcanic": "VO",
        "eruption": "VO",
        "drought": "DR",
        "droughts": "DR",
        "wildfire": "WF",
        "wildfires": "WF",
        "forest fire": "WF",
        "bushfire": "WF",
    }

    # Supported GDACS alert severity levels
    SUPPORTED_ALERT_LEVELS: Set[str] = {"green", "orange", "red"}

    def __init__(
        self,
        config: Optional[GDACSConfig] = None,
        timeout: Optional[int] = None,
    ):
        self.config = config or get_gdacs_config()
        self.timeout = timeout if timeout is not None else self.config.timeout

    def query_events(
        self,
        event_types: Optional[Union[str, List[str]]] = None,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
        alert_levels: Optional[Union[str, List[str]]] = None,
        country: Optional[str] = None,
        min_severity: Optional[float] = None,
        page_number: int = 1,
        page_size: int = 100,
        bounds: Optional[GeoBounds] = None,
        min_latitude: Optional[float] = None,
        max_latitude: Optional[float] = None,
        min_longitude: Optional[float] = None,
        max_longitude: Optional[float] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        max_radius_km: Optional[float] = None,
    ) -> GDACSQueryResponse:
        """
        Queries multi-hazard disaster alerts matching specified criteria from GDACS.

        Args:
            event_types: Hazard code(s) or name(s) (e.g. 'FL', 'floods', ['EQ', 'TC']).
            from_date: Start of observation time window (ISO string, date, or datetime).
            to_date: End of observation time window (ISO string, date, or datetime).
            alert_levels: Alert severity level(s): 'green', 'orange', 'red' (single or list).
            country: Country name or ISO code to filter (e.g. 'India', 'TUR').
            min_severity: Minimum physical severity metric threshold.
            page_number: Result page number (1-indexed, default 1).
            page_size: Records per page (1 to 100, default 100).
            bounds: GeoBounds instance for client-side spatial bounding box filtering.
            min_latitude: Minimum latitude (-90 to 90). Overrides bounds if set.
            max_latitude: Maximum latitude (-90 to 90). Overrides bounds if set.
            min_longitude: Minimum longitude (-180 to 180). Overrides bounds if set.
            max_longitude: Maximum longitude (-180 to 180). Overrides bounds if set.
            latitude: Latitude for radial search filter (-90 to 90).
            longitude: Longitude for radial search filter (-180 to 180).
            max_radius_km: Maximum radius in kilometers for radial filter.

        Returns:
            GDACSQueryResponse containing normalized GDACSEvent objects.

        Raises:
            GDACSInvalidParameterError: If any parameter value or range is invalid.
            GDACSTimeoutError: If the request times out.
            GDACSHTTPError: If the server returns an HTTP error code.
            GDACSParsingError: If the response cannot be parsed as valid GeoJSON.
            GDACSNetworkError: If a low-level network failure occurs.
        """
        # 1. Parameter Normalization & Validation
        params: Dict[str, Any] = {}

        # Hazard Event Types
        if event_types is not None:
            normalized_types = self._normalize_event_types(event_types)
            if normalized_types:
                params["eventlist"] = ";".join(normalized_types)

        # Alert Levels
        if alert_levels is not None:
            normalized_levels = self._normalize_alert_levels(alert_levels)
            if normalized_levels:
                params["alertlevel"] = ";".join(normalized_levels)

        # Dates
        from_str = self._format_date(from_date) if from_date is not None else None
        to_str = self._format_date(to_date) if to_date is not None else None

        if from_str and to_str and from_str > to_str:
            raise GDACSInvalidParameterError(
                f"Invalid date range: from_date ({from_str}) cannot be after to_date ({to_str})."
            )

        if from_str:
            params["fromDate"] = from_str
        if to_str:
            params["toDate"] = to_str

        # Country
        if country is not None:
            cleaned_country = country.strip()
            if not cleaned_country:
                raise GDACSInvalidParameterError("country parameter cannot be blank if provided.")
            params["country"] = cleaned_country

        # Severity
        if min_severity is not None:
            try:
                params["severity"] = float(min_severity)
            except (ValueError, TypeError) as err:
                raise GDACSInvalidParameterError(f"min_severity must be numeric: {min_severity}") from err

        # Pagination
        if not isinstance(page_number, int) or page_number < 1:
            raise GDACSInvalidParameterError(f"page_number must be a positive integer >= 1: {page_number}")
        params["pageNumber"] = page_number

        if not isinstance(page_size, int) or page_size < 1:
            raise GDACSInvalidParameterError(f"page_size must be a positive integer: {page_size}")
        if page_size > 100:
            raise GDACSInvalidParameterError(f"page_size cannot exceed 100 (GDACS API maximum): {page_size}")
        params["pageSize"] = page_size

        # Spatial Coordinates Validation (for client-side filtering)
        eff_min_lat = min_latitude if min_latitude is not None else (bounds.min_latitude if bounds else None)
        eff_max_lat = max_latitude if max_latitude is not None else (bounds.max_latitude if bounds else None)
        eff_min_lon = min_longitude if min_longitude is not None else (bounds.min_longitude if bounds else None)
        eff_max_lon = max_longitude if max_longitude is not None else (bounds.max_longitude if bounds else None)

        has_bbox_filter = any(v is not None for v in [eff_min_lat, eff_max_lat, eff_min_lon, eff_max_lon])
        if has_bbox_filter:
            self._validate_coordinate_bounds(eff_min_lat, eff_max_lat, eff_min_lon, eff_max_lon)

        has_radial_filter = (latitude is not None or longitude is not None or max_radius_km is not None)
        if has_radial_filter:
            if latitude is None or longitude is None or max_radius_km is None:
                raise GDACSInvalidParameterError("Radial search requires latitude, longitude, and max_radius_km.")
            if not (-90.0 <= float(latitude) <= 90.0):
                raise GDACSInvalidParameterError(f"Latitude out of bounds [-90, 90]: {latitude}")
            if not (-180.0 <= float(longitude) <= 180.0):
                raise GDACSInvalidParameterError(f"Longitude out of bounds [-180, 180]: {longitude}")
            if float(max_radius_km) <= 0:
                raise GDACSInvalidParameterError(f"max_radius_km must be positive: {max_radius_km}")

        # 2. Build URL and Execute Request
        query_url = self._build_url(self.config.base_url, params)
        logger.info("Querying GDACS Search API: %s", query_url)

        raw_payload = self._execute_request(query_url)
        response = GDACSQueryResponse.from_geojson(raw_payload, query_params=params, api_url=query_url)

        # 3. Apply Client-Side Spatial Filtering if Requested
        if has_bbox_filter or has_radial_filter:
            filtered_events: List[GDACSEvent] = []
            for ev in response.events:
                if ev.latitude is None or ev.longitude is None:
                    continue

                # Bounding Box Filter
                if has_bbox_filter:
                    if eff_min_lat is not None and ev.latitude < eff_min_lat:
                        continue
                    if eff_max_lat is not None and ev.latitude > eff_max_lat:
                        continue
                    if eff_min_lon is not None and ev.longitude < eff_min_lon:
                        continue
                    if eff_max_lon is not None and ev.longitude > eff_max_lon:
                        continue

                # Radial Filter
                if has_radial_filter:
                    dist_km = self._haversine_distance_km(float(latitude), float(longitude), ev.latitude, ev.longitude)
                    if dist_km > float(max_radius_km):
                        continue

                filtered_events.append(ev)

            return GDACSQueryResponse(
                count=len(filtered_events),
                events=filtered_events,
                query_params=params,
                api_url=query_url,
                disclaimer=response.disclaimer,
            )

        return response

    def get_event_by_id(
        self,
        event_id: Union[str, int],
        event_type: Optional[str] = None,
    ) -> Optional[GDACSEvent]:
        """
        Fetches detailed record for a specific disaster event using its type and ID.
        Note: In GDACS, event IDs are scoped per hazard type (e.g. eventid=1000212
        represents a Flood when eventtype='FL' but an Earthquake when eventtype='EQ').

        Args:
            event_id: Unique event ID (e.g. 1000212, or composite string 'FL-1000212').
            event_type: Two-letter hazard code (e.g. 'FL', 'EQ', 'TC') or alias.
                        Required if event_id does not contain a prefix.

        Returns:
            GDACSEvent if found, None if not found (404).

        Raises:
            GDACSInvalidParameterError: If event_id or event_type cannot be resolved.
            GDACSHTTPError: If server returns an HTTP error other than 404.
        """
        raw_id_str = str(event_id).strip()
        if not raw_id_str:
            raise GDACSInvalidParameterError("event_id cannot be empty.")

        resolved_type = event_type
        resolved_id = raw_id_str

        # Handle composite identifier like "FL-1000212" or "FL:1000212"
        for sep in ["-", ":", "_"]:
            if sep in raw_id_str:
                parts = raw_id_str.split(sep, 1)
                prefix_candidate = parts[0].strip().upper()
                if prefix_candidate in self.SUPPORTED_EVENT_TYPES or prefix_candidate.lower() in self.EVENT_TYPE_ALIASES:
                    resolved_type = prefix_candidate
                    resolved_id = parts[1].strip()
                    break

        if not resolved_type:
            raise GDACSInvalidParameterError(
                f"GDACS requires event_type ('FL', 'EQ', 'TC', 'VO', 'DR', 'WF') because event IDs "
                f"are scoped per hazard type. Provide event_type='FL' or pass event_id as 'TYPE-ID' (e.g. 'FL-{raw_id_str}')."
            )

        # Normalize resolved type
        normalized_types = self._normalize_event_types(resolved_type)
        if not normalized_types:
            raise GDACSInvalidParameterError(f"Unsupported event_type: {resolved_type}")
        type_code = normalized_types[0]

        try:
            numeric_id = int(resolved_id)
        except ValueError as err:
            raise GDACSInvalidParameterError(f"GDACS event ID must be numeric: {resolved_id}") from err

        params = {"eventtype": type_code, "eventid": numeric_id}
        query_url = self._build_url(self.config.event_data_url, params)
        logger.info("Fetching GDACS event data by ID: %s", query_url)

        try:
            raw_payload = self._execute_request(query_url)
            if raw_payload.get("type") == "Feature":
                return GDACSEvent.from_geojson_feature(raw_payload)
            features = raw_payload.get("features", [])
            if features and isinstance(features[0], dict):
                return GDACSEvent.from_geojson_feature(features[0])
            return None
        except GDACSHTTPError as err:
            if err.status_code in {404, 400}:
                logger.info("GDACS event '%s-%s' not found.", type_code, numeric_id)
                return None
            raise

    # --------------------------------------------------------------------------
    # Internal Request & Validation Helpers
    # --------------------------------------------------------------------------
    def _execute_request(self, url: str) -> dict:
        """
        Executes an HTTP GET request to the GDACS service and parses JSON.
        Handles empty responses (HTTP 204 or b''), timeouts, connection failures,
        HTTP errors, and malformed JSON.
        """
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json, application/geo+json",
        }
        req = urllib.request.Request(url, headers=headers)

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

            err_msg = f"GDACS API HTTP {status_code}: {http_err.reason}."
            if error_body:
                err_msg += f" Details: {error_body.strip()[:200]}"

            if status_code == 400:
                raise GDACSInvalidParameterError(err_msg) from http_err
            raise GDACSHTTPError(err_msg, status_code=status_code) from http_err

        except (socket.timeout, TimeoutError) as timeout_err:
            raise GDACSTimeoutError(
                f"GDACS API request timed out after {self.timeout}s."
            ) from timeout_err

        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, (socket.timeout, TimeoutError)):
                raise GDACSTimeoutError(
                    f"GDACS API request timed out after {self.timeout}s."
                ) from url_err
            raise GDACSNetworkError(
                f"Failed to connect to GDACS API: {url_err.reason}"
            ) from url_err

        except Exception as general_err:
            raise GDACSClientError(f"Unexpected error communicating with GDACS: {general_err}") from general_err

        # GDACS Quirk: Returns HTTP 204 or empty bytes b'' when no events match query
        if status_code == 204 or not raw_bytes.strip():
            return {"type": "FeatureCollection", "features": [], "bbox": []}

        try:
            text = raw_bytes.decode("utf-8")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise GDACSParsingError(f"Expected GeoJSON dictionary from GDACS, received {type(payload).__name__}")
            return payload
        except (json.JSONDecodeError, UnicodeDecodeError) as parse_err:
            raise GDACSParsingError(f"Failed to parse GDACS response as valid JSON: {parse_err}") from parse_err

    @classmethod
    def _normalize_event_types(cls, val: Union[str, List[str]]) -> List[str]:
        """Normalizes hazard type string or list of strings into official 2-letter codes."""
        raw_items: List[str] = []
        if isinstance(val, str):
            # Support semicolon or comma-separated strings
            split_items = [s.strip() for s in val.replace(",", ";").split(";") if s.strip()]
            raw_items.extend(split_items)
        elif isinstance(val, (list, tuple, set)):
            for item in val:
                if isinstance(item, str) and item.strip():
                    raw_items.append(item.strip())
        else:
            raise GDACSInvalidParameterError(f"Unsupported event_types parameter type: {type(val).__name__}")

        if not raw_items:
            raise GDACSInvalidParameterError("event_types parameter cannot be empty.")

        normalized: List[str] = []
        for item in raw_items:
            code = item.upper()
            if code in cls.SUPPORTED_EVENT_TYPES:
                if code not in normalized:
                    normalized.append(code)
                continue
            # Try alias lookup
            lower = item.lower()
            if lower in cls.EVENT_TYPE_ALIASES:
                alias_code = cls.EVENT_TYPE_ALIASES[lower]
                if alias_code not in normalized:
                    normalized.append(alias_code)
                continue
            raise GDACSInvalidParameterError(
                f"Unsupported hazard event type '{item}'. Supported codes: {sorted(cls.SUPPORTED_EVENT_TYPES)} "
                f"or aliases: {sorted(set(cls.EVENT_TYPE_ALIASES.keys()))}"
            )
        return normalized

    @classmethod
    def _normalize_alert_levels(cls, val: Union[str, List[str]]) -> List[str]:
        """Normalizes alert severity level(s) into lowercase: 'green', 'orange', 'red'."""
        raw_items: List[str] = []
        if isinstance(val, str):
            split_items = [s.strip() for s in val.replace(",", ";").split(";") if s.strip()]
            raw_items.extend(split_items)
        elif isinstance(val, (list, tuple, set)):
            for item in val:
                if isinstance(item, str) and item.strip():
                    raw_items.append(item.strip())
        else:
            raise GDACSInvalidParameterError(f"Unsupported alert_levels parameter type: {type(val).__name__}")

        if not raw_items:
            raise GDACSInvalidParameterError("alert_levels parameter cannot be empty.")

        normalized: List[str] = []
        for item in raw_items:
            level = item.lower()
            if level in cls.SUPPORTED_ALERT_LEVELS:
                if level not in normalized:
                    normalized.append(level)
            else:
                raise GDACSInvalidParameterError(
                    f"Unsupported alert level '{item}'. Allowed values: {sorted(cls.SUPPORTED_ALERT_LEVELS)}"
                )
        return normalized

    @staticmethod
    def _build_url(base_url: str, params: Dict[str, Any]) -> str:
        """Constructs full URL with URL-encoded query parameters."""
        query_string = urllib.parse.urlencode(params)
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}{query_string}"

    @staticmethod
    def _format_date(val: Union[str, date, datetime]) -> str:
        """Normalizes date, datetime, or date string into ISO-8601 string."""
        if isinstance(val, datetime):
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc).strftime("%Y-%m-%d")
        if isinstance(val, date):
            return val.isoformat()
        if isinstance(val, str):
            cleaned = val.strip()
            if not cleaned:
                raise GDACSInvalidParameterError("Date parameter string cannot be blank.")
            return cleaned
        raise GDACSInvalidParameterError(f"Unsupported date type: {type(val).__name__}")

    @staticmethod
    def _validate_coordinate_bounds(
        min_lat: Optional[float],
        max_lat: Optional[float],
        min_lon: Optional[float],
        max_lon: Optional[float],
    ) -> None:
        """Validates bounding box coordinates."""
        for label, val, lower, upper in [
            ("min_latitude", min_lat, -90.0, 90.0),
            ("max_latitude", max_lat, -90.0, 90.0),
            ("min_longitude", min_lon, -180.0, 180.0),
            ("max_longitude", max_lon, -180.0, 180.0),
        ]:
            if val is not None and not (lower <= float(val) <= upper):
                raise GDACSInvalidParameterError(f"{label} ({val}) is outside valid range [{lower}, {upper}].")

        if min_lat is not None and max_lat is not None and float(min_lat) > float(max_lat):
            raise GDACSInvalidParameterError(
                f"min_latitude ({min_lat}) cannot be greater than max_latitude ({max_lat})."
            )

        if min_lon is not None and max_lon is not None and float(min_lon) > float(max_lon):
            raise GDACSInvalidParameterError(
                f"min_longitude ({min_lon}) cannot be greater than max_longitude ({max_lon})."
            )

    @staticmethod
    def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculates great-circle distance between two points in kilometers."""
        earth_radius_km = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return earth_radius_km * c

    @staticmethod
    def format_events_for_display(response: GDACSQueryResponse) -> str:
        """
        Formats a GDACSQueryResponse into a human-readable terminal report,
        clearly distinguishing fields returned directly by GDACS from inferred
        fields and unavailable metrics.
        """
        lines = []
        divider = "=" * 80
        thin_divider = "-" * 80

        lines.append(divider)
        lines.append(" GLOBAL DISASTER ALERT AND COORDINATION SYSTEM (GDACS) REPORT")
        lines.append(divider)
        lines.append(f" Total Alerts Found   : {response.count}")
        if response.api_url:
            lines.append(f" Query API URL        : {response.api_url}")
        lines.append(f" Provenance Notice    : {response.disclaimer}")
        lines.append(divider)

        if not response.events:
            lines.append("  [!] No disaster alerts found matching the specified query parameters.")
            lines.append(divider)
            return "\n".join(lines)

        for idx, ev in enumerate(response.events, start=1):
            alert_upper = ev.alert_level.upper()
            badge = f"[{alert_upper} ALERT]"
            lines.append(f"\n[Event {idx}/{len(response.events)}] {badge} {ev.name}")
            lines.append(f" Event ID       : {ev.event_id} (Hazard Type: {ev.event_type} - {ev.event_type_name})")
            if ev.episode_id:
                lines.append(f" Episode ID     : {ev.episode_id}")
            
            glide_display = ev.glide if ev.glide else "Not Assigned"
            lines.append(f" GLIDE Number   : {glide_display}")

            score_str = f"{ev.alert_score:.1f}" if ev.alert_score is not None else "N/A"
            lines.append(f" Alert Severity : {ev.alert_level} (Overall Score: {score_str})")

            # Dates
            start_str = ev.from_date_str or "Unknown"
            end_str = ev.to_date_str or "Ongoing / Open"
            lines.append(f" Active Period  : {start_str} to {end_str}")

            # Location & Coordinates
            loc_parts = []
            if ev.country:
                loc_parts.append(ev.country)
            if ev.iso3:
                loc_parts.append(f"({ev.iso3})")
            loc_str = " ".join(loc_parts) if loc_parts else "Global / Unspecified"
            lines.append(f" Country/Region : {loc_str}")

            if ev.latitude is not None and ev.longitude is not None:
                lines.append(f" Centroid Coords: Lat: {ev.latitude:.4f}, Lon: {ev.longitude:.4f}")

            # Severity data returned by GDACS
            if ev.severity_text:
                lines.append(f" GDACS Severity : {ev.severity_text}")
            elif ev.severity is not None:
                unit_str = f" {ev.severity_unit}" if ev.severity_unit else ""
                lines.append(f" GDACS Severity : {ev.severity}{unit_str}")
            else:
                lines.append(" GDACS Severity : Physical severity metric not reported in search feed")

            # Field distinction notice
            lines.append(" Impact Notice  : Casualties and damage statistics are NOT present in GDACS search feeds.")

            # URLs
            if ev.report_url:
                lines.append(f" Situation Rept : {ev.report_url}")
            if ev.details_url:
                lines.append(f" Event Data URL : {ev.details_url}")

        lines.append(f"\n{thin_divider}")
        lines.append(" Note: GDACS alerts represent algorithmic severity models and UN/EC coordination reports.")
        lines.append(" Verification against ground-truth incident records is required before confirming event occurrence.")
        lines.append(divider)
        return "\n".join(lines)


# ------------------------------------------------------------------------------
# Standalone CLI Runner
# ------------------------------------------------------------------------------
def main() -> None:
    """Command-line runner for interactive GDACS disaster queries."""
    parser = argparse.ArgumentParser(
        description="Query the official GDACS multi-hazard disaster alert catalog.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--event-type",
        "-t",
        default="FL",
        help="Hazard type code ('EQ', 'TC', 'FL', 'VO', 'DR', 'WF') or alias (e.g. 'floods', 'earthquake').",
    )
    parser.add_argument(
        "--start-date",
        "-s",
        default="2018-08-01",
        help="Start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        "-e",
        default="2018-08-31",
        help="End date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--alert-level",
        "-a",
        default=None,
        help="Alert level filter: 'green', 'orange', 'red', or semicolon-separated 'orange;red'.",
    )
    parser.add_argument(
        "--country",
        "-c",
        default=None,
        help="Country name or ISO code filter (e.g. 'India', 'TUR').",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=10,
        help="Maximum number of alerts to display (1 to 100).",
    )
    parser.add_argument(
        "--event-id",
        "-i",
        default=None,
        help="Fetch a single event by ID (e.g. '1000212' or 'FL-1000212').",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response model.",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    client = GDACSClient()

    try:
        if args.event_id:
            ev = client.get_event_by_id(args.event_id, event_type=args.event_type)
            if not ev:
                print(f"[!] No GDACS event found with ID '{args.event_id}' and type '{args.event_type}'.", file=sys.stderr)
                return 1
            single_response = GDACSQueryResponse(count=1, events=[ev])
            if args.json:
                print(single_response.model_dump_json(indent=2))
            else:
                print(GDACSClient.format_events_for_display(single_response))
            return 0

        response = client.query_events(
            event_types=args.event_type,
            from_date=args.start_date,
            to_date=args.end_date,
            alert_levels=args.alert_level,
            country=args.country,
            page_size=min(args.limit, 100),
        )

        if args.json:
            print(response.model_dump_json(indent=2))
        else:
            print(GDACSClient.format_events_for_display(response))
        return 0

    except GDACSClientError as err:
        print(f"\n[GDACS Error] {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
