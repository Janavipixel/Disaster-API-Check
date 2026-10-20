"""
Official USGS Earthquake Catalog API integration for seismic hazard intelligence.
Retrieves and normalizes real-time and historical earthquake event data via GeoJSON.
Requires no API key (public domain service).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import logging
import socket
from typing import Any, Dict, List, Optional, Union
import urllib.error
import urllib.parse
import urllib.request

from src.config import USGSConfig, get_usgs_config
from src.models import EarthquakeEvent, EarthquakeQueryResponse, GeoBounds

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------
class USGSClientError(Exception):
    """Base exception for all USGS Earthquake client errors."""
    pass


class USGSInvalidParameterError(USGSClientError):
    """Raised when query parameters (dates, magnitudes, coordinates) are invalid."""
    pass


class USGSTimeoutError(USGSClientError):
    """Raised when an API request to the USGS service times out."""
    pass


class USGSHTTPError(USGSClientError):
    """Raised when the USGS API responds with an HTTP 4xx or 5xx status code."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class USGSParsingError(USGSClientError):
    """Raised when USGS response data is malformed or cannot be parsed as GeoJSON."""
    pass


class USGSNetworkError(USGSClientError):
    """Raised on socket/DNS connection failures when contacting USGS."""
    pass


# ------------------------------------------------------------------------------
# USGS Client Implementation
# ------------------------------------------------------------------------------
class USGSClient:
    """
    Client for interacting with the public USGS Earthquake Catalog API.
    Provides methods to query seismic events by date range, magnitude, and geographic bounds.
    """

    def __init__(
        self,
        config: Optional[USGSConfig] = None,
        timeout: Optional[int] = None,
    ):
        self.config = config or get_usgs_config()
        self.timeout = timeout if timeout is not None else self.config.timeout

    def query_earthquakes(
        self,
        start_time: Optional[Union[str, date, datetime]] = None,
        end_time: Optional[Union[str, date, datetime]] = None,
        min_magnitude: Optional[float] = None,
        max_magnitude: Optional[float] = None,
        bounds: Optional[GeoBounds] = None,
        min_latitude: Optional[float] = None,
        max_latitude: Optional[float] = None,
        min_longitude: Optional[float] = None,
        max_longitude: Optional[float] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        max_radius_km: Optional[float] = None,
        limit: int = 20,
        order_by: str = "time",
    ) -> EarthquakeQueryResponse:
        """
        Queries earthquakes matching the provided criteria from the USGS Earthquake API.

        Args:
            start_time: Beginning of event time window (ISO string, date, or datetime).
            end_time: End of event time window (ISO string, date, or datetime).
            min_magnitude: Minimum magnitude threshold (e.g. 4.5).
            max_magnitude: Maximum magnitude threshold (e.g. 9.5).
            bounds: GeoBounds instance specifying bounding box coordinates.
            min_latitude: Minimum latitude (-90 to 90). Overrides bounds if set.
            max_latitude: Maximum latitude (-90 to 90). Overrides bounds if set.
            min_longitude: Minimum longitude (-180 to 180). Overrides bounds if set.
            max_longitude: Maximum longitude (-180 to 180). Overrides bounds if set.
            latitude: Latitude for radial search (-90 to 90).
            longitude: Longitude for radial search (-180 to 180).
            max_radius_km: Maximum search radius in kilometers.
            limit: Maximum number of events to return (1 to 20,000, default 20).
            order_by: Sort order ('time', 'time-asc', 'magnitude', 'magnitude-asc').

        Returns:
            EarthquakeQueryResponse containing normalized EarthquakeEvent objects.

        Raises:
            USGSInvalidParameterError: If parameter values or ranges are invalid.
            USGSTimeoutError: If the request times out.
            USGSHTTPError: If the server returns an HTTP error code.
            USGSParsingError: If the response cannot be parsed as valid GeoJSON.
            USGSNetworkError: If a low-level network failure occurs.
        """
        # 1. Parameter Normalization & Validation
        params: Dict[str, Any] = {"format": "geojson"}

        # Dates
        start_str = self._format_date(start_time) if start_time is not None else None
        end_str = self._format_date(end_time) if end_time is not None else None

        if start_str and end_str and start_str > end_str:
            raise USGSInvalidParameterError(
                f"Invalid date range: start_time ({start_str}) cannot be after end_time ({end_str})."
            )

        if start_str:
            params["starttime"] = start_str
        if end_str:
            params["endtime"] = end_str

        # Magnitudes
        if min_magnitude is not None:
            try:
                min_mag_val = float(min_magnitude)
                params["minmagnitude"] = min_mag_val
            except (ValueError, TypeError) as err:
                raise USGSInvalidParameterError(f"min_magnitude must be numeric: {min_magnitude}") from err

        if max_magnitude is not None:
            try:
                max_mag_val = float(max_magnitude)
                params["maxmagnitude"] = max_mag_val
            except (ValueError, TypeError) as err:
                raise USGSInvalidParameterError(f"max_magnitude must be numeric: {max_magnitude}") from err

        if (
            "minmagnitude" in params
            and "maxmagnitude" in params
            and params["minmagnitude"] > params["maxmagnitude"]
        ):
            raise USGSInvalidParameterError(
                f"Invalid magnitude range: min_magnitude ({params['minmagnitude']}) "
                f"cannot exceed max_magnitude ({params['maxmagnitude']})."
            )

        # Spatial Bounding Box
        effective_min_lat = min_latitude if min_latitude is not None else (bounds.min_latitude if bounds else None)
        effective_max_lat = max_latitude if max_latitude is not None else (bounds.max_latitude if bounds else None)
        effective_min_lon = min_longitude if min_longitude is not None else (bounds.min_longitude if bounds else None)
        effective_max_lon = max_longitude if max_longitude is not None else (bounds.max_longitude if bounds else None)

        if any(v is not None for v in [effective_min_lat, effective_max_lat, effective_min_lon, effective_max_lon]):
            self._validate_coordinate_bounds(effective_min_lat, effective_max_lat, effective_min_lon, effective_max_lon)
            if effective_min_lat is not None:
                params["minlatitude"] = effective_min_lat
            if effective_max_lat is not None:
                params["maxlatitude"] = effective_max_lat
            if effective_min_lon is not None:
                params["minlongitude"] = effective_min_lon
            if effective_max_lon is not None:
                params["maxlongitude"] = effective_max_lon

        # Radial search
        if latitude is not None or longitude is not None or max_radius_km is not None:
            if latitude is None or longitude is None:
                raise USGSInvalidParameterError("Radial search requires both latitude and longitude.")
            if not (-90.0 <= float(latitude) <= 90.0):
                raise USGSInvalidParameterError(f"Latitude out of bounds [-90, 90]: {latitude}")
            if not (-180.0 <= float(longitude) <= 180.0):
                raise USGSInvalidParameterError(f"Longitude out of bounds [-180, 180]: {longitude}")
            params["latitude"] = float(latitude)
            params["longitude"] = float(longitude)
            if max_radius_km is not None:
                if float(max_radius_km) <= 0:
                    raise USGSInvalidParameterError(f"max_radius_km must be positive: {max_radius_km}")
                params["maxradiuskm"] = float(max_radius_km)

        # Pagination and Ordering
        if not isinstance(limit, int) or limit <= 0:
            raise USGSInvalidParameterError(f"limit must be a positive integer: {limit}")
        params["limit"] = min(limit, 20000)

        valid_orders = {"time", "time-asc", "magnitude", "magnitude-asc"}
        if order_by not in valid_orders:
            raise USGSInvalidParameterError(
                f"Invalid order_by value '{order_by}'. Allowed values: {sorted(valid_orders)}"
            )
        params["orderby"] = order_by

        # 2. Build URL and Execute Request
        query_url = self._build_url(self.config.base_url, params)
        logger.info("Querying USGS Earthquake API: %s", query_url)

        raw_payload = self._execute_request(query_url)
        return EarthquakeQueryResponse.from_geojson(raw_payload, query_params=params, api_url=query_url)

    def get_event_by_id(self, event_id: str) -> Optional[EarthquakeEvent]:
        """
        Fetches a specific earthquake event by its USGS event identifier.

        Args:
            event_id: Unique event ID (e.g. 'us6000jllz' or 'nc73821031').

        Returns:
            EarthquakeEvent if found, None if not found (404).
        """
        cleaned_id = event_id.strip()
        if not cleaned_id:
            raise USGSInvalidParameterError("event_id cannot be empty.")

        params = {"eventid": cleaned_id, "format": "geojson"}
        query_url = self._build_url(self.config.base_url, params)
        logger.info("Fetching USGS earthquake by ID: %s", query_url)

        try:
            raw_payload = self._execute_request(query_url)
            # Detail queries return a single GeoJSON Feature
            if raw_payload.get("type") == "Feature":
                return EarthquakeEvent.from_geojson_feature(raw_payload)
            # Fallback if wrapped in FeatureCollection
            features = raw_payload.get("features", [])
            if features and isinstance(features[0], dict):
                return EarthquakeEvent.from_geojson_feature(features[0])
            return None
        except USGSHTTPError as err:
            if err.status_code in {404, 400}:
                logger.info("Earthquake event ID '%s' not found on USGS.", cleaned_id)
                return None
            raise

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------
    def _execute_request(self, url: str) -> dict:
        """
        Executes an HTTP GET request to the given URL and parses JSON.
        Handles timeouts, network connection failures, HTTP errors, and malformed JSON.
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

            err_msg = f"USGS API HTTP {status_code}: {http_err.reason}."
            if error_body:
                err_msg += f" Details: {error_body.strip()[:200]}"

            if status_code == 400:
                raise USGSInvalidParameterError(err_msg) from http_err
            raise USGSHTTPError(err_msg, status_code=status_code) from http_err

        except (socket.timeout, TimeoutError) as timeout_err:
            raise USGSTimeoutError(
                f"USGS Earthquake API request timed out after {self.timeout}s."
            ) from timeout_err

        except urllib.error.URLError as url_err:
            # Check if inner reason was socket timeout
            if isinstance(url_err.reason, (socket.timeout, TimeoutError)):
                raise USGSTimeoutError(
                    f"USGS Earthquake API request timed out after {self.timeout}s."
                ) from url_err
            raise USGSNetworkError(
                f"Failed to connect to USGS Earthquake API: {url_err.reason}"
            ) from url_err

        except Exception as general_err:
            raise USGSClientError(f"Unexpected error communicating with USGS: {general_err}") from general_err

        # Parse JSON payload
        try:
            text = raw_bytes.decode("utf-8")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise USGSParsingError(f"Expected GeoJSON dictionary from USGS, received {type(payload).__name__}")
            return payload
        except (json.JSONDecodeError, UnicodeDecodeError) as parse_err:
            raise USGSParsingError(f"Failed to parse USGS response as valid JSON: {parse_err}") from parse_err

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
            return val.astimezone(timezone.utc).isoformat()
        if isinstance(val, date):
            return val.isoformat()
        if isinstance(val, str):
            cleaned = val.strip()
            if not cleaned:
                raise USGSInvalidParameterError("Date parameter string cannot be blank.")
            return cleaned
        raise USGSInvalidParameterError(f"Unsupported date type: {type(val).__name__}")

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
                raise USGSInvalidParameterError(f"{label} ({val}) is outside valid range [{lower}, {upper}].")

        if min_lat is not None and max_lat is not None and float(min_lat) > float(max_lat):
            raise USGSInvalidParameterError(
                f"min_latitude ({min_lat}) cannot be greater than max_latitude ({max_lat})."
            )

        if min_lon is not None and max_lon is not None and float(min_lon) > float(max_lon):
            raise USGSInvalidParameterError(
                f"min_longitude ({min_lon}) cannot be greater than max_longitude ({max_lon})."
            )

    @staticmethod
    def format_earthquakes_for_display(response: EarthquakeQueryResponse) -> str:
        """
        Formats an EarthquakeQueryResponse into a human-readable terminal report.
        """
        lines = []
        divider = "=" * 80
        thin_divider = "-" * 80

        lines.append(divider)
        lines.append(" USGS EARTHQUAKE CATALOG REPORT")
        lines.append(divider)
        lines.append(f" Total Events Found   : {response.count}")
        if response.api_url:
            lines.append(f" Query API URL        : {response.api_url}")
        lines.append(f" Provenance Notice    : {response.disclaimer}")
        lines.append(divider)

        if not response.events:
            lines.append("  [!] No earthquakes found matching the specified query parameters.")
            lines.append(divider)
            return "\n".join(lines)

        for idx, ev in enumerate(response.events, start=1):
            mag_str = f"M {ev.magnitude:.1f}" if ev.magnitude is not None else "M Unknown"
            mag_type = f"({ev.magnitude_type})" if ev.magnitude_type else ""
            lines.append(f"\n[Event {idx}/{len(response.events)}] [{mag_str} {mag_type}] {ev.place}")
            lines.append(f" Event ID    : {ev.event_id}")
            lines.append(f" Origin Time : {ev.origin_time_str or 'Unknown'}")
            
            coords = []
            if ev.latitude is not None and ev.longitude is not None:
                coords.append(f"Lat: {ev.latitude:.4f}, Lon: {ev.longitude:.4f}")
            if ev.depth_km is not None:
                coords.append(f"Depth: {ev.depth_km:.1f} km")
            if coords:
                lines.append(f" Epicenter   : {', '.join(coords)}")

            if ev.alert_level:
                lines.append(f" PAGER Alert : {ev.alert_level.upper()}")
            if ev.mmi is not None:
                lines.append(f" Max MMI     : {ev.mmi:.1f}")
            if ev.felt_reports is not None:
                lines.append(f" DYFI Felt   : {ev.felt_reports} reports")
            if ev.url:
                lines.append(f" USGS URL    : {ev.url}")

        return "\n".join(lines)


def main() -> int:
    """CLI runner for direct testing and query execution."""
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="USGS Earthquake Catalog Query Client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--start-time", default=None, help="Start time (e.g. '2023-02-06' or '2023-02-06T00:00:00Z')")
    parser.add_argument("--end-time", default=None, help="End time (e.g. '2023-02-07')")
    parser.add_argument("--min-mag", type=float, default=6.0, help="Minimum magnitude threshold")
    parser.add_argument("--max-mag", type=float, default=None, help="Maximum magnitude threshold")
    parser.add_argument("--event-id", default=None, help="Query specific USGS event ID (e.g. 'us6000jllz')")
    parser.add_argument("--limit", type=int, default=10, help="Max results to return")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")

    args = parser.parse_args()
    client = USGSClient()

    try:
        if args.event_id:
            event = client.get_event_by_id(args.event_id)
            if not event:
                print(f"Event ID '{args.event_id}' not found.", file=sys.stderr)
                return 1
            if args.json:
                print(event.model_dump_json(indent=2))
            else:
                resp = EarthquakeQueryResponse(count=1, events=[event])
                print(client.format_earthquakes_for_display(resp))
            return 0

        response = client.query_earthquakes(
            start_time=args.start_time,
            end_time=args.end_time,
            min_magnitude=args.min_mag,
            max_magnitude=args.max_mag,
            limit=args.limit,
        )

        if args.json:
            print(response.model_dump_json(indent=2))
        else:
            print(client.format_earthquakes_for_display(response))
        return 0

    except USGSClientError as err:
        print(f"\n[USGS API Error] {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

