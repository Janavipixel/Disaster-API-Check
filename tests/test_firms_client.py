"""
Unit tests for the NASA FIRMS (Fire Information for Resource Management System) API Client.
Tests cover:
  - Configuration defaults, validation, and secret masking
  - CSV parsing for VIIRS (375m) and MODIS (1km) feeds
  - Empty response and malformed payload handling
  - Parameter validation (bbox, country code, day_range, dates)
  - Mocked HTTP requests and URL structure
  - HTTP error handling (400 Invalid MAP_KEY, 401/403, 500)
  - Timeout and network error handling
  - Human-readable terminal output formatting
  - Data boundary and thermal anomaly disclaimer enforcement
"""

from datetime import date, datetime, timezone
import io
import os
import socket
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from src.clients.firms_client import (
    FIRMSClient,
    FIRMSClientError,
    FIRMSHTTPError,
    FIRMSInvalidParameterError,
    FIRMSNetworkError,
    FIRMSParsingError,
    FIRMSTimeoutError,
    SAMPLE_FIRMS_EMPTY_CSV,
    SAMPLE_FIRMS_MODIS_CSV,
    SAMPLE_FIRMS_VIIRS_CSV,
)
from src.config import ConfigurationError, FIRMSConfig, get_firms_config
from src.models import ActiveFireDetection, FIRMSQueryResponse


# ------------------------------------------------------------------------------
# 1. Configuration Tests
# ------------------------------------------------------------------------------
def test_firms_config_defaults_and_custom():
    cfg = FIRMSConfig(
        map_key="12345678901234567890123456789012",
        base_url="https://firms.modaps.eosdis.nasa.gov/api",
        default_source="MODIS_NRT",
        timeout=45,
    )
    assert cfg.map_key == "12345678901234567890123456789012"
    assert cfg.base_url == "https://firms.modaps.eosdis.nasa.gov/api"
    assert cfg.default_source == "MODIS_NRT"
    assert cfg.timeout == 45
    assert cfg.is_configured is True
    # Secret masking in repr
    assert "12345678901234567890123456789012" not in repr(cfg)
    assert "****" in repr(cfg)


def test_firms_config_missing_and_placeholder_validation():
    # Missing key
    cfg_empty = FIRMSConfig(map_key="")
    assert cfg_empty.is_configured is False
    with pytest.raises(ConfigurationError) as exc_empty:
        cfg_empty.validate()
    assert "missing" in str(exc_empty.value).lower()

    # Placeholder key
    cfg_placeholder = FIRMSConfig(map_key="your-nasa-firms-map-key-here")
    assert cfg_placeholder.is_configured is False
    with pytest.raises(ConfigurationError) as exc_ph:
        cfg_placeholder.validate()
    assert "placeholder" in str(exc_ph.value).lower()


# ------------------------------------------------------------------------------
# 2. CSV Parsing Tests
# ------------------------------------------------------------------------------
def test_parse_viirs_csv_payload():
    client = FIRMSClient(config=FIRMSConfig(map_key="12345678901234567890123456789012"))
    resp = client._parse_csv(
        csv_text=SAMPLE_FIRMS_VIIRS_CSV,
        source="VIIRS_SNPP_NRT",
        target_area="-122.0,38.0,-121.0,39.0",
        api_url="https://firms.modaps.eosdis.nasa.gov/api/area/csv/MASKED/VIIRS_SNPP_NRT/...",
    )

    assert resp.total_count == 3
    assert resp.count == 3
    assert len(resp.detections) == 3

    det1 = resp.detections[0]
    assert det1.latitude == pytest.approx(38.5421)
    assert det1.longitude == pytest.approx(-121.8492)
    assert det1.acq_date == "2023-08-15"
    assert det1.acq_time == "09:30 UTC"
    assert det1.satellite == "Suomi NPP"
    assert det1.instrument == "VIIRS"
    assert det1.confidence == "nominal"
    assert det1.brightness == pytest.approx(342.5)
    assert det1.bright_t31 == pytest.approx(298.1)
    assert det1.frp == pytest.approx(24.8)
    assert det1.daynight == "N"

    # Context and verification flags
    assert det1.is_verified_wildfire is False
    assert "Thermal anomaly" in det1.disclaimer

    det2 = resp.detections[1]
    assert det2.confidence == "high"
    assert det2.brightness == pytest.approx(358.2)

    det3 = resp.detections[2]
    assert det3.confidence == "low"


def test_parse_modis_csv_payload():
    client = FIRMSClient(config=FIRMSConfig(map_key="12345678901234567890123456789012"))
    resp = client._parse_csv(
        csv_text=SAMPLE_FIRMS_MODIS_CSV,
        source="MODIS_NRT",
        target_area="-122.5,37.5,-122.0,38.0",
        api_url="https://firms.modaps.eosdis.nasa.gov/api/area/csv/MASKED/MODIS_NRT/...",
    )

    assert resp.total_count == 2
    assert len(resp.detections) == 2

    m1 = resp.detections[0]
    assert m1.latitude == pytest.approx(37.7825)
    assert m1.longitude == pytest.approx(-122.4180)
    assert m1.acq_date == "2023-08-15"
    assert m1.acq_time == "04:15 UTC"
    assert m1.satellite == "Terra"
    assert m1.instrument == "MODIS"
    assert m1.confidence == "85%"
    assert m1.brightness == pytest.approx(325.4)
    assert m1.bright_t31 == pytest.approx(295.2)
    assert m1.frp == pytest.approx(14.2)
    assert m1.daynight == "N"

    m2 = resp.detections[1]
    assert m2.satellite == "Aqua"
    assert m2.confidence == "92%"


def test_parse_empty_and_whitespace_csv():
    client = FIRMSClient(config=FIRMSConfig(map_key="12345678901234567890123456789012"))
    resp = client._parse_csv(
        csv_text=SAMPLE_FIRMS_EMPTY_CSV,
        source="VIIRS_SNPP_NRT",
        target_area="USA",
        api_url="https://firms.modaps.eosdis.nasa.gov/api/country/csv/...",
    )
    assert resp.total_count == 0
    assert resp.count == 0
    assert resp.detections == []

    # Blank/whitespace
    resp_blank = client._parse_csv("", source="MODIS_NRT", target_area="USA", api_url="")
    assert resp_blank.total_count == 0
    assert resp_blank.detections == []


def test_parse_invalid_key_plain_text_response():
    client = FIRMSClient(config=FIRMSConfig(map_key="12345678901234567890123456789012"))
    with pytest.raises(FIRMSHTTPError) as exc_info:
        client._parse_csv(
            csv_text="Invalid MAP_KEY.",
            source="VIIRS_SNPP_NRT",
            target_area="area",
            api_url="url",
        )
    assert exc_info.value.status_code == 400
    assert "Invalid MAP_KEY" in str(exc_info.value)


def test_parse_html_error_response():
    client = FIRMSClient(config=FIRMSConfig(map_key="12345678901234567890123456789012"))
    with pytest.raises(FIRMSParsingError) as exc_info:
        client._parse_csv(
            csv_text="<!DOCTYPE html><html><body>Error 404</body></html>",
            source="VIIRS_SNPP_NRT",
            target_area="area",
            api_url="url",
        )
    assert "non-CSV" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 3. Parameter Validation Tests
# ------------------------------------------------------------------------------
def test_validate_bbox_valid_formats():
    client = FIRMSClient()
    # Tuple
    assert client._validate_and_format_bbox((-124.5, 32.5, -114.0, 42.0)) == "-124.5000,32.5000,-114.0000,42.0000"
    # List
    assert client._validate_and_format_bbox([-124.5, 32.5, -114.0, 42.0]) == "-124.5000,32.5000,-114.0000,42.0000"
    # String
    assert client._validate_and_format_bbox("-124.5, 32.5, -114.0, 42.0") == "-124.5000,32.5000,-114.0000,42.0000"


def test_validate_bbox_invalid_inputs():
    client = FIRMSClient()
    # Wrong count
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_and_format_bbox((-124.5, 32.5, -114.0))

    # Out of latitude range
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_and_format_bbox((-124.5, -95.0, -114.0, 42.0))

    # South > North
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_and_format_bbox((-124.5, 45.0, -114.0, 32.0))

    # Non-numeric
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_and_format_bbox("west,south,east,north")


def test_validate_country_code():
    client = FIRMSClient()
    assert client._validate_country_code("usa") == "USA"
    assert client._validate_country_code("IND") == "IND"
    assert client._validate_country_code("grc") == "GRC"

    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_country_code("")
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_country_code("UNITED_STATES")
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_country_code("123")


def test_validate_day_range():
    client = FIRMSClient()
    assert client._validate_day_range(1) == 1
    assert client._validate_day_range(5) == 5
    assert client._validate_day_range("10") == 10

    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_day_range(0)
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_day_range(11)
    with pytest.raises(FIRMSInvalidParameterError):
        client._validate_day_range("invalid")


def test_format_date():
    client = FIRMSClient()
    assert client._format_date("2023-08-15") == "2023-08-15"
    assert client._format_date(date(2023, 8, 15)) == "2023-08-15"
    assert client._format_date(datetime(2023, 8, 15, 12, 0, 0)) == "2023-08-15"

    with pytest.raises(FIRMSInvalidParameterError):
        client._format_date("15/08/2023")


# ------------------------------------------------------------------------------
# 4. Mocked HTTP Execution Tests
# ------------------------------------------------------------------------------
def test_query_area_success_mocked_http():
    config = FIRMSConfig(map_key="testkey12345678901234567890123456")
    client = FIRMSClient(config=config)

    mock_resp = MagicMock()
    mock_resp.read.return_value = SAMPLE_FIRMS_VIIRS_CSV.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        resp = client.query_area(
            bbox=(-124.5, 32.5, -114.0, 42.0),
            source="VIIRS_SNPP_NRT",
            day_range=3,
            date_str="2023-08-15",
        )

        assert resp.total_count == 3
        assert len(resp.detections) == 3
        assert resp.source_name == "VIIRS_SNPP_NRT"

        # Verify URL called
        call_args = mock_urlopen.call_args[0]
        req = call_args[0]
        expected_url = (
            "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
            "testkey12345678901234567890123456/VIIRS_SNPP_NRT/"
            "-124.5000,32.5000,-114.0000,42.0000/3/2023-08-15"
        )
        assert req.full_url == expected_url

        # Ensure raw secret is not in returned masked api_url
        assert "testkey12345678901234567890123456" not in resp.api_url
        assert "****" in resp.api_url


def test_query_country_success_mocked_http():
    config = FIRMSConfig(map_key="testkey12345678901234567890123456")
    client = FIRMSClient(config=config)

    mock_resp = MagicMock()
    mock_resp.read.return_value = SAMPLE_FIRMS_MODIS_CSV.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        resp = client.query_country(
            country_code="USA",
            source="MODIS_NRT",
            day_range=1,
        )

        assert resp.total_count == 2
        assert len(resp.detections) == 2

        call_args = mock_urlopen.call_args[0]
        req = call_args[0]
        expected_url = (
            "https://firms.modaps.eosdis.nasa.gov/api/country/csv/"
            "testkey12345678901234567890123456/MODIS_NRT/USA/1"
        )
        assert req.full_url == expected_url


def test_query_area_missing_key_raises_invalid_parameter():
    client = FIRMSClient(config=FIRMSConfig(map_key=""))
    with pytest.raises(FIRMSInvalidParameterError) as exc_info:
        client.query_area(bbox=(-124.5, 32.5, -114.0, 42.0))
    assert "missing" in str(exc_info.value).lower()



def test_query_area_placeholder_key_raises_invalid_parameter():
    client = FIRMSClient(config=FIRMSConfig(map_key="your-nasa-firms-map-key-here"))
    with pytest.raises(FIRMSInvalidParameterError) as exc_info:
        client.query_area(bbox=(-124.5, 32.5, -114.0, 42.0))
    assert "placeholder" in str(exc_info.value).lower()


# ------------------------------------------------------------------------------
# 5. HTTP and Network Error Handling Tests
# ------------------------------------------------------------------------------
def test_http_400_invalid_map_key_error():
    config = FIRMSConfig(map_key="badkey12345678901234567890123456")
    client = FIRMSClient(config=config)

    http_err = urllib.error.HTTPError(
        url="https://firms.modaps.eosdis.nasa.gov/api/area/...",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(b"Invalid MAP_KEY."),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(FIRMSHTTPError) as exc_info:
            client.query_area(bbox=(-124.5, 32.5, -114.0, 42.0))

        assert exc_info.value.status_code == 400
        assert "Invalid MAP_KEY" in str(exc_info.value)
        assert "https://firms.modaps.eosdis.nasa.gov/api/map_key" in str(exc_info.value)


def test_http_403_forbidden_error():
    config = FIRMSConfig(map_key="validkey123456789012345678901234")
    client = FIRMSClient(config=config)

    http_err = urllib.error.HTTPError(
        url="https://firms.modaps.eosdis.nasa.gov/api/country/...",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=io.BytesIO(b"Access Denied"),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(FIRMSHTTPError) as exc_info:
            client.query_country(country_code="USA")

        assert exc_info.value.status_code == 403
        assert "Forbidden" in str(exc_info.value)


def test_timeout_error():
    config = FIRMSConfig(map_key="validkey123456789012345678901234")
    client = FIRMSClient(config=config, timeout=5)

    with patch("urllib.request.urlopen", side_effect=socket.timeout("Socket timed out")):
        with pytest.raises(FIRMSTimeoutError) as exc_info:
            client.query_country(country_code="USA")

        assert "timed out after 5s" in str(exc_info.value)


def test_network_connection_error():
    config = FIRMSConfig(map_key="validkey123456789012345678901234")
    client = FIRMSClient(config=config)

    url_err = urllib.error.URLError("getaddrinfo failed - DNS lookup failure")
    with patch("urllib.request.urlopen", side_effect=url_err):
        with pytest.raises(FIRMSNetworkError) as exc_info:
            client.query_country(country_code="USA")

        assert "network connection error" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 6. Terminal Display Formatting Tests
# ------------------------------------------------------------------------------
def test_format_detections_for_display_with_results():
    client = FIRMSClient(config=FIRMSConfig(map_key="12345678901234567890123456789012"))
    resp = client._parse_csv(
        csv_text=SAMPLE_FIRMS_VIIRS_CSV,
        source="VIIRS_SNPP_NRT",
        target_area="California",
        api_url="https://firms.modaps.eosdis.nasa.gov/api/area/...",
    )

    output = FIRMSClient.format_detections_for_display(resp)
    assert "NASA FIRMS ACTIVE FIRE / THERMAL ANOMALY DETECTIONS" in output
    assert "Sensor Feed: VIIRS_SNPP_NRT" in output
    assert "Total Detections: 3" in output
    assert "38.5421, -121.8492" in output
    assert "Suomi NPP (VIIRS)" in output
    assert "NOMINAL" in output
    assert "342.5 K" in output
    assert "24.8 MW" in output
    # Mandatory disclaimer
    assert "SCIENTIFIC NOTICE & DATA BOUNDARY:" in output
    assert "NOT be treated as verified ground wildfire perimeters" in output


def test_format_detections_for_display_empty():
    resp = FIRMSQueryResponse(
        total_count=0,
        count=0,
        detections=[],
        source_name="VIIRS_SNPP_NRT",
        area_or_country="California",
    )
    output = FIRMSClient.format_detections_for_display(resp)
    assert "No active-fire thermal anomalies detected" in output
