"""
Unit tests for the Unified Disaster Intelligence Pipeline Orchestrator.
Covers:
  - Incident date window derivation
  - Subsystem source routing (earthquake vs flood vs wildfire)
  - Conservative cross-source incident matching (accepting matching location, rejecting peripheral events)
  - Multi-source aggregation and primary coordinate resolution
  - Resilient partial-failure handling (Tavily failure, USGS failure, GDACS failure)
  - All sources failure handling
  - Empty results handling
  - Human-readable display report formatting
  - JSON serialization
"""

from datetime import datetime, timezone
import json
from unittest.mock import MagicMock, patch
import pytest

from src.clients.firms_client import (
    FIRMSClient,
    FIRMSHTTPError,
    FIRMSTimeoutError,
)
from src.clients.gdacs_client import (
    GDACSClient,
    GDACSHTTPError,
    GDACSTimeoutError,
)
from src.clients.reliefweb_client import (
    ReliefWebClient,
    ReliefWebHTTPError,
    ReliefWebTimeoutError,
)
from src.clients.usgs_client import (
    USGSClient,
    USGSHTTPError,
    USGSTimeoutError,
)
from src.config import FIRMSConfig
from src.models import (
    ActiveFireDetection,
    ClaimEvidence,
    EarthquakeEvent,
    EarthquakeQueryResponse,
    FIRMSQueryResponse,
    GDACSEvent,
    GDACSQueryResponse,
    ReliefWebReport,
    ReliefWebQueryResponse,
    SearchResult,
    UnifiedFIRMSData,
    UnifiedIncidentReport,
    UnifiedReliefWebData,
)
from src.pipeline import DisasterPipeline, matches_location
from src.query_parser import (
    DisasterQueryInfo,
    derive_incident_date_range,
    parse_disaster_query,
)
from src.tavily_client import NetworkOrAPIError, TavilySearchService


# ------------------------------------------------------------------------------
# Fixtures and Sample Mock Records
# ------------------------------------------------------------------------------
SAMPLE_USGS_TURKEY_EVENT = EarthquakeEvent(
    event_id="us6000jllz",
    magnitude=7.8,
    magnitude_type="mww",
    place="26 km E of Nurdağı, Turkey",
    origin_time=datetime(2023, 2, 6, 1, 17, 34, tzinfo=timezone.utc),
    origin_time_str="2023-02-06T01:17:34+00:00",
    longitude=37.0143,
    latitude=37.2256,
    depth_km=10.0,
    url="https://earthquake.usgs.gov/earthquakes/eventpage/us6000jllz",
    alert_level="red",
    felt_reports=3182,
)

SAMPLE_USGS_ALASKA_EVENT = EarthquakeEvent(
    event_id="ak0231abc",
    magnitude=5.1,
    magnitude_type="ml",
    place="85 km S of Fox Islands, Alaska",
    origin_time=datetime(2023, 2, 6, 4, 12, 0, tzinfo=timezone.utc),
    origin_time_str="2023-02-06T04:12:00+00:00",
    longitude=-168.12,
    latitude=52.45,
    depth_km=25.0,
    url="https://earthquake.usgs.gov/earthquakes/eventpage/ak0231abc",
    alert_level="green",
)

SAMPLE_GDACS_TURKEY_ALERT = GDACSEvent(
    event_id="1357372",
    episode_id="1",
    event_type="EQ",
    event_type_name="Earthquake",
    name="Earthquake in Türkiye",
    country="Türkiye",
    iso3="TUR",
    alert_level="Red",
    alert_score=3.0,
    from_date_str="2023-02-06T01:17:35+00:00",
    to_date_str="2023-02-06T01:17:35+00:00",
    longitude=37.032,
    latitude=37.1736,
    severity=7.8,
    severity_text="Magnitude 7.8M, Depth:17.925km",
    glide="EQ-2023-000015-TUR",
    report_url="https://www.gdacs.org/report.aspx?eventid=1357372&episodeid=1&eventtype=EQ",
)

SAMPLE_GDACS_NZ_ALERT = GDACSEvent(
    event_id="1357999",
    episode_id="1",
    event_type="EQ",
    event_type_name="Earthquake",
    name="Earthquake in New Zealand",
    country="New Zealand",
    iso3="NZL",
    alert_level="Green",
    alert_score=1.0,
    from_date_str="2023-02-06T08:00:00+00:00",
    longitude=174.5,
    latitude=-41.2,
    severity=4.9,
)

SAMPLE_GDACS_KERALA_ALERT = GDACSEvent(
    event_id="1000212",
    episode_id="2",
    event_type="FL",
    event_type_name="Flood",
    name="Flood in India",
    country="India",
    iso3="IND",
    alert_level="Orange",
    alert_score=2.0,
    from_date_str="2018-08-10T00:00:00+00:00",
    to_date_str="2018-09-24T00:00:00+00:00",
    longitude=76.403,
    latitude=9.919,
    glide="2018-000134",
    report_url="https://www.gdacs.org/report.aspx?eventid=1000212&episodeid=2&eventtype=FL",
    affected_countries=[{"countryname": "India", "iso3": "IND"}],
)

SAMPLE_GDACS_NIGERIA_ALERT = GDACSEvent(
    event_id="1000213",
    episode_id="3",
    event_type="FL",
    event_type_name="Flood",
    name="Flood in Nigeria",
    country="Nigeria",
    iso3="NGA",
    alert_level="Orange",
    alert_score=2.0,
    from_date_str="2018-08-31T00:00:00+00:00",
    longitude=8.151,
    latitude=8.469,
    glide="2018-000120",
    report_url="https://www.gdacs.org/report.aspx?eventid=1000213&episodeid=3&eventtype=FL",
    affected_countries=[{"countryname": "Nigeria", "iso3": "NGA"}],
)

SAMPLE_TAVILY_ARTICLE = SearchResult(
    title="Deadly Turkey-Syria Earthquake Kills Thousands",
    url="https://www.reuters.com/world/middle-east/turkey-quake-2023",
    content="A catastrophic magnitude 7.8 earthquake struck southern Turkey and northern Syria early on Monday.",
    score=0.98,
    published_date="2023-02-06",
    domain="reuters.com",
    source_credibility="established_news",
    temporal_category="contemporaneous",
)

SAMPLE_RELIEFWEB_KERALA_REPORT = ReliefWebReport(
    report_id="2754629",
    title="India: Floods in Kerala - Situation Report No. 1",
    url="https://reliefweb.int/report/india/india-floods-kerala-sitrep-1",
    publication_date="2018-08-19T00:00:00+00:00",
    publication_date_dt=datetime(2018, 8, 19, 0, 0, 0, tzinfo=timezone.utc),
    sources=["UN Children's Fund", "Government of India"],
    format="Situation Report",
    primary_country="India",
    countries=["India"],
    disaster_names=["India: Floods - Aug 2018"],
    glide_numbers=["FL-2018-000130-IND"],
    body_snippet="Severe monsoon rainfall in Kerala has led to unprecedented flooding across all 14 districts.",
)

SAMPLE_RELIEFWEB_NIGERIA_REPORT = ReliefWebReport(
    report_id="2754999",
    title="Nigeria: Flood Emergency Situation Report No. 2",
    url="https://reliefweb.int/report/nigeria/nigeria-flood-emergency-sitrep-2",
    publication_date="2018-08-20T00:00:00+00:00",
    publication_date_dt=datetime(2018, 8, 20, 0, 0, 0, tzinfo=timezone.utc),
    sources=["UN OCHA"],
    format="Situation Report",
    primary_country="Nigeria",
    countries=["Nigeria"],
    disaster_names=["Nigeria: Floods - Aug 2018"],
    body_snippet="Flooding across central Nigeria states.",
)


SAMPLE_FIRMS_CALIFORNIA_DETECTION = ActiveFireDetection(
    latitude=38.5421,
    longitude=-121.8492,
    acq_date="2020-08-18",
    acq_time="09:30 UTC",
    satellite="Suomi NPP",
    instrument="VIIRS",
    confidence="nominal",
    brightness=342.5,
    bright_t31=298.1,
    frp=24.8,
    daynight="N",
)


@pytest.fixture(autouse=True)
def mock_default_reliefweb(monkeypatch):
    """Ensure ReliefWeb is mocked by default across pipeline unit tests to prevent network calls."""
    mock_resp = ReliefWebQueryResponse(count=0, total_count=0, reports=[])
    monkeypatch.setattr(ReliefWebClient, "query_reports", MagicMock(return_value=mock_resp))


@pytest.fixture(autouse=True)
def mock_default_firms(monkeypatch):
    """Ensure NASA FIRMS is mocked by default across pipeline unit tests to prevent network calls."""
    mock_resp = FIRMSQueryResponse(count=0, total_count=0, detections=[], source_name="VIIRS_SNPP_NRT", area_or_country="N/A")
    monkeypatch.setattr(FIRMSClient, "query_area", MagicMock(return_value=mock_resp))
    monkeypatch.setattr(FIRMSClient, "query_country", MagicMock(return_value=mock_resp))


# ------------------------------------------------------------------------------
# 1. Date Range Derivation Tests
# ------------------------------------------------------------------------------
def test_derive_incident_date_range_exact_day():
    info = parse_disaster_query("Turkey earthquake on February 6, 2023")
    start, end = derive_incident_date_range(info)
    assert start == "2023-02-06"
    assert end == "2023-02-08"


def test_derive_incident_date_range_month_year():
    info = parse_disaster_query("Kerala floods in August 2018")
    start, end = derive_incident_date_range(info)
    assert start == "2018-08-01"
    assert end == "2018-08-31"


def test_derive_incident_date_range_year_only():
    info = parse_disaster_query("Nepal earthquake 2015")
    start, end = derive_incident_date_range(info)
    assert start == "2015-01-01"
    assert end == "2015-12-31"


def test_derive_incident_date_range_no_date():
    info = parse_disaster_query("California wildfires")
    start, end = derive_incident_date_range(info)
    assert start is None
    assert end is None


# ------------------------------------------------------------------------------
# 2. Location Matching Helper Tests
# ------------------------------------------------------------------------------
def test_matches_location_exact_and_aliases():
    assert matches_location("Turkey", ["26 km E of Nurdağı, Turkey"])
    assert matches_location("Turkey", ["Earthquake in Türkiye", "TUR"])
    assert matches_location("Kerala", ["Flood in India", "IND"])
    assert not matches_location("Kerala", ["Flood in Nigeria", "NGA"])
    assert not matches_location("Turkey", ["Earthquake in New Zealand", "NZL"])
    assert not matches_location(None, ["Any text"])
    assert not matches_location("", ["Any text"])


# ------------------------------------------------------------------------------
# 3. Source Selection & Routing Tests
# ------------------------------------------------------------------------------
def test_source_routing_earthquake():
    """Earthquake query must route to Tavily, USGS, and GDACS."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer="Overview")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(count=1, events=[SAMPLE_USGS_TURKEY_EVENT])
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_TURKEY_ALERT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake on February 6, 2023")

    assert "USGS Earthquake Catalog" in report.sources_queried
    assert "GDACS Disaster Alerts" in report.sources_queried
    assert "Tavily Web Intelligence" in report.sources_queried
    assert mock_usgs.query_earthquakes.called
    assert mock_gdacs.query_events.called
    assert mock_tavily.search.called


def test_source_routing_floods():
    """Floods query must route to Tavily and GDACS, skipping USGS."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer=None)
    mock_usgs = MagicMock()
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_KERALA_ALERT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Kerala floods in August 2018")

    assert "USGS Earthquake Catalog" not in report.sources_queried
    assert not mock_usgs.query_earthquakes.called
    assert "GDACS Disaster Alerts" in report.sources_queried
    assert mock_gdacs.query_events.called
    assert report.usgs.status == "not_applicable"


def test_source_routing_wildfire():
    """Wildfire query must route to Tavily and GDACS (WF), skipping USGS."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=0, events=[])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("California wildfires August 2020")

    assert not mock_usgs.query_earthquakes.called
    assert mock_gdacs.query_events.called
    called_type = mock_gdacs.query_events.call_args[1].get("event_types")
    assert called_type == "WF"
    assert report.usgs.status == "not_applicable"


# ------------------------------------------------------------------------------
# 4. Conservative Cross-Source Matching Tests
# ------------------------------------------------------------------------------
def test_conservative_matching_seismic_filters_peripheral_events():
    """Verify that an earthquake in Alaska is not matched to a Turkey query."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    # USGS returns both Turkey and Alaska events in the time window
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(
        count=2,
        events=[SAMPLE_USGS_TURKEY_EVENT, SAMPLE_USGS_ALASKA_EVENT],
    )
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=0, events=[])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake on February 6, 2023")

    assert len(report.usgs.matched_events) == 1
    assert report.usgs.matched_events[0].event_id == "us6000jllz"  # Turkey matched
    assert report.usgs.unmatched_events_count == 1  # Alaska excluded
    assert report.primary_coordinates is not None
    assert report.primary_coordinates.latitude == 37.2256
    assert report.primary_coordinates.longitude == 37.0143


def test_conservative_matching_gdacs_filters_unrelated_alerts():
    """Verify that a flood in Nigeria is not matched to a Kerala (India) query."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_gdacs = MagicMock()
    # GDACS returns Flood in India and Flood in Nigeria
    mock_gdacs.query_events.return_value = GDACSQueryResponse(
        count=2,
        events=[SAMPLE_GDACS_KERALA_ALERT, SAMPLE_GDACS_NIGERIA_ALERT],
    )

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Kerala floods in August 2018")

    assert len(report.gdacs.matched_events) == 1
    assert report.gdacs.matched_events[0].event_id == "1000212"  # India matched
    assert report.gdacs.unmatched_events_count == 1  # Nigeria excluded
    assert report.primary_coordinates is not None
    assert report.primary_coordinates.latitude == 9.919


def test_conservative_matching_no_location_match_does_not_claim_event():
    """If no returned events match the queried location, matched_events must be empty."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(
        count=1,
        events=[SAMPLE_USGS_ALASKA_EVENT],
    )
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(
        count=1,
        events=[SAMPLE_GDACS_NZ_ALERT],
    )

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Chile earthquake on February 6, 2023")

    assert report.usgs.status == "no_matching_events"
    assert len(report.usgs.matched_events) == 0
    assert report.usgs.unmatched_events_count == 1

    assert report.gdacs.status == "no_matching_events"
    assert len(report.gdacs.matched_events) == 0
    assert report.gdacs.unmatched_events_count == 1
    assert report.primary_coordinates is None


def test_cross_source_divergent_locations_not_cross_matched():
    """
    Verify that an alert from one source (GDACS NZ alert) sharing the same date
    as another source (USGS Turkey event) is NOT incorrectly cross-matched to the query.
    """
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer="Overview")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(
        count=1,
        events=[SAMPLE_USGS_TURKEY_EVENT],
    )
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(
        count=1,
        events=[SAMPLE_GDACS_NZ_ALERT],  # Same day, different country
    )

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake on February 6, 2023")

    # USGS matched Turkey
    assert len(report.usgs.matched_events) == 1
    assert report.usgs.matched_events[0].event_id == "us6000jllz"

    # GDACS rejected New Zealand even though date matched
    assert report.gdacs.status == "no_matching_events"
    assert len(report.gdacs.matched_events) == 0
    assert report.gdacs.unmatched_events_count == 1

    # Primary coordinates originate from USGS Turkey, NOT GDACS NZ
    assert report.primary_coordinates is not None
    assert report.primary_coordinates.latitude == 37.2256
    assert "USGS" in report.primary_coordinates.source


# ------------------------------------------------------------------------------
# 5. Resilient Partial Failure Tests
# ------------------------------------------------------------------------------
def test_partial_failure_tavily_error_does_not_break_usgs_and_gdacs():
    """When Tavily throws a network error, USGS and GDACS must still succeed."""
    mock_tavily = MagicMock()
    mock_tavily.search.side_effect = NetworkOrAPIError("Connection refused by Tavily")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(count=1, events=[SAMPLE_USGS_TURKEY_EVENT])
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_TURKEY_ALERT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake February 6, 2023")

    assert "Tavily Web Intelligence" in report.sources_failed
    assert "USGS Earthquake Catalog" in report.sources_succeeded
    assert "GDACS Disaster Alerts" in report.sources_succeeded
    assert len(report.usgs.matched_events) == 1
    assert len(report.gdacs.matched_events) == 1
    assert report.tavily.status == "failed"


def test_partial_failure_usgs_timeout_does_not_break_tavily_and_gdacs():
    """When USGS times out, Tavily and GDACS must still succeed."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer="Summary")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.side_effect = USGSTimeoutError("USGS request timed out")
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_TURKEY_ALERT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake February 6, 2023")

    assert "USGS Earthquake Catalog" in report.sources_failed
    assert report.usgs.status == "failed"
    assert "GDACS Disaster Alerts" in report.sources_succeeded
    assert "Tavily Web Intelligence" in report.sources_succeeded
    assert len(report.gdacs.matched_events) == 1


def test_partial_failure_gdacs_error_does_not_break_usgs_and_tavily():
    """When GDACS returns HTTP 500, USGS and Tavily must still succeed."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer="Summary")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(count=1, events=[SAMPLE_USGS_TURKEY_EVENT])
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.side_effect = GDACSHTTPError("Internal Server Error", status_code=500)

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake February 6, 2023")

    assert "GDACS Disaster Alerts" in report.sources_failed
    assert report.gdacs.status == "failed"
    assert "USGS Earthquake Catalog" in report.sources_succeeded
    assert "Tavily Web Intelligence" in report.sources_succeeded


def test_all_sources_fail_gracefully():
    """When all sources fail, the pipeline returns a report with all failures tracked."""
    mock_tavily = MagicMock()
    mock_tavily.search.side_effect = NetworkOrAPIError("Tavily down")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.side_effect = USGSTimeoutError("USGS timeout")
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.side_effect = GDACSHTTPError("GDACS down", status_code=503)
    mock_reliefweb = MagicMock()
    mock_reliefweb.query_reports.side_effect = ReliefWebHTTPError("ReliefWeb down", status_code=503)

    pipeline = DisasterPipeline(
        tavily_service=mock_tavily,
        usgs_client=mock_usgs,
        gdacs_client=mock_gdacs,
        reliefweb_client=mock_reliefweb,
    )
    report = pipeline.process_query("Turkey earthquake February 6, 2023")

    assert len(report.sources_failed) == 4
    assert len(report.sources_succeeded) == 0
    assert report.usgs.status == "failed"
    assert report.gdacs.status == "failed"
    assert report.reliefweb.status == "failed"
    assert report.tavily.status == "failed"
    assert report.primary_coordinates is None


# ------------------------------------------------------------------------------
# 6. Display Formatting & Serialization Tests
# ------------------------------------------------------------------------------
def test_format_unified_report_for_display():
    """Verify human-readable output formatting contains all required sections."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer="Overview")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(count=1, events=[SAMPLE_USGS_TURKEY_EVENT])
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_TURKEY_ALERT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake on February 6, 2023")

    formatted = DisasterPipeline.format_unified_report_for_display(report)
    assert "UNIFIED DISASTER INTELLIGENCE PIPELINE REPORT" in formatted
    assert "Turkey earthquake on February 6, 2023" in formatted
    assert "USGS EARTHQUAKE CATALOG" in formatted
    assert "M 7.8 (mww) - 26 km E of Nurdağı, Turkey" in formatted
    assert "GDACS DISASTER ALERTS" in formatted
    assert "[RED ALERT] Earthquake in Türkiye" in formatted
    assert "EQ-2023-000015-TUR" in formatted
    assert "TAVILY WEB INTELLIGENCE" in formatted
    assert "FACTUAL SOURCE ATTRIBUTIONS" in formatted
    assert "DATA BOUNDARIES & UNAVAILABLE FIELDS" in formatted
    assert "Casualty counts and operational updates originate from journalistic media reports" in formatted


def test_unified_report_json_serialization():
    """Verify that UnifiedIncidentReport serializes cleanly to valid JSON."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer="Overview")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(count=1, events=[SAMPLE_USGS_TURKEY_EVENT])
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_TURKEY_ALERT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Turkey earthquake on February 6, 2023")

    json_str = report.model_dump_json(indent=2)
    parsed = json.loads(json_str)

    assert parsed["original_query"] == "Turkey earthquake on February 6, 2023"
    assert parsed["disaster_type"] == "earthquake"
    assert parsed["location"] == "Turkey"
    assert parsed["primary_coordinates"]["latitude"] == 37.2256
    assert parsed["usgs"]["matched_events"][0]["magnitude"] == 7.8
    assert parsed["gdacs"]["matched_events"][0]["glide"] == "EQ-2023-000015-TUR"
    assert "unavailable_fields" in parsed


def test_empty_results_across_all_sources():
    """Verify handling when all queried sources return zero results."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(count=0, events=[])
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=0, events=[])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Unknown event in Atlantis 2099")

    assert report.gdacs.status == "no_matching_events"
    assert report.tavily.status == "empty_results"
    assert report.primary_coordinates is None

    formatted = DisasterPipeline.format_unified_report_for_display(report)
    assert "No web intelligence articles retrieved" in formatted


def test_gdacs_centroid_labeling_and_footprint_disclaimer():
    """Verify GDACS centroid is labeled as point estimate, NOT verified boundary/footprint."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_KERALA_ALERT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Kerala floods in August 2018")

    assert report.primary_coordinates is not None
    assert report.primary_coordinates.coordinate_type == "centroid"
    assert report.primary_coordinates.coordinate_label == "GDACS Event Centroid"

    formatted = DisasterPipeline.format_unified_report_for_display(report)
    assert "GDACS Event Centroid   : Lat 9.9190, Lon 76.4030 (Point Estimate)" in formatted
    assert "Verified Coordinates" not in formatted
    assert "Point centroid does NOT represent the spatial disaster boundary or inundation extent" in formatted


def test_gdacs_unmatched_alerts_diagnostics_preserved():
    """Verify that unrelated alerts (e.g. Nigeria flood) are rejected with explicit diagnostics."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_gdacs = MagicMock()
    # Query returns both Kerala flood and Nigeria flood
    mock_gdacs.query_events.return_value = GDACSQueryResponse(
        count=2,
        events=[SAMPLE_GDACS_KERALA_ALERT, SAMPLE_GDACS_NIGERIA_ALERT],
    )

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Kerala floods in August 2018")

    assert len(report.gdacs.matched_events) == 1
    assert report.gdacs.matched_events[0].event_id == "1000212"  # Kerala
    assert report.gdacs.unmatched_events_count == 1
    assert len(report.gdacs.unmatched_diagnostics) == 1
    assert "Flood in Nigeria" in report.gdacs.unmatched_diagnostics[0]
    assert "Nigeria" in report.gdacs.unmatched_diagnostics[0]

    formatted = DisasterPipeline.format_unified_report_for_display(report)
    assert "Excluded Unmatched Alerts (1):" in formatted
    assert "Flood in Nigeria" in formatted


def test_subnational_query_rejects_divergent_coordinates_in_parent_country():
    """
    If a GDACS alert has parent country 'India' but its coordinates are in Assam (Lat 26.2, Lon 92.9),
    it must be rejected for a 'Kerala' query because it is outside Kerala regional bounds.
    """
    assam_alert = GDACSEvent(
        event_id="1000999",
        episode_id="1",
        event_type="FL",
        event_type_name="Flood",
        name="Flood in India",
        country="India",
        iso3="IND",
        alert_level="Orange",
        alert_score=2.0,
        from_date_str="2018-08-10T00:00:00+00:00",
        longitude=92.900,  # Assam coordinates
        latitude=26.200,   # Assam coordinates
    )

    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[assam_alert])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs, gdacs_client=mock_gdacs)
    report = pipeline.process_query("Kerala floods in August 2018")

    assert len(report.gdacs.matched_events) == 0
    assert report.gdacs.status == "no_matching_events"
    assert report.gdacs.unmatched_events_count == 1
    assert any("outside regional bounds for 'Kerala'" in d for d in report.gdacs.unmatched_diagnostics)


def test_reliefweb_integration_success_and_matching():
    """Verify ReliefWeb situation reports matching target location are parsed and retained."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], answer=None)
    mock_usgs = MagicMock()
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=0, events=[])
    mock_reliefweb = MagicMock()
    mock_reliefweb.query_reports.return_value = ReliefWebQueryResponse(
        total_count=2,
        count=2,
        reports=[SAMPLE_RELIEFWEB_KERALA_REPORT, SAMPLE_RELIEFWEB_NIGERIA_REPORT],
    )

    pipeline = DisasterPipeline(
        tavily_service=mock_tavily,
        usgs_client=mock_usgs,
        gdacs_client=mock_gdacs,
        reliefweb_client=mock_reliefweb,
    )
    report = pipeline.process_query("Kerala floods August 2018")

    assert report.reliefweb.status == "success"
    assert len(report.reliefweb.matched_reports) == 1
    matched = report.reliefweb.matched_reports[0]
    assert matched.report_id == "2754629"
    assert matched.temporal_relation == "contemporaneous"
    assert report.reliefweb.unmatched_reports_count == 1
    assert any("Nigeria" in d for d in report.reliefweb.unmatched_diagnostics)
    assert "ReliefWeb Humanitarian Reports" in report.sources_succeeded


def test_reliefweb_partial_failure_does_not_break_other_sources():
    """When ReliefWeb returns HTTP 403 (unapproved appname), other sources still succeed."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], answer="Overview")
    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(count=1, events=[SAMPLE_USGS_TURKEY_EVENT])
    mock_gdacs = MagicMock()
    mock_gdacs.query_events.return_value = GDACSQueryResponse(count=1, events=[SAMPLE_GDACS_TURKEY_ALERT])
    mock_reliefweb = MagicMock()
    mock_reliefweb.query_reports.side_effect = ReliefWebHTTPError("Approved appname required", status_code=403)

    pipeline = DisasterPipeline(
        tavily_service=mock_tavily,
        usgs_client=mock_usgs,
        gdacs_client=mock_gdacs,
        reliefweb_client=mock_reliefweb,
    )
    report = pipeline.process_query("Turkey earthquake on February 6, 2023")

    assert report.reliefweb.status == "failed"
    assert "ReliefWeb Humanitarian Reports" in report.sources_failed
    assert "USGS Earthquake Catalog" in report.sources_succeeded
    assert "GDACS Disaster Alerts" in report.sources_succeeded
    assert "Tavily Web Intelligence" in report.sources_succeeded
    assert report.primary_coordinates is not None


def test_format_display_includes_reliefweb_section():
    """Verify that formatted terminal output includes the ReliefWeb section and caveat."""
    report = UnifiedIncidentReport(
        original_query="Kerala floods August 2018",
        disaster_type="floods",
        location="Kerala",
        incident_date_str="August 2018",
        reliefweb=UnifiedReliefWebData(
            queried=True,
            status="success",
            matched_reports=[SAMPLE_RELIEFWEB_KERALA_REPORT],
            total_reports_found=1,
        ),
    )

    output = DisasterPipeline.format_unified_report_for_display(report)
    assert "3. RELIEFWEB HUMANITARIAN SITUATION REPORTS" in output
    assert "Report Publication Date, NOT Incident Date" in output
    assert "[Reported Humanitarian Estimate - NOT Verified Ground Truth]" in output
    assert "UN Children's Fund" in output


# ------------------------------------------------------------------------------
# 8. NASA FIRMS Integration Tests
# ------------------------------------------------------------------------------
def test_wildfire_routing_to_firms_success_and_matching(monkeypatch):
    """Verify that wildfire queries route to NASA FIRMS, resolve coordinates, and add attributions."""
    mock_firms_resp = FIRMSQueryResponse(
        total_count=1,
        count=1,
        detections=[SAMPLE_FIRMS_CALIFORNIA_DETECTION],
        source_name="VIIRS_SNPP_NRT",
        area_or_country="-124.5000,32.5000,-114.0000,42.0000",
        api_url="https://firms.modaps.eosdis.nasa.gov/api/area/...",
    )

    mock_firms_client = MagicMock(spec=FIRMSClient)
    mock_firms_client.config = FIRMSConfig(map_key="validkey123456789012345678901234")
    mock_firms_client.query_area.return_value = mock_firms_resp

    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], verification_report=None)

    pipeline = DisasterPipeline(
        tavily_service=mock_tavily,
        firms_client=mock_firms_client,
    )

    report = pipeline.process_query(
        "California wildfires August 2020",
        enable_usgs=True,
        enable_gdacs=False,
        enable_reliefweb=False,
        enable_firms=True,
    )

    # Routing
    assert "NASA FIRMS Active Fire" in report.sources_queried
    assert "NASA FIRMS Active Fire" in report.sources_succeeded
    assert report.firms.queried is True
    assert report.firms.status == "success"
    assert len(report.firms.matched_detections) == 1

    # Coordinate resolution to thermal hotspot
    assert report.primary_coordinates is not None
    assert report.primary_coordinates.coordinate_label == "NASA FIRMS Thermal Hotspot"
    assert report.primary_coordinates.coordinate_type == "thermal_hotspot"
    assert report.primary_coordinates.latitude == pytest.approx(38.5421)
    assert report.primary_coordinates.longitude == pytest.approx(-121.8492)
    assert "does not define wildfire perimeter" in report.primary_coordinates.disclaimer

    # Source attribution and limitations
    assert "active_fire_thermal_detections" in report.source_attributions
    assert "NASA FIRMS" in report.source_attributions["active_fire_thermal_detections"]
    assert any("thermal anomalies" in lim.lower() for lim in report.data_limitations)


def test_non_wildfire_skips_firms():
    """Verify that non-fire queries (earthquake, flood) skip FIRMS with status 'not_applicable'."""
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[], verification_report=None)

    mock_usgs = MagicMock()
    mock_usgs.query_earthquakes.return_value = EarthquakeQueryResponse(events=[SAMPLE_USGS_TURKEY_EVENT])

    pipeline = DisasterPipeline(tavily_service=mock_tavily, usgs_client=mock_usgs)
    report = pipeline.process_query(
        "Turkey earthquake on February 6, 2023",
        enable_firms=True,
    )

    assert report.firms.queried is False
    assert report.firms.status == "not_applicable"
    assert "NASA FIRMS Active Fire" not in report.sources_queried


def test_firms_unconfigured_fails_gracefully_without_breaking_other_sources():
    """Verify that unconfigured FIRMS MAP_KEY produces status 'unconfigured' without crashing pipeline."""
    mock_firms_client = MagicMock(spec=FIRMSClient)
    # Simulate unconfigured FIRMSConfig
    mock_firms_client.config = FIRMSConfig(map_key="")

    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], verification_report=None)

    pipeline = DisasterPipeline(tavily_service=mock_tavily, firms_client=mock_firms_client)
    report = pipeline.process_query(
        "California wildfires August 2020",
        enable_firms=True,
        enable_tavily=True,
    )

    assert "NASA FIRMS Active Fire" in report.sources_queried
    assert "NASA FIRMS Active Fire" in report.sources_failed
    assert report.firms.queried is True
    assert report.firms.status == "unconfigured"
    assert "MAP_KEY is not configured" in report.firms.error_message
    # Other sources should succeed
    assert "Tavily Web Intelligence" in report.sources_succeeded


def test_firms_partial_failure_does_not_break_other_sources():
    """Verify that FIRMS HTTP or timeout errors are handled as graceful partial failures."""
    mock_firms_client = MagicMock(spec=FIRMSClient)
    mock_firms_client.config = FIRMSConfig(map_key="validkey123456789012345678901234")
    mock_firms_client.query_area.side_effect = FIRMSHTTPError("NASA FIRMS 400 Bad Request: Invalid MAP_KEY", status_code=400)

    mock_tavily = MagicMock()
    mock_tavily.search.return_value = MagicMock(results=[SAMPLE_TAVILY_ARTICLE], verification_report=None)

    pipeline = DisasterPipeline(tavily_service=mock_tavily, firms_client=mock_firms_client)
    report = pipeline.process_query(
        "California wildfires August 2020",
        enable_firms=True,
        enable_tavily=True,
    )

    assert report.firms.status == "failed"
    assert "NASA FIRMS Active Fire" in report.sources_failed
    assert "Tavily Web Intelligence" in report.sources_succeeded


def test_format_display_includes_firms_section():
    """Verify that formatted terminal output includes the NASA FIRMS section with thermal anomaly disclaimer."""
    report = UnifiedIncidentReport(
        original_query="California wildfires August 2020",
        disaster_type="wildfire",
        location="California",
        incident_date_str="August 2020",
        firms=UnifiedFIRMSData(
            queried=True,
            status="success",
            matched_detections=[SAMPLE_FIRMS_CALIFORNIA_DETECTION],
            total_detections_found=1,
            satellite_source="VIIRS_SNPP_NRT",
        ),
    )

    output = DisasterPipeline.format_unified_report_for_display(report)
    assert "4. NASA FIRMS ACTIVE FIRE / THERMAL ANOMALIES (MODIS / VIIRS)" in output
    assert "VIIRS_SNPP_NRT" in output
    assert "38.5421" in output
    assert "-121.8492" in output
    assert "NOMINAL" in output
    assert "342.5 K" in output
    assert "[Satellite Thermal Anomaly - NOT Confirmed Ground Wildfire]" in output
    assert "Scientific Notice:" in output
    assert "agricultural burning or industrial flaring" in output


