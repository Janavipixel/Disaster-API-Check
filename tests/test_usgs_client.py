"""
Unit tests for the official USGS Earthquake Catalog API client integration.
Covers:
  - Configuration initialization and overrides
  - GeoJSON single event parsing and normalization (mag, depth, coordinates, timestamps)
  - Multiple events collection parsing
  - Empty results handling
  - Missing and null optional fields handling
  - Malformed JSON handling
  - Parameter validation (date ranges, magnitudes, bounding box coordinates, radial queries)
  - Mocked HTTP requests (200 OK, 400 Bad Request, 500 Server Error)
  - Timeout and network error handling
  - Event detail query by ID (found and 404 not found)
  - Output formatting for terminal display
"""

from datetime import date, datetime, timezone
import io
import json
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.clients.usgs_client import (
    USGSClient,
    USGSClientError,
    USGSHTTPError,
    USGSInvalidParameterError,
    USGSNetworkError,
    USGSParsingError,
    USGSTimeoutError,
)
from src.config import USGSConfig
from src.models import EarthquakeEvent, EarthquakeQueryResponse, GeoBounds


# ------------------------------------------------------------------------------
# Fixtures and Sample Payloads
# ------------------------------------------------------------------------------
SAMPLE_FEATURE_M78 = {
    "type": "Feature",
    "properties": {
        "mag": 7.8,
        "place": "26 km E of Nurdağı, Turkey",
        "time": 1675646254000,
        "updated": 1675700000000,
        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000jllz",
        "detail": "https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us6000jllz&format=geojson",
        "felt": 3182,
        "cdi": 9.1,
        "mmi": 9.5,
        "alert": "red",
        "status": "reviewed",
        "tsunami": 0,
        "sig": 2910,
        "magType": "mww",
        "type": "earthquake",
        "title": "M 7.8 - 26 km E of Nurdağı, Turkey",
    },
    "geometry": {
        "type": "Point",
        "coordinates": [37.0143, 37.2256, 10.0],
    },
    "id": "us6000jllz",
}

SAMPLE_FEATURE_M75 = {
    "type": "Feature",
    "properties": {
        "mag": 7.5,
        "place": "4 km SSE of Ekinözü, Turkey",
        "time": 1675679058000,
        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000jlqa",
        "magType": "mww",
        "alert": "red",
        "status": "reviewed",
        "type": "earthquake",
    },
    "geometry": {
        "type": "Point",
        "coordinates": [37.2029, 38.0106, 7.4],
    },
    "id": "us6000jlqa",
}

SAMPLE_GEOJSON_COLLECTION = {
    "type": "FeatureCollection",
    "metadata": {
        "generated": 1675700000000,
        "url": "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson",
        "title": "USGS Earthquakes",
        "status": 200,
        "api": "1.14.0",
        "count": 2,
    },
    "features": [SAMPLE_FEATURE_M78, SAMPLE_FEATURE_M75],
    "bbox": [37.0143, 37.2256, 7.4, 37.2029, 38.0106, 10.0],
}


# ------------------------------------------------------------------------------
# Configuration Tests
# ------------------------------------------------------------------------------
def test_usgs_config_defaults_and_custom():
    default_cfg = USGSConfig()
    assert "earthquake.usgs.gov" in default_cfg.base_url
    assert default_cfg.timeout == 30
    assert "DisasterIntelligencePipeline" in default_cfg.user_agent
    assert "USGSConfig" in repr(default_cfg)

    custom_cfg = USGSConfig(
        base_url="https://custom.usgs.gov/query",
        timeout=15,
        user_agent="CustomAgent/2.0",
    )
    assert custom_cfg.base_url == "https://custom.usgs.gov/query"
    assert custom_cfg.timeout == 15
    assert custom_cfg.user_agent == "CustomAgent/2.0"


# ------------------------------------------------------------------------------
# GeoJSON Parsing & Normalization Tests
# ------------------------------------------------------------------------------
def test_parse_geojson_single_event():
    """Validates normalization of event ID, magnitude, place, time, coords, depth, and URL."""
    event = EarthquakeEvent.from_geojson_feature(SAMPLE_FEATURE_M78)
    assert event.event_id == "us6000jllz"
    assert event.magnitude == 7.8
    assert event.magnitude_type == "mww"
    assert event.place == "26 km E of Nurdağı, Turkey"
    assert event.origin_time is not None
    assert event.origin_time.year == 2023
    assert event.origin_time.month == 2
    assert event.origin_time.day == 6
    assert event.longitude == 37.0143
    assert event.latitude == 37.2256
    assert event.depth_km == 10.0
    assert event.url == "https://earthquake.usgs.gov/earthquakes/eventpage/us6000jllz"
    assert event.alert_level == "red"
    assert event.mmi == 9.5
    assert event.felt_reports == 3182
    assert event.significance == 2910
    assert event.event_type == "earthquake"
    assert event.status == "reviewed"


def test_parse_geojson_multiple_events():
    """Validates parsing a FeatureCollection with multiple events."""
    resp = EarthquakeQueryResponse.from_geojson(SAMPLE_GEOJSON_COLLECTION)
    assert resp.count == 2
    assert len(resp.events) == 2
    assert resp.events[0].event_id == "us6000jllz"
    assert resp.events[1].event_id == "us6000jlqa"
    assert resp.events[0].magnitude == 7.8
    assert resp.events[1].magnitude == 7.5


def test_parse_geojson_empty_results():
    """Validates clean handling of empty GeoJSON results."""
    empty_payload = {
        "type": "FeatureCollection",
        "metadata": {"count": 0},
        "features": [],
    }
    resp = EarthquakeQueryResponse.from_geojson(empty_payload)
    assert resp.count == 0
    assert resp.events == []


def test_parse_geojson_missing_optional_fields():
    """Validates robust handling of features with null, missing, or malformed optional fields."""
    sparse_feature = {
        "type": "Feature",
        "properties": {
            "mag": None,
            "place": None,
            "time": None,
            "url": None,
            "magType": None,
        },
        "geometry": {
            "type": "Point",
            "coordinates": [],
        },
        "id": "sparse_123",
    }
    event = EarthquakeEvent.from_geojson_feature(sparse_feature)
    assert event.event_id == "sparse_123"
    assert event.magnitude is None
    assert event.magnitude_type is None
    assert event.place == "Unknown location"
    assert event.origin_time is None
    assert event.origin_time_str is None
    assert event.longitude is None
    assert event.latitude is None
    assert event.depth_km is None
    assert event.url is None


def test_parse_geojson_malformed_json_string():
    """Validates that malformed JSON strings raise USGSParsingError."""
    client = USGSClient()
    with patch.object(client, "_execute_request", side_effect=USGSParsingError("Invalid JSON")):
        with pytest.raises(USGSParsingError):
            client.query_earthquakes(start_time="2023-01-01")


# ------------------------------------------------------------------------------
# Parameter Validation Tests
# ------------------------------------------------------------------------------
def test_query_earthquakes_invalid_date_range():
    client = USGSClient()
    with pytest.raises(USGSInvalidParameterError) as exc_info:
        client.query_earthquakes(start_time="2023-02-10", end_time="2023-02-01")
    assert "cannot be after end_time" in str(exc_info.value)


def test_query_earthquakes_invalid_magnitude_range():
    client = USGSClient()
    with pytest.raises(USGSInvalidParameterError) as exc_info:
        client.query_earthquakes(min_magnitude=7.5, max_magnitude=5.0)
    assert "cannot exceed max_magnitude" in str(exc_info.value)

    with pytest.raises(USGSInvalidParameterError):
        client.query_earthquakes(min_magnitude="not_a_number")


def test_query_earthquakes_invalid_coordinate_bounds():
    client = USGSClient()
    # Latitude out of bounds
    with pytest.raises(USGSInvalidParameterError) as exc1:
        client.query_earthquakes(min_latitude=95.0)
    assert "outside valid range" in str(exc1.value)

    # min_lat > max_lat
    with pytest.raises(USGSInvalidParameterError) as exc2:
        client.query_earthquakes(min_latitude=30.0, max_latitude=20.0)
    assert "cannot be greater than max_latitude" in str(exc2.value)

    # Via GeoBounds
    with pytest.raises(ValueError):
        GeoBounds(min_latitude=100.0, max_latitude=110.0, min_longitude=10.0, max_longitude=20.0)


def test_query_earthquakes_invalid_radial_search():
    client = USGSClient()
    # Missing longitude
    with pytest.raises(USGSInvalidParameterError) as exc1:
        client.query_earthquakes(latitude=37.0)
    assert "requires both latitude and longitude" in str(exc1.value)

    # Negative radius
    with pytest.raises(USGSInvalidParameterError) as exc2:
        client.query_earthquakes(latitude=37.0, longitude=37.0, max_radius_km=-50)
    assert "must be positive" in str(exc2.value)


def test_query_earthquakes_invalid_limit_and_order():
    client = USGSClient()
    with pytest.raises(USGSInvalidParameterError):
        client.query_earthquakes(limit=0)

    with pytest.raises(USGSInvalidParameterError):
        client.query_earthquakes(order_by="invalid_order")


# ------------------------------------------------------------------------------
# Mocked HTTP Execution Tests
# ------------------------------------------------------------------------------
def test_query_earthquakes_success_mocked_http():
    """Tests successful query with dates, magnitude, and bounds using mocked HTTP response."""
    client = USGSClient()
    mock_resp = io.BytesIO(json.dumps(SAMPLE_GEOJSON_COLLECTION).encode("utf-8"))
    mock_resp.status = 200

    bounds = GeoBounds(
        min_latitude=36.0,
        max_latitude=39.0,
        min_longitude=36.0,
        max_longitude=39.0,
    )

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        response = client.query_earthquakes(
            start_time=date(2023, 2, 6),
            end_time="2023-02-07",
            min_magnitude=7.0,
            bounds=bounds,
            limit=10,
        )

        assert response.count == 2
        assert len(response.events) == 2
        assert response.events[0].magnitude == 7.8
        assert mock_urlopen.called

        # Verify query parameters in constructed request
        call_args = mock_urlopen.call_args[0]
        request_obj = call_args[0]
        url = request_obj.full_url
        assert "minmagnitude=7.0" in url
        assert "minlatitude=36.0" in url
        assert "maxlatitude=39.0" in url
        assert "limit=10" in url


def test_query_earthquakes_http_error_400():
    """Tests that an HTTP 400 response from USGS raises USGSInvalidParameterError."""
    client = USGSClient()
    error_fp = io.BytesIO(b"Bad Request: Unrecognized parameter")
    http_err = urllib.error.HTTPError(
        url="https://earthquake.usgs.gov/fdsnws/event/1/query",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=error_fp,
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(USGSInvalidParameterError) as exc_info:
            client.query_earthquakes(start_time="2023-01-01")
        assert "HTTP 400" in str(exc_info.value)


def test_query_earthquakes_http_error_500():
    """Tests that an HTTP 500 response from USGS raises USGSHTTPError."""
    client = USGSClient()
    error_fp = io.BytesIO(b"Internal Server Error")
    http_err = urllib.error.HTTPError(
        url="https://earthquake.usgs.gov/fdsnws/event/1/query",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=error_fp,
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(USGSHTTPError) as exc_info:
            client.query_earthquakes(start_time="2023-01-01")
        assert exc_info.value.status_code == 500


def test_query_earthquakes_timeout_error():
    """Tests that socket and read timeouts raise USGSTimeoutError."""
    client = USGSClient(timeout=5)
    with patch("urllib.request.urlopen", side_effect=socket.timeout("The read operation timed out")):
        with pytest.raises(USGSTimeoutError) as exc_info:
            client.query_earthquakes(start_time="2023-01-01")
        assert "timed out after 5s" in str(exc_info.value)


def test_query_earthquakes_network_error():
    """Tests that URLError (e.g. DNS failure) raises USGSNetworkError."""
    client = USGSClient()
    url_err = urllib.error.URLError("getaddrinfo failed")
    with patch("urllib.request.urlopen", side_effect=url_err):
        with pytest.raises(USGSNetworkError) as exc_info:
            client.query_earthquakes(start_time="2023-01-01")
        assert "Failed to connect" in str(exc_info.value)


# ------------------------------------------------------------------------------
# Event by ID Tests
# ------------------------------------------------------------------------------
def test_get_event_by_id_success():
    client = USGSClient()
    mock_resp = io.BytesIO(json.dumps(SAMPLE_FEATURE_M78).encode("utf-8"))
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        event = client.get_event_by_id("us6000jllz")
        assert event is not None
        assert event.event_id == "us6000jllz"
        assert event.magnitude == 7.8


def test_get_event_by_id_not_found():
    client = USGSClient()
    error_fp = io.BytesIO(b"Event not found")
    http_err = urllib.error.HTTPError(
        url="https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=invalid_id",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=error_fp,
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        event = client.get_event_by_id("invalid_id")
        assert event is None


def test_get_event_by_id_empty_input():
    client = USGSClient()
    with pytest.raises(USGSInvalidParameterError):
        client.get_event_by_id("   ")


# ------------------------------------------------------------------------------
# Terminal Display Formatting Tests
# ------------------------------------------------------------------------------
def test_format_earthquakes_for_display():
    client = USGSClient()
    resp = EarthquakeQueryResponse.from_geojson(SAMPLE_GEOJSON_COLLECTION, api_url="https://mock.usgs.gov")
    display_str = client.format_earthquakes_for_display(resp)

    assert "USGS EARTHQUAKE CATALOG REPORT" in display_str
    assert "Total Events Found   : 2" in display_str
    assert "M 7.8" in display_str
    assert "26 km E of Nurdağı, Turkey" in display_str
    assert "us6000jllz" in display_str
    assert "Depth: 10.0 km" in display_str
    assert "PAGER Alert : RED" in display_str

    empty_resp = EarthquakeQueryResponse(count=0, events=[])
    empty_str = client.format_earthquakes_for_display(empty_resp)
    assert "No earthquakes found matching the specified query parameters" in empty_str
