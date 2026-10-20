"""
Unit tests for the official ReliefWeb API (v2) client.
Covers:
  - Configuration initialization, defaults, and overrides
  - Response parsing for single and multiple humanitarian reports
  - Empty results handling (HTTP 200 with 0 count, data: [])
  - Missing and null optional fields handling
  - Malformed JSON handling
  - Parameter validation (limits, offsets, date formatting)
  - Mocked HTTP requests (200 OK POST, query, filters, payload structure)
  - HTTP error handling: 403 Forbidden (appname requirement), 400 Bad Request, 500 Server Error
  - Timeout and network error handling
  - Report detail query by ID (200 OK, 404 Not Found, empty ID)
  - Output formatting for terminal display with provenance and disclaimer notices
  - Sample authentic Kerala Floods August 2018 dataset parsing
"""

from datetime import date, datetime, timezone
import io
import json
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.clients.reliefweb_client import (
    SAMPLE_KERALA_FLOODS_PAYLOAD,
    ReliefWebClient,
    ReliefWebClientError,
    ReliefWebHTTPError,
    ReliefWebInvalidParameterError,
    ReliefWebNetworkError,
    ReliefWebParsingError,
    ReliefWebTimeoutError,
)
from src.config import ReliefWebConfig
from src.models import ReliefWebReport, ReliefWebQueryResponse


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------
SAMPLE_RAW_REPORT_ITEM = {
    "id": "1001",
    "score": 1.0,
    "fields": {
        "id": "1001",
        "title": "India: Kerala Floods - Situation Report No. 1",
        "url": "https://reliefweb.int/report/india/india-kerala-floods-sitrep-1",
        "date": {
            "created": "2018-08-18T10:00:00+00:00",
            "original": "2018-08-18T00:00:00+00:00",
        },
        "source": [
            {"id": 1, "name": "UN Children's Fund", "shortname": "UNICEF"},
            {"id": 2, "name": "Government of India", "shortname": "Govt. India"},
        ],
        "format": [{"id": 10, "name": "Situation Report"}],
        "theme": [
            {"name": "Disaster Management"},
            {"name": "Water Sanitation Hygiene"},
        ],
        "primary_country": {"id": 119, "name": "India", "iso3": "ind"},
        "country": [{"id": 119, "name": "India", "iso3": "ind"}],
        "disaster": [
            {"id": 46194, "name": "India: Floods - Aug 2018", "glide": "FL-2018-000130-IND"}
        ],
        "disaster_type": [{"id": 4611, "name": "Flood"}],
        "body": "Inundation has affected all 14 districts across the state of Kerala.",
        "headline": {"title": "Critical Flood Response Underway"},
    },
}

SAMPLE_API_RESPONSE_PAYLOAD = {
    "time": 15,
    "totalCount": 1,
    "count": 1,
    "data": [SAMPLE_RAW_REPORT_ITEM],
}


# ------------------------------------------------------------------------------
# 1. Configuration Tests
# ------------------------------------------------------------------------------
def test_reliefweb_config_defaults_and_custom():
    """Verify default and custom configuration initialization."""
    default_cfg = ReliefWebConfig()
    assert default_cfg.base_url == "https://api.reliefweb.int/v2/reports"
    assert default_cfg.timeout == 30
    assert default_cfg.limit == 10
    assert default_cfg.user_agent == "DisasterIntelligencePipeline/1.0"
    assert "ReliefWebConfig" in repr(default_cfg)

    custom_cfg = ReliefWebConfig(
        appname="TestApp-123",
        base_url="https://custom.api.org/reports",
        timeout=15,
        user_agent="CustomAgent/2.0",
        limit=25,
    )
    assert custom_cfg.appname == "TestApp-123"
    assert custom_cfg.base_url == "https://custom.api.org/reports"
    assert custom_cfg.timeout == 15
    assert custom_cfg.user_agent == "CustomAgent/2.0"
    assert custom_cfg.limit == 25


# ------------------------------------------------------------------------------
# 2. Parsing & Normalization Tests
# ------------------------------------------------------------------------------
def test_parse_api_payload_single_report():
    """Verify accurate extraction of all metadata fields from a ReliefWeb report."""
    response = ReliefWebQueryResponse.from_api_payload(SAMPLE_API_RESPONSE_PAYLOAD)
    assert response.total_count == 1
    assert response.count == 1
    assert len(response.reports) == 1

    rep = response.reports[0]
    assert rep.report_id == "1001"
    assert rep.title == "India: Kerala Floods - Situation Report No. 1"
    assert rep.url == "https://reliefweb.int/report/india/india-kerala-floods-sitrep-1"
    assert rep.publication_date == "2018-08-18T00:00:00+00:00"
    assert rep.publication_date_dt is not None
    assert rep.publication_date_dt.year == 2018
    assert rep.publication_date_dt.month == 8
    assert rep.sources == ["UN Children's Fund", "Government of India"]
    assert rep.format == "Situation Report"
    assert "Disaster Management" in rep.themes
    assert rep.primary_country == "India"
    assert rep.countries == ["India"]
    assert rep.disaster_names == ["India: Floods - Aug 2018"]
    assert rep.glide_numbers == ["FL-2018-000130-IND"]
    assert "all 14 districts" in rep.body_snippet
    assert rep.headline == "Critical Flood Response Underway"
    assert rep.is_verified_ground_truth is False
    assert "operational estimates" in rep.disclaimer


def test_parse_api_payload_empty_results():
    """Verify empty response payload handled without error."""
    payload = {"time": 5, "totalCount": 0, "count": 0, "data": []}
    response = ReliefWebQueryResponse.from_api_payload(payload)
    assert response.total_count == 0
    assert response.count == 0
    assert response.reports == []


def test_parse_api_payload_missing_optional_fields():
    """Verify resilience when fields like source, body, date are missing or null."""
    minimal_item = {
        "id": "2002",
        "fields": {
            "title": "Minimal Disaster Report",
            "url": "https://reliefweb.int/node/2002",
        },
    }
    payload = {"totalCount": 1, "count": 1, "data": [minimal_item]}
    response = ReliefWebQueryResponse.from_api_payload(payload)
    assert len(response.reports) == 1
    rep = response.reports[0]
    assert rep.report_id == "2002"
    assert rep.title == "Minimal Disaster Report"
    assert rep.publication_date is None
    assert rep.sources == []
    assert rep.format is None
    assert rep.body_snippet is None
    assert rep.countries == []


def test_parse_api_payload_malformed_json():
    """Verify parsing error raised on malformed raw JSON bytes."""
    client = ReliefWebClient()
    mock_resp = io.BytesIO(b"{ invalid json string here ")
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(ReliefWebParsingError) as exc_info:
            client.query_reports(query="Kerala")
        assert "Malformed JSON returned by ReliefWeb API" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 3. HTTP Execution & Query Construction Tests
# ------------------------------------------------------------------------------
def test_query_reports_success_mocked_http():
    """Verify query construction, POST payload, headers, and appname query parameter."""
    client = ReliefWebClient(
        config=ReliefWebConfig(appname="CustomApp-Test"),
        timeout=12,
    )

    mock_resp = io.BytesIO(json.dumps(SAMPLE_API_RESPONSE_PAYLOAD).encode("utf-8"))
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        response = client.query_reports(
            query="Kerala floods",
            country="India",
            from_date="2018-08-01",
            to_date="2018-08-31",
            formats=["Situation Report", "Assessment"],
            limit=5,
        )

        assert response.count == 1
        mock_urlopen.assert_called_once()
        called_req = mock_urlopen.call_args[0][0]

        # URL verification
        assert "appname=CustomApp-Test" in called_req.full_url
        assert called_req.headers["Content-type"] == "application/json"
        assert called_req.headers["User-agent"] == "DisasterIntelligencePipeline/1.0"

        # POST payload verification
        sent_payload = json.loads(called_req.data.decode("utf-8"))
        assert sent_payload["limit"] == 5
        assert sent_payload["query"]["value"] == "Kerala floods"

        filter_obj = sent_payload["filter"]
        assert filter_obj["operator"] == "AND"
        conds = filter_obj["conditions"]
        assert any(c.get("field") == "country" and c.get("value") == "India" for c in conds)
        assert any(c.get("field") == "date.created" for c in conds)
        assert any(c.get("field") == "format.name" for c in conds)


def test_query_reports_http_error_403_appname():
    """Verify HTTP 403 Forbidden produces clear appname pre-approval error."""
    client = ReliefWebClient()
    http_error = urllib.error.HTTPError(
        url="https://api.reliefweb.int/v2/reports?appname=demo",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=io.BytesIO(b'{"status":403,"error":{"message":"You are not using an approved appname."}}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(ReliefWebHTTPError) as exc_info:
            client.query_reports(query="Kerala")
        assert exc_info.value.status_code == 403
        assert "Approved appname required" in str(exc_info.value)
        assert "RELIEFWEB_APPNAME" in str(exc_info.value)


def test_query_reports_http_error_400():
    """Verify HTTP 400 Bad Request raises ReliefWebInvalidParameterError."""
    client = ReliefWebClient()
    http_error = urllib.error.HTTPError(
        url="https://mock.url",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(b'{"error": "Invalid date range"}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(ReliefWebInvalidParameterError) as exc_info:
            client.query_reports(query="test")
        assert "HTTP 400 Bad Request" in str(exc_info.value)


def test_query_reports_http_error_500():
    """Verify HTTP 500 Server Error raises ReliefWebHTTPError with status_code."""
    client = ReliefWebClient()
    http_error = urllib.error.HTTPError(
        url="https://mock.url",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=io.BytesIO(b"Backend Service Failure"),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(ReliefWebHTTPError) as exc_info:
            client.query_reports(query="test")
        assert exc_info.value.status_code == 500
        assert "HTTP 500" in str(exc_info.value)


def test_query_reports_timeout_error():
    """Verify socket timeout raises ReliefWebTimeoutError."""
    client = ReliefWebClient(timeout=8)
    with patch("urllib.request.urlopen", side_effect=socket.timeout("Timed out")):
        with pytest.raises(ReliefWebTimeoutError) as exc_info:
            client.query_reports(query="test")
        assert "timed out after 8s" in str(exc_info.value)


def test_query_reports_network_error():
    """Verify network connection or DNS failure raises ReliefWebNetworkError."""
    client = ReliefWebClient()
    url_err = urllib.error.URLError("DNS resolution failed")
    with patch("urllib.request.urlopen", side_effect=url_err):
        with pytest.raises(ReliefWebNetworkError) as exc_info:
            client.query_reports(query="test")
        assert "Failed to connect to ReliefWeb API" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 4. Detail Query by ID Tests
# ------------------------------------------------------------------------------
def test_get_report_by_id_success():
    """Verify report retrieval by ID."""
    client = ReliefWebClient()
    mock_resp = io.BytesIO(json.dumps(SAMPLE_API_RESPONSE_PAYLOAD).encode("utf-8"))
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        rep = client.get_report_by_id("1001")
        assert rep is not None
        assert rep.report_id == "1001"
        assert rep.title == "India: Kerala Floods - Situation Report No. 1"


def test_get_report_by_id_not_found():
    """Verify HTTP 404 returns None."""
    client = ReliefWebClient()
    http_error = urllib.error.HTTPError(
        url="https://mock.url/1001",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=io.BytesIO(b"Report not found"),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        rep = client.get_report_by_id("9999999")
        assert rep is None


def test_get_report_by_id_empty_id_raises():
    """Verify empty report ID raises ReliefWebInvalidParameterError."""
    client = ReliefWebClient()
    with pytest.raises(ReliefWebInvalidParameterError):
        client.get_report_by_id("   ")


# ------------------------------------------------------------------------------
# 5. Parameter Validation Tests
# ------------------------------------------------------------------------------
def test_parameter_validation_limits():
    """Verify parameter bounds enforcement for limit and offset."""
    client = ReliefWebClient()
    with pytest.raises(ReliefWebInvalidParameterError) as exc:
        client.query_reports(limit=0)
    assert "limit (0) must be between 1 and 1000" in str(exc.value)

    with pytest.raises(ReliefWebInvalidParameterError) as exc:
        client.query_reports(limit=1001)
    assert "limit (1001) must be between 1 and 1000" in str(exc.value)

    with pytest.raises(ReliefWebInvalidParameterError) as exc:
        client.query_reports(offset=-1)
    assert "offset (-1) cannot be negative" in str(exc.value)


def test_date_formatting_and_iso_timestamps():
    """Verify _format_date handles datetime, date, string with appropriate UTC timestamps."""
    client = ReliefWebClient()
    dt = datetime(2018, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert client._format_date(dt) == "2018-08-15T12:00:00+00:00"

    d = date(2018, 8, 15)
    assert client._format_date(d, is_end=False) == "2018-08-15T00:00:00+00:00"
    assert client._format_date(d, is_end=True) == "2018-08-15T23:59:59+00:00"

    s = "2018-08-15"
    assert client._format_date(s, is_end=False) == "2018-08-15T00:00:00+00:00"
    assert client._format_date(s, is_end=True) == "2018-08-15T23:59:59+00:00"

    with pytest.raises(ReliefWebInvalidParameterError):
        client._format_date("   ")


# ------------------------------------------------------------------------------
# 6. Display Formatting & Sample Dataset Tests
# ------------------------------------------------------------------------------
def test_format_reports_for_display():
    """Verify terminal formatting displays publication date distinction and disclaimer."""
    response = ReliefWebQueryResponse.from_api_payload(SAMPLE_API_RESPONSE_PAYLOAD)
    text = ReliefWebClient.format_reports_for_display(response)

    assert "RELIEFWEB HUMANITARIAN SITUATION REPORTS" in text
    assert "Total Reports Matching: 1"
    assert "Report Publication Date, NOT Incident Date" in text
    assert "[Humanitarian Field Estimate - NOT Verified Ground Truth]" in text
    assert "CAVEAT: Figures in situation reports represent operational agency estimates" in text


def test_sample_kerala_floods_payload():
    """Verify built-in authentic Kerala Floods August 2018 sample dataset."""
    response = ReliefWebQueryResponse.from_api_payload(SAMPLE_KERALA_FLOODS_PAYLOAD)
    assert response.total_count == 3
    assert response.count == 3
    assert len(response.reports) == 3

    unicef_rep = response.reports[0]
    assert "Floods in Kerala" in unicef_rep.title
    assert "UN Children's Fund" in unicef_rep.sources
    assert unicef_rep.format == "Situation Report"
    assert "FL-2018-000130-IND" in unicef_rep.glide_numbers

    ifrc_rep = response.reports[1]
    assert "Emergency Plan of Action" in ifrc_rep.title
    assert "International Federation of Red Cross And Red Crescent Societies" in ifrc_rep.sources

    pdna_rep = response.reports[2]
    assert "Post Disaster Needs Assessment" in pdna_rep.title
    assert "Government of Kerala" in pdna_rep.sources
