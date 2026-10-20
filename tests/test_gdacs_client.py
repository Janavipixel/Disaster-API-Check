"""
Unit tests for the official GDACS (Global Disaster Alert and Coordination System) API client.
Covers:
  - Configuration initialization, defaults, and overrides
  - GeoJSON single event parsing and normalization (floods, earthquakes, tropical cyclones)
  - Multiple events collection parsing
  - Empty results handling (HTTP 204 / empty byte payload safeguard)
  - Missing and null optional fields handling
  - Malformed JSON handling
  - Parameter validation (hazard types, aliases, alert levels, date ranges, pagination, coordinates)
  - Client-side spatial bounding box and radial distance filtering
  - Mocked HTTP requests (200 OK, 400 Bad Request, 500 Server Error)
  - Timeout and network error handling
  - Event detail query by ID (composite ID, explicit type, 404 not found)
  - Output formatting for terminal display with provenance and data limitation notices
"""

from datetime import date, datetime, timezone
import io
import json
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.clients.gdacs_client import (
    GDACSClient,
    GDACSClientError,
    GDACSHTTPError,
    GDACSInvalidParameterError,
    GDACSNetworkError,
    GDACSParsingError,
    GDACSTimeoutError,
)
from src.config import GDACSConfig
from src.models import GDACSEvent, GDACSQueryResponse, GeoBounds


# ------------------------------------------------------------------------------
# Fixtures and Sample GeoJSON Payloads
# ------------------------------------------------------------------------------
SAMPLE_FEATURE_KERALA_FLOOD = {
    "type": "Feature",
    "bbox": [76.403, 9.919, 76.403, 9.919],
    "geometry": {
        "type": "Point",
        "coordinates": [76.403, 9.919],
    },
    "properties": {
        "eventtype": "FL",
        "eventid": 1000212,
        "episodeid": 2,
        "eventname": None,
        "glide": "2018-000134",
        "name": "Flood in India",
        "description": "Flood in India",
        "htmldescription": "Orange Flood in India from: 10 Aug 2018 00 to: 24 Sep 2018 00.",
        "icon": "https://www.gdacs.org/images/gdacs_icons/maps/orange/FL.png",
        "url": {
            "geometry": "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry?eventtype=FL&eventid=1000212&episodeid=2",
            "report": "https://www.gdacs.org/report.aspx?eventid=1000212&episodeid=2&eventtype=FL",
            "details": "https://www.gdacs.org/gdacsapi/api/events/geteventdata?eventtype=FL&eventid=1000212",
        },
        "alertlevel": "Orange",
        "alertscore": 2.0,
        "episodealertlevel": "orange",
        "episodealertscore": 0.0,
        "istemporary": "false",
        "iscurrent": "false",
        "country": "India",
        "fromdate": "2018-08-10T00:00:00",
        "todate": "2018-09-24T00:00:00",
        "iso3": "IND",
        "affectedcountries": [
            {"iso2": "IN", "iso3": "IND", "countryname": "India"}
        ],
        "severitydata": {
            "severity": 0.0,
            "severitytext": "Magnitude 0.00",
            "severityunit": "",
        },
    },
}

SAMPLE_FEATURE_TURKEY_EQ = {
    "type": "Feature",
    "bbox": [37.0143, 37.2256, 37.0143, 37.2256],
    "geometry": {
        "type": "Point",
        "coordinates": [37.0143, 37.2256],
    },
    "properties": {
        "eventtype": "EQ",
        "eventid": 1357372,
        "episodeid": 1,
        "eventname": "Kahramanmaras Earthquake",
        "glide": "EQ-2023-000015-TUR",
        "name": "Earthquake in Türkiye",
        "description": "Earthquake in Türkiye, Gaziantep province",
        "htmldescription": "Red Earthquake in Türkiye from: 06 Feb 2023.",
        "url": {
            "report": "https://www.gdacs.org/report.aspx?eventid=1357372&episodeid=1&eventtype=EQ",
            "details": "https://www.gdacs.org/gdacsapi/api/events/geteventdata?eventtype=EQ&eventid=1357372",
        },
        "alertlevel": "Red",
        "alertscore": 3.0,
        "episodealertlevel": "red",
        "episodealertscore": 3.0,
        "iscurrent": False,
        "country": "Türkiye",
        "fromdate": "2023-02-06T01:17:34",
        "todate": "2023-02-06T01:17:34",
        "iso3": "TUR",
        "affectedcountries": [
            {"iso2": "TR", "iso3": "TUR", "countryname": "Türkiye"},
            {"iso2": "SY", "iso3": "SYR", "countryname": "Syria"},
        ],
        "severitydata": {
            "severity": 7.8,
            "severitytext": "Magnitude 7.8M, Depth:17.925km",
            "severityunit": "M",
        },
        "impacts": [
            {
                "source": "NEIC",
                "resource": {
                    "impact": "https://www.gdacs.org/gdacsapi/api/export/getimpact?id=521685"
                },
            }
        ],
    },
}

SAMPLE_GEOJSON_COLLECTION = {
    "type": "FeatureCollection",
    "features": [SAMPLE_FEATURE_KERALA_FLOOD, SAMPLE_FEATURE_TURKEY_EQ],
    "bbox": [37.0143, 9.919, 76.403, 37.2256],
}


# ------------------------------------------------------------------------------
# 1. Configuration Tests
# ------------------------------------------------------------------------------
def test_gdacs_config_defaults_and_custom():
    """Verify default endpoints, timeout, user agent, and overrides."""
    default_cfg = GDACSConfig()
    assert "geteventlist/search" in default_cfg.base_url
    assert "geteventdata" in default_cfg.event_data_url
    assert default_cfg.timeout == 30
    assert "DisasterIntelligencePipeline" in default_cfg.user_agent
    assert "GDACSConfig" in repr(default_cfg)

    custom_cfg = GDACSConfig(
        base_url="https://mock.gdacs.org/search",
        event_data_url="https://mock.gdacs.org/data",
        timeout=15,
        user_agent="CustomAgent/2.0",
    )
    assert custom_cfg.base_url == "https://mock.gdacs.org/search"
    assert custom_cfg.event_data_url == "https://mock.gdacs.org/data"
    assert custom_cfg.timeout == 15
    assert custom_cfg.user_agent == "CustomAgent/2.0"


# ------------------------------------------------------------------------------
# 2. Parsing and Normalization Tests
# ------------------------------------------------------------------------------
def test_parse_geojson_single_event_flood():
    """Verify parsing and normalization of flood event (e.g. Kerala floods 2018)."""
    ev = GDACSEvent.from_geojson_feature(SAMPLE_FEATURE_KERALA_FLOOD)
    assert ev.event_id == "1000212"
    assert ev.episode_id == "2"
    assert ev.event_type == "FL"
    assert ev.event_type_name == "Flood"
    assert ev.name == "Flood in India"
    assert ev.glide == "2018-000134"
    assert ev.alert_level == "Orange"
    assert ev.alert_score == 2.0
    assert ev.country == "India"
    assert ev.iso3 == "IND"
    assert ev.longitude == 76.403
    assert ev.latitude == 9.919
    assert ev.bbox == [76.403, 9.919, 76.403, 9.919]
    assert ev.from_date_str == "2018-08-10T00:00:00+00:00"
    assert ev.report_url == "https://www.gdacs.org/report.aspx?eventid=1000212&episodeid=2&eventtype=FL"
    assert ev.is_current is False
    assert len(ev.affected_countries) == 1
    assert ev.affected_countries[0]["iso3"] == "IND"


def test_parse_geojson_single_event_earthquake():
    """Verify parsing and normalization of earthquake event (e.g. Turkey 2023 EQ)."""
    ev = GDACSEvent.from_geojson_feature(SAMPLE_FEATURE_TURKEY_EQ)
    assert ev.event_id == "1357372"
    assert ev.event_type == "EQ"
    assert ev.event_type_name == "Earthquake"
    assert ev.name == "Earthquake in Türkiye"
    assert ev.alert_level == "Red"
    assert ev.alert_score == 3.0
    assert ev.severity == 7.8
    assert ev.severity_unit == "M"
    assert ev.severity_text == "Magnitude 7.8M, Depth:17.925km"
    assert ev.country == "Türkiye"
    assert ev.iso3 == "TUR"
    assert len(ev.affected_countries) == 2
    assert len(ev.impacts) == 1
    assert ev.impacts[0]["source"] == "NEIC"


def test_parse_geojson_multiple_events_collection():
    """Verify parsing of multi-feature GeoJSON FeatureCollection."""
    response = GDACSQueryResponse.from_geojson(SAMPLE_GEOJSON_COLLECTION, api_url="https://mock.url")
    assert response.count == 2
    assert len(response.events) == 2
    assert response.events[0].event_id == "1000212"
    assert response.events[1].event_id == "1357372"
    assert response.api_url == "https://mock.url"
    assert "GDACS" in response.disclaimer


def test_parse_geojson_empty_results_and_safeguard():
    """Verify empty features list and empty raw byte payload (GDACS 204 quirk)."""
    empty_payload = {"type": "FeatureCollection", "features": []}
    response = GDACSQueryResponse.from_geojson(empty_payload)
    assert response.count == 0
    assert response.events == []

    client = GDACSClient()
    # Mocking _execute_request returning the empty fallback
    with patch.object(client, "_execute_request", return_value={"type": "FeatureCollection", "features": []}):
        resp = client.query_events(event_types="VO", from_date="2000-01-01", to_date="2000-01-02")
        assert resp.count == 0
        assert resp.events == []


def test_parse_geojson_missing_optional_fields():
    """Ensure missing or null properties in GeoJSON feature do not raise errors."""
    sparse_feature = {
        "type": "Feature",
        "properties": {
            "eventid": 99999,
            "eventtype": "TC",
        },
        "geometry": None,
    }
    ev = GDACSEvent.from_geojson_feature(sparse_feature)
    assert ev.event_id == "99999"
    assert ev.event_type == "TC"
    assert ev.event_type_name == "Tropical Cyclone"
    assert ev.latitude is None
    assert ev.longitude is None
    assert ev.bbox is None
    assert ev.country is None
    assert ev.alert_score is None
    assert ev.severity is None


def test_parse_geojson_malformed_json_string():
    """Verify GDACSParsingError is raised on corrupt response payload."""
    client = GDACSClient()
    mock_resp = io.BytesIO(b"{Not Valid JSON: <xml>}")
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(GDACSParsingError) as exc_info:
            client.query_events(event_types="FL")
        assert "Failed to parse GDACS response as valid JSON" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 3. Parameter Normalization and Validation Tests
# ------------------------------------------------------------------------------
def test_query_events_invalid_date_range():
    """Verify GDACSInvalidParameterError when start_date is chronologically after end_date."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError) as exc_info:
        client.query_events(from_date="2023-08-31", to_date="2023-08-01")
    assert "Invalid date range" in str(exc_info.value)


def test_query_events_invalid_hazard_type():
    """Verify unknown hazard type raises GDACSInvalidParameterError."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError) as exc_info:
        client.query_events(event_types="METEOR")
    assert "Unsupported hazard event type 'METEOR'" in str(exc_info.value)


def test_query_events_hazard_type_aliases():
    """Verify human aliases like 'floods', 'earthquake', 'cyclone' are normalized to codes."""
    assert GDACSClient._normalize_event_types("floods") == ["FL"]
    assert GDACSClient._normalize_event_types("earthquake") == ["EQ"]
    assert GDACSClient._normalize_event_types(["cyclone", "wildfire"]) == ["TC", "WF"]
    assert GDACSClient._normalize_event_types("FL;EQ") == ["FL", "EQ"]


def test_query_events_invalid_alert_level():
    """Verify unsupported alert level raises GDACSInvalidParameterError."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError) as exc_info:
        client.query_events(alert_levels="purple")
    assert "Unsupported alert level 'purple'" in str(exc_info.value)


def test_query_events_invalid_pagination():
    """Verify pagination validation (page_number >= 1, 1 <= page_size <= 100)."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(page_number=0)
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(page_size=0)
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(page_size=101)  # Exceeds max 100


def test_query_events_invalid_coordinate_bounds():
    """Verify bounding box validation rejects invalid lat/lon or min > max."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(min_latitude=95.0)  # > 90
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(min_latitude=40.0, max_latitude=30.0)  # min > max
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(min_longitude=120.0, max_longitude=110.0)  # min > max


def test_query_events_invalid_radial_search():
    """Verify radial search parameter requirements."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(latitude=10.0)  # missing longitude & radius
    with pytest.raises(GDACSInvalidParameterError):
        client.query_events(latitude=10.0, longitude=76.0, max_radius_km=-5.0)  # negative radius


# ------------------------------------------------------------------------------
# 4. Client-Side Spatial Filtering Tests
# ------------------------------------------------------------------------------
def test_query_events_client_side_bbox_filtering():
    """Verify that bounding box filters out events outside the spatial rectangle."""
    client = GDACSClient()
    # Mock return of Kerala Flood (lat: 9.9, lon: 76.4) and Turkey EQ (lat: 37.2, lon: 37.0)
    with patch.object(client, "_execute_request", return_value=SAMPLE_GEOJSON_COLLECTION):
        # Query only India / Kerala bounding box
        response = client.query_events(
            bounds=GeoBounds(min_latitude=8.0, max_latitude=12.0, min_longitude=75.0, max_longitude=78.0)
        )
        assert response.count == 1
        assert response.events[0].event_id == "1000212"  # Kerala flood retained, Turkey EQ excluded


def test_query_events_client_side_radial_filtering():
    """Verify that radial distance filter retains only events within radius."""
    client = GDACSClient()
    with patch.object(client, "_execute_request", return_value=SAMPLE_GEOJSON_COLLECTION):
        # Center near Kochi, Kerala with 200km radius
        response = client.query_events(
            latitude=9.9312,
            longitude=76.2673,
            max_radius_km=200.0,
        )
        assert response.count == 1
        assert response.events[0].event_id == "1000212"


# ------------------------------------------------------------------------------
# 5. Mocked HTTP Requests and Error Handling Tests
# ------------------------------------------------------------------------------
def test_query_events_success_mocked_http():
    """Verify successful HTTP GET execution and URL parameter construction."""
    client = GDACSClient()
    mock_resp = io.BytesIO(json.dumps(SAMPLE_GEOJSON_COLLECTION).encode("utf-8"))
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        response = client.query_events(
            event_types="FL",
            from_date=date(2018, 8, 1),
            to_date=date(2018, 8, 31),
            alert_levels=["orange", "red"],
            country="India",
            page_size=25,
        )
        assert response.count == 2
        mock_urlopen.assert_called_once()
        called_req = mock_urlopen.call_args[0][0]
        full_url = called_req.full_url
        assert "eventlist=FL" in full_url
        assert "fromDate=2018-08-01" in full_url
        assert "toDate=2018-08-31" in full_url
        assert "alertlevel=orange%3Bred" in full_url or "alertlevel=orange;red" in full_url
        assert "country=India" in full_url
        assert "pageSize=25" in full_url
        assert called_req.headers["User-agent"] == "DisasterIntelligencePipeline/1.0"


def test_query_events_http_error_400():
    """Verify HTTP 400 Bad Request raises GDACSInvalidParameterError."""
    client = GDACSClient()
    http_error = urllib.error.HTTPError(
        url="https://mock.url",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(b'{"error": "Invalid date format"}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(GDACSInvalidParameterError) as exc_info:
            client.query_events(event_types="FL")
        assert "GDACS API HTTP 400" in str(exc_info.value)


def test_query_events_http_error_500():
    """Verify HTTP 500 Server Error raises GDACSHTTPError with status_code."""
    client = GDACSClient()
    http_error = urllib.error.HTTPError(
        url="https://mock.url",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=io.BytesIO(b"Server Failure"),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(GDACSHTTPError) as exc_info:
            client.query_events(event_types="FL")
        assert exc_info.value.status_code == 500
        assert "GDACS API HTTP 500" in str(exc_info.value)


def test_query_events_timeout_error():
    """Verify socket timeout raises GDACSTimeoutError."""
    client = GDACSClient(timeout=10)
    with patch("urllib.request.urlopen", side_effect=socket.timeout("Connection timed out")):
        with pytest.raises(GDACSTimeoutError) as exc_info:
            client.query_events(event_types="FL")
        assert "timed out after 10s" in str(exc_info.value)


def test_query_events_network_error():
    """Verify DNS or socket connection failure raises GDACSNetworkError."""
    client = GDACSClient()
    url_error = urllib.error.URLError("Name or service not known")
    with patch("urllib.request.urlopen", side_effect=url_error):
        with pytest.raises(GDACSNetworkError) as exc_info:
            client.query_events(event_types="FL")
        assert "Failed to connect to GDACS API" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 6. Detail Event Query by ID Tests
# ------------------------------------------------------------------------------
def test_get_event_by_id_success():
    """Verify fetching event by numeric ID and hazard type."""
    client = GDACSClient()
    mock_resp = io.BytesIO(json.dumps(SAMPLE_FEATURE_KERALA_FLOOD).encode("utf-8"))
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ev = client.get_event_by_id(1000212, event_type="FL")
        assert ev is not None
        assert ev.event_id == "1000212"
        assert ev.event_type == "FL"


def test_get_event_by_id_with_composite_prefix():
    """Verify composite string 'FL-1000212' resolves type and ID."""
    client = GDACSClient()
    mock_resp = io.BytesIO(json.dumps(SAMPLE_FEATURE_KERALA_FLOOD).encode("utf-8"))
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        ev = client.get_event_by_id("FL-1000212")
        assert ev is not None
        assert ev.event_id == "1000212"
        called_url = mock_urlopen.call_args[0][0].full_url
        assert "eventtype=FL" in called_url
        assert "eventid=1000212" in called_url


def test_get_event_by_id_missing_type_raises():
    """Verify that omitting event_type on a bare numeric ID raises GDACSInvalidParameterError."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError) as exc_info:
        client.get_event_by_id("1000212")
    assert "scoped per hazard type" in str(exc_info.value)


def test_get_event_by_id_not_found():
    """Verify that HTTP 404 returns None instead of raising."""
    client = GDACSClient()
    http_error = urllib.error.HTTPError(
        url="https://mock.url",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=io.BytesIO(b"Not Found"),
    )
    with patch("urllib.request.urlopen", side_effect=http_error):
        ev = client.get_event_by_id(999999, event_type="FL")
        assert ev is None


def test_get_event_by_id_empty_input():
    """Verify that empty ID raises GDACSInvalidParameterError."""
    client = GDACSClient()
    with pytest.raises(GDACSInvalidParameterError):
        client.get_event_by_id("", event_type="FL")


# ------------------------------------------------------------------------------
# 7. Terminal Display Formatting Tests
# ------------------------------------------------------------------------------
def test_format_events_for_display():
    """Verify terminal formatting outputs all required sections, badges, and notices."""
    response = GDACSQueryResponse.from_geojson(SAMPLE_GEOJSON_COLLECTION, api_url="https://mock.api/search")
    report = GDACSClient.format_events_for_display(response)

    assert "GLOBAL DISASTER ALERT AND COORDINATION SYSTEM (GDACS) REPORT" in report
    assert "Total Alerts Found   : 2" in report
    assert "[ORANGE ALERT] Flood in India" in report
    assert "[RED ALERT] Earthquake in Türkiye" in report
    assert "GLIDE Number   : 2018-000134" in report
    assert "GLIDE Number   : EQ-2023-000015-TUR" in report
    assert "Centroid Coords: Lat: 9.9190, Lon: 76.4030" in report
    assert "Magnitude 7.8M, Depth:17.925km" in report
    assert "Casualties and damage statistics are NOT present in GDACS search feeds." in report
    assert "Verification against ground-truth incident records is required" in report

    # Test empty report formatting
    empty_report = GDACSClient.format_events_for_display(GDACSQueryResponse(count=0, events=[]))
    assert "No disaster alerts found matching the specified query parameters." in empty_report
