"""
Official NASA FIRMS (Fire Information for Resource Management System) API Client.
Retrieves active fire and thermal anomaly detections from satellite radiometers
(MODIS on Terra & Aqua, VIIRS on Suomi NPP, NOAA-20, and NOAA-21).

A service of NASA EOSDIS (Earth Observing System Data and Information System).
Requires a free 32-character MAP_KEY obtained at:
https://firms.modaps.eosdis.nasa.gov/api/map_key

Important Scientific Context:
Active fire detections represent thermal anomalies (heat signatures). They indicate
high-temperature pixels (e.g. wildfires, prescribed burns, industrial flaring, or
agricultural clearing) and must NOT be treated as definitive ground-verified wildfire
perimeters without corroborating context.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import io
import logging
from pathlib import Path
import re
import socket
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request

# Ensure project root is in sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import FIRMSConfig, get_firms_config, mask_api_key
from src.models import ActiveFireDetection, FIRMSQueryResponse

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------
class FIRMSClientError(Exception):
    """Base exception for all NASA FIRMS client errors."""
    pass


class FIRMSInvalidParameterError(FIRMSClientError):
    """Raised when query parameters (coordinates, bounding box, date, day_range) are invalid."""
    pass


class FIRMSTimeoutError(FIRMSClientError):
    """Raised when an API request to NASA FIRMS times out."""
    pass


class FIRMSHTTPError(FIRMSClientError):
    """Raised when the NASA FIRMS API returns an HTTP 4xx or 5xx error code."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class FIRMSParsingError(FIRMSClientError):
    """Raised when the response cannot be parsed as valid CSV data."""
    pass


class FIRMSNetworkError(FIRMSClientError):
    """Raised on socket/DNS connection failures when contacting NASA FIRMS."""
    pass


# ------------------------------------------------------------------------------
# Sample Offline Fixtures for Testing
# ------------------------------------------------------------------------------
SAMPLE_FIRMS_VIIRS_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
    "38.5421,-121.8492,342.5,0.39,0.36,2023-08-15,0930,N,VIIRS,nominal,2.0NRT,298.1,24.8,N\n"
    "38.5612,-121.8210,358.2,0.41,0.37,2023-08-15,0930,N,VIIRS,high,2.0NRT,301.4,45.2,N\n"
    "38.5105,-121.8841,318.4,0.39,0.36,2023-08-15,0930,N,VIIRS,low,2.0NRT,292.0,8.1,N\n"
)

SAMPLE_FIRMS_MODIS_CSV = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n"
    "37.7825,-122.4180,325.4,1.1,1.0,2023-08-15,0415,Terra,MODIS,85,6.1NRT,295.2,14.2,N\n"
    "37.7950,-122.4050,336.8,1.1,1.0,2023-08-15,0415,Aqua,MODIS,92,6.1NRT,298.6,22.0,N\n"
)

SAMPLE_FIRMS_EMPTY_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
)


# ------------------------------------------------------------------------------
# Client Implementation
# ------------------------------------------------------------------------------
class FIRMSClient:
    """
    Client for interacting with the NASA FIRMS Active Fire API.
    Supports querying active fire / thermal anomaly detections by geographic
    bounding box (Area API) and country code (Country API).
    """

    SUPPORTED_SOURCES: Set[str] = {
        "VIIRS_SNPP_NRT",
        "VIIRS_NOAA20_NRT",
        "VIIRS_NOAA21_NRT",
        "MODIS_NRT",
        "VIIRS_SNPP_SP",
        "MODIS_SP",
    }

    def __init__(
        self,
        config: Optional[FIRMSConfig] = None,
        timeout: Optional[int] = None,
    ):
        self.config = config or get_firms_config()
        self.timeout = timeout if timeout is not None else self.config.timeout

    def query_area(
        self,
        bbox: Union[Tuple[float, float, float, float], List[float], str],
        source: Optional[str] = None,
        day_range: int = 1,
        date_str: Optional[Union[str, date, datetime]] = None,
        map_key: Optional[str] = None,
    ) -> FIRMSQueryResponse:
        """
        Queries active fire detections within a geographic bounding box via the Area API.

        Args:
            bbox: Bounding box defined as (west, south, east, north) / (min_lon, min_lat, max_lon, max_lat)
                  either as a 4-tuple, 4-element list, or comma-separated string 'west,south,east,north'.
            source: Sensor data source (e.g. 'VIIRS_SNPP_NRT', 'MODIS_NRT'). Defaults to config.
            day_range: Number of days to retrieve backward from target date (1 to 10, default 1).
            date_str: Target date formatted as 'YYYY-MM-DD', date, or datetime. Defaults to most recent data.
            map_key: Optional override for the 32-character MAP_KEY.

        Returns:
            FIRMSQueryResponse containing parsed ActiveFireDetection records.
        """
        coords_str = self._validate_and_format_bbox(bbox)
        validated_range = self._validate_day_range(day_range)
        formatted_date = self._format_date(date_str) if date_str else None
        effective_source = (source or self.config.default_source or "VIIRS_SNPP_NRT").strip()
        effective_key = self._resolve_map_key(map_key)

        base_url = self.config.base_url.rstrip("/")
        # URL structure: /api/area/csv/{MAP_KEY}/{SOURCE}/{BBOX}/{DAY_RANGE}[/{DATE}]
        if formatted_date:
            url = f"{base_url}/area/csv/{effective_key}/{effective_source}/{coords_str}/{validated_range}/{formatted_date}"
            masked_url = f"{base_url}/area/csv/{mask_api_key(effective_key)}/{effective_source}/{coords_str}/{validated_range}/{formatted_date}"
        else:
            url = f"{base_url}/area/csv/{effective_key}/{effective_source}/{coords_str}/{validated_range}"
            masked_url = f"{base_url}/area/csv/{mask_api_key(effective_key)}/{effective_source}/{coords_str}/{validated_range}"

        csv_text = self._execute_request(url)
        return self._parse_csv(
            csv_text=csv_text,
            source=effective_source,
            target_area=coords_str,
            api_url=masked_url,
        )

    def query_country(
        self,
        country_code: str,
        source: Optional[str] = None,
        day_range: int = 1,
        date_str: Optional[Union[str, date, datetime]] = None,
        map_key: Optional[str] = None,
    ) -> FIRMSQueryResponse:
        """
        Queries active fire detections for a specific country by ISO code via the Country API.

        Args:
            country_code: 3-letter ISO country code (e.g. 'USA', 'IND', 'GRC', 'CAN').
            source: Sensor data source (e.g. 'VIIRS_SNPP_NRT', 'MODIS_NRT'). Defaults to config.
            day_range: Number of days to retrieve backward from target date (1 to 10, default 1).
            date_str: Target date formatted as 'YYYY-MM-DD', date, or datetime. Defaults to most recent data.
            map_key: Optional override for the 32-character MAP_KEY.

        Returns:
            FIRMSQueryResponse containing parsed ActiveFireDetection records.
        """
        clean_country = self._validate_country_code(country_code)
        validated_range = self._validate_day_range(day_range)
        formatted_date = self._format_date(date_str) if date_str else None
        effective_source = (source or self.config.default_source or "VIIRS_SNPP_NRT").strip()
        effective_key = self._resolve_map_key(map_key)

        base_url = self.config.base_url.rstrip("/")
        # URL structure: /api/country/csv/{MAP_KEY}/{SOURCE}/{COUNTRY}/{DAY_RANGE}[/{DATE}]
        if formatted_date:
            url = f"{base_url}/country/csv/{effective_key}/{effective_source}/{clean_country}/{validated_range}/{formatted_date}"
            masked_url = f"{base_url}/country/csv/{mask_api_key(effective_key)}/{effective_source}/{clean_country}/{validated_range}/{formatted_date}"
        else:
            url = f"{base_url}/country/csv/{effective_key}/{effective_source}/{clean_country}/{validated_range}"
            masked_url = f"{base_url}/country/csv/{mask_api_key(effective_key)}/{effective_source}/{clean_country}/{validated_range}"

        csv_text = self._execute_request(url)
        return self._parse_csv(
            csv_text=csv_text,
            source=effective_source,
            target_area=clean_country,
            api_url=masked_url,
        )

    # --------------------------------------------------------------------------
    # Internal Request & Parsing Helpers
    # --------------------------------------------------------------------------
    def _execute_request(self, url: str) -> str:
        """
        Executes HTTP GET request to NASA FIRMS API and returns raw text response.
        Handles status codes, timeout, and DNS/socket errors safely.
        """
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "text/csv, text/plain, */*",
        }
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                return raw_bytes.decode("utf-8", errors="replace")

        except urllib.error.HTTPError as http_err:
            status_code = http_err.code
            error_body = ""
            try:
                error_body = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            clean_body = error_body.strip()
            if status_code == 400:
                if "Invalid MAP_KEY" in clean_body or "MAP_KEY" in clean_body:
                    raise FIRMSHTTPError(
                        f"NASA FIRMS API HTTP 400 Bad Request: Invalid MAP_KEY. "
                        f"A valid 32-character personal MAP_KEY is required from https://firms.modaps.eosdis.nasa.gov/api/map_key. "
                        f"(Server response: {clean_body})",
                        status_code=400,
                    )
                raise FIRMSInvalidParameterError(
                    f"NASA FIRMS API HTTP 400 Bad Request: {clean_body}",
                )

            if status_code in {401, 403}:
                raise FIRMSHTTPError(
                    f"NASA FIRMS API HTTP {status_code} Unauthorized/Forbidden. "
                    f"Verify FIRMS_MAP_KEY in your .env file or request a key at https://firms.modaps.eosdis.nasa.gov/api/map_key. "
                    f"(Server response: {clean_body})",
                    status_code=status_code,
                )

            raise FIRMSHTTPError(
                f"NASA FIRMS API HTTP {status_code}: {clean_body}",
                status_code=status_code,
            )

        except (socket.timeout, TimeoutError):
            raise FIRMSTimeoutError(
                f"NASA FIRMS API request timed out after {self.timeout}s: {url}"
            )

        except urllib.error.URLError as url_err:
            reason = getattr(url_err, "reason", url_err)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise FIRMSTimeoutError(
                    f"NASA FIRMS API request timed out after {self.timeout}s: {url}"
                )
            raise FIRMSNetworkError(
                f"NASA FIRMS network connection error: {reason}"
            )

        except Exception as exc:
            raise FIRMSClientError(f"Unexpected error communicating with NASA FIRMS: {exc}")

    def _parse_csv(
        self,
        csv_text: str,
        source: str,
        target_area: str,
        api_url: str,
    ) -> FIRMSQueryResponse:
        """
        Parses raw CSV string into FIRMSQueryResponse and ActiveFireDetection records.
        Handles text errors, header-only empty responses, and malformed rows.
        Never fabricates detections.
        """
        if not csv_text or not csv_text.strip():
            return FIRMSQueryResponse(
                total_count=0,
                count=0,
                detections=[],
                source_name=source,
                area_or_country=target_area,
                api_url=api_url,
            )

        clean_text = csv_text.strip()

        # Check for plain text error responses that might arrive with HTTP 200
        if clean_text.startswith("Invalid MAP_KEY") or clean_text == "Invalid MAP_KEY.":
            raise FIRMSHTTPError(
                "NASA FIRMS API error: Invalid MAP_KEY. Please provide a valid 32-character key "
                "from https://firms.modaps.eosdis.nasa.gov/api/map_key.",
                status_code=400,
            )

        if "Error:" in clean_text[:60] or "DOCTYPE html" in clean_text[:60]:
            raise FIRMSParsingError(
                f"NASA FIRMS returned non-CSV response: {clean_text[:200]}"
            )

        detections: List[ActiveFireDetection] = []
        try:
            reader = csv.DictReader(io.StringIO(clean_text))
            for row in reader:
                if not row or not any(row.values()):
                    continue
                try:
                    det = ActiveFireDetection.from_csv_row(row)
                    detections.append(det)
                except Exception as row_err:
                    logger.debug("Skipping unparseable FIRMS CSV row: %s (Row: %s)", row_err, row)
                    continue

        except Exception as parse_err:
            raise FIRMSParsingError(f"Failed to parse NASA FIRMS CSV response: {parse_err}")

        return FIRMSQueryResponse(
            total_count=len(detections),
            count=len(detections),
            detections=detections,
            source_name=source,
            area_or_country=target_area,
            api_url=api_url,
        )

    # --------------------------------------------------------------------------
    # Validation & Formatting Helpers
    # --------------------------------------------------------------------------
    def _resolve_map_key(self, map_key: Optional[str]) -> str:
        """Resolves and validates that a non-placeholder MAP_KEY is present."""
        key = (map_key if map_key is not None else self.config.map_key or "").strip()
        if not key:
            raise FIRMSInvalidParameterError(
                "NASA FIRMS MAP_KEY is missing. Please set FIRMS_MAP_KEY in your .env file "
                "or pass it explicitly (obtain a free key at https://firms.modaps.eosdis.nasa.gov/api/map_key)."
            )
        if key == "your-nasa-firms-map-key-here" or key.startswith("your-"):
            raise FIRMSInvalidParameterError(
                "NASA FIRMS MAP_KEY is set to placeholder value. "
                "Please configure a valid 32-character key from https://firms.modaps.eosdis.nasa.gov/api/map_key in .env."
            )
        return key

    @staticmethod
    def _validate_and_format_bbox(
        bbox: Union[Tuple[float, float, float, float], List[float], str]
    ) -> str:
        """
        Validates bounding box coordinates in order: west, south, east, north
        (i.e. min_lon, min_lat, max_lon, max_lat).
        Returns comma-separated numeric string.
        """
        coords: List[float] = []
        if isinstance(bbox, str):
            parts = [p.strip() for p in bbox.split(",") if p.strip()]
            if len(parts) != 4:
                raise FIRMSInvalidParameterError(
                    f"Bounding box string must contain exactly 4 comma-separated values 'west,south,east,north', got: {bbox!r}"
                )
            try:
                coords = [float(p) for p in parts]
            except ValueError:
                raise FIRMSInvalidParameterError(f"Bounding box contains non-numeric values: {bbox!r}")
        elif isinstance(bbox, (list, tuple)):
            if len(bbox) != 4:
                raise FIRMSInvalidParameterError(
                    f"Bounding box sequence must contain exactly 4 elements (west, south, east, north), got {len(bbox)}"
                )
            try:
                coords = [float(v) for v in bbox]
            except (ValueError, TypeError):
                raise FIRMSInvalidParameterError(f"Bounding box elements must be numeric: {bbox!r}")
        else:
            raise FIRMSInvalidParameterError(f"Unsupported bbox type: {type(bbox).__name__}")

        west, south, east, north = coords

        if not (-180.0 <= west <= 180.0):
            raise FIRMSInvalidParameterError(f"west longitude ({west}) must be between -180 and 180")
        if not (-180.0 <= east <= 180.0):
            raise FIRMSInvalidParameterError(f"east longitude ({east}) must be between -180 and 180")
        if not (-90.0 <= south <= 90.0):
            raise FIRMSInvalidParameterError(f"south latitude ({south}) must be between -90 and 90")
        if not (-90.0 <= north <= 90.0):
            raise FIRMSInvalidParameterError(f"north latitude ({north}) must be between -90 and 90")
        if south > north:
            raise FIRMSInvalidParameterError(f"south latitude ({south}) cannot be greater than north latitude ({north})")

        return f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}"

    @staticmethod
    def _validate_country_code(country_code: str) -> str:
        """Validates 3-letter ISO country code."""
        clean = (country_code or "").strip().upper()
        if not clean or len(clean) not in {2, 3} or not clean.isalpha():
            raise FIRMSInvalidParameterError(
                f"Country code must be a 2 or 3-letter ISO code (e.g. 'USA', 'IND', 'GRC'), got: {country_code!r}"
            )
        return clean

    @staticmethod
    def _validate_day_range(day_range: int) -> int:
        """Validates and clamps day_range between 1 and 5 (maximum permitted by NASA FIRMS Area API)."""
        try:
            val = int(day_range)
        except (ValueError, TypeError):
            raise FIRMSInvalidParameterError(f"day_range must be an integer, got: {day_range!r}")
        if val < 1:
            return 1
        if val > 5:
            return 5
        return val

    @staticmethod
    def _format_date(d: Union[str, date, datetime]) -> str:
        """Formats a date object or string into 'YYYY-MM-DD'."""
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        if isinstance(d, date):
            return d.strftime("%Y-%m-%d")
        if isinstance(d, str):
            clean = d.strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
                return clean
            # Attempt to parse ISO or other formats
            try:
                parsed = datetime.fromisoformat(clean)
                return parsed.strftime("%Y-%m-%d")
            except Exception:
                raise FIRMSInvalidParameterError(
                    f"Date string must be in 'YYYY-MM-DD' format, got: {d!r}"
                )
        raise FIRMSInvalidParameterError(f"Unsupported date type: {type(d).__name__}")

    # --------------------------------------------------------------------------
    # Output Formatting
    # --------------------------------------------------------------------------
    @staticmethod
    def format_detections_for_display(response: FIRMSQueryResponse, max_display: int = 10) -> str:
        """
        Formats active fire detections into a clean, human-readable terminal table.
        Emphasizes thermal anomaly nature and explicit sensor attribution.
        """
        lines: List[str] = []
        d_thick = "=" * 80
        d_thin = "-" * 80

        lines.append(d_thick)
        lines.append(" NASA FIRMS ACTIVE FIRE / THERMAL ANOMALY DETECTIONS")
        lines.append(f" Sensor Feed: {response.source_name} | Query Area/Country: {response.area_or_country}")
        lines.append(f" Total Detections: {response.total_count}")
        lines.append(d_thin)

        if not response.detections:
            lines.append("  [!] No active-fire thermal anomalies detected in the queried area and time window.")
            lines.append(f"\n{d_thick}")
            return "\n".join(lines)

        lines.append("  #   Coordinates (Lat, Lon)      Date & Time (UTC)   Satellite / Instrument   Confidence   Brightness (K)  FRP (MW)")
        lines.append(d_thin)

        for idx, det in enumerate(response.detections[:max_display], start=1):
            coords = f"{det.latitude:.4f}, {det.longitude:.4f}"
            dt_str = f"{det.acq_date} {det.acq_time or 'N/A'}"
            sat_inst = f"{det.satellite or 'Sat'} ({det.instrument or 'Sensor'})"
            conf = det.confidence.upper() if det.confidence else "N/A"
            bright = f"{det.brightness:.1f} K" if det.brightness is not None else "N/A"
            frp = f"{det.frp:.1f} MW" if det.frp is not None else "N/A"

            lines.append(
                f"  {idx:<3} {coords:<26}  {dt_str:<18}  {sat_inst:<23}  {conf:<11}  {bright:<14}  {frp}"
            )

        if len(response.detections) > max_display:
            lines.append(f"  ... and {len(response.detections) - max_display} additional active fire detections.")

        lines.append(f"\n{d_thin}")
        lines.append(" [*] SCIENTIFIC NOTICE & DATA BOUNDARY:")
        lines.append("     Active-fire telemetry represents satellite thermal anomalies/heat signatures.")
        lines.append("     Thermal detections can include wildfires, prescribed burns, or industrial flares,")
        lines.append("     and must NOT be treated as verified ground wildfire perimeters without context.")
        lines.append(d_thick)

        return "\n".join(lines)


# ------------------------------------------------------------------------------
# CLI Runner
# ------------------------------------------------------------------------------
def main() -> None:
    """CLI runner for direct FIRMS API queries or sample demonstration."""
    parser = argparse.ArgumentParser(
        description="NASA FIRMS Active Fire / Thermal Anomaly API Client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--bbox",
        type=str,
        default=None,
        help="Bounding box 'west,south,east,north' (e.g. '-124.5,32.5,-114.0,42.0' for California)",
    )
    parser.add_argument(
        "--country",
        type=str,
        default=None,
        help="3-letter ISO country code (e.g. 'USA', 'IND', 'GRC')",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="VIIRS_SNPP_NRT",
        choices=["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"],
        help="Sensor data feed",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to query backward (1 to 10)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Display sample offline VIIRS fire detections fixture",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )

    args = parser.parse_args()

    # UTF-8 stdout configuration for Windows consoles
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.sample:
        client = FIRMSClient(config=FIRMSConfig(map_key="sample_key_00000000000000000000"))
        resp = client._parse_csv(
            SAMPLE_FIRMS_VIIRS_CSV,
            source=args.source,
            target_area=args.bbox or args.country or "California",
            api_url="https://firms.modaps.eosdis.nasa.gov/api/area/sample",
        )
        if args.json:
            print(resp.model_dump_json(indent=2))
        else:
            print(FIRMSClient.format_detections_for_display(resp))
        return

    if not args.bbox and not args.country:
        print("[!] Please specify --bbox, --country, or --sample. Use --help for guidance.", file=sys.stderr)
        sys.exit(1)

    client = FIRMSClient()
    try:
        if args.bbox:
            response = client.query_area(
                bbox=args.bbox,
                source=args.source,
                day_range=args.days,
                date_str=args.date,
            )
        else:
            response = client.query_country(
                country_code=args.country,
                source=args.source,
                day_range=args.days,
                date_str=args.date,
            )

        if args.json:
            print(response.model_dump_json(indent=2))
        else:
            print(FIRMSClient.format_detections_for_display(response))

    except FIRMSClientError as err:
        print(f"\n[NASA FIRMS Error] {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

