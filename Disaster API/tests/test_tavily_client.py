"""
Unit tests for TavilySearchService error handling, query validation, and formatting.
Uses unittest.mock to mock TavilyClient calls for isolated, zero-cost unit testing.
"""

from unittest.mock import MagicMock, patch
import pytest

from tavily import (
    BadRequestError,
    InvalidAPIKeyError,
    UsageLimitExceededError,
)

from src.config import TavilyConfig
from src.models import (
    CrossVerificationReport,
    DisasterEventMetadata,
    SearchResponse,
    SearchResult,
)
from src.tavily_client import (
    AuthenticationError,
    InvalidQueryError,
    MissingKeyError,
    NetworkOrAPIError,
    RateLimitError,
    TavilySearchService,
)


@pytest.fixture
def mock_service():
    """Provides a TavilySearchService with a mocked internal TavilyClient."""
    config = TavilyConfig(api_key="tvly-mock-valid-key-for-testing")
    with patch("src.tavily_client.TavilyClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance
        service = TavilySearchService(config=config)
        service._client = mock_instance
        yield service, mock_instance


def test_init_fails_without_key():
    config = TavilyConfig(api_key="")
    with pytest.raises(MissingKeyError) as exc_info:
        TavilySearchService(config=config)
    assert "missing" in str(exc_info.value).lower()


def test_init_fails_with_placeholder_key():
    config = TavilyConfig(api_key="tvly-your-api-key-here")
    with pytest.raises(MissingKeyError) as exc_info:
        TavilySearchService(config=config)
    assert "placeholder" in str(exc_info.value).lower()


def test_query_validation_empty_or_whitespace(mock_service):
    service, _ = mock_service
    with pytest.raises(InvalidQueryError):
        service.search("")
    with pytest.raises(InvalidQueryError):
        service.search("   ")
    with pytest.raises(InvalidQueryError):
        service.search("x")  # Too short


def test_search_mumbai_floods_july_2005_end_to_end(mock_service):
    """Scenario 1: Mumbai floods, July 2005 with contemporaneous and retrospective sources."""
    service, mock_client = mock_service
    mock_client.search.return_value = {
        "answer": "On July 26, 2005, Mumbai received an unprecedented 944 mm of rain.",
        "results": [
            {
                "title": "Mumbai Deluge of 26 July 2005",
                "url": "https://thehindu.com/news/mumbai-floods-2005",
                "content": "On 26 July 2005, Mumbai recorded 944 mm of rainfall in 24 hours. Over 1,000 fatalities occurred.",
                "score": 0.95,
                "published_date": "2005-07-28",
            },
            {
                "title": "Retrospective on Mumbai 2005 Floods",
                "url": "https://sciencedirect.com/article/mumbai-flood-analysis",
                "content": "Severe flooding affected 14 districts across Maharashtra in July 2005 with 944 mm recorded.",
                "score": 0.89,
                "published_date": "2023-07-15",
            },
        ],
    }

    response = service.search("Mumbai floods July 2005", max_results=5, include_answer=True)

    assert response.query == "Mumbai floods July 2005"
    assert "Mumbai floods July 2005" in response.actual_search_query
    assert response.event_info is not None
    assert response.event_info.location == "Mumbai"
    assert response.event_info.disaster_type == "floods"
    assert response.event_info.event_date_str == "July 2005"
    assert response.total_results == 2
    assert response.total_retained == 2

    # Verify temporal classifications
    contemp = [r for r in response.retained_results if r.temporal_category == "contemporaneous"]
    retro = [r for r in response.retained_results if r.temporal_category == "retrospective"]
    assert len(contemp) == 1
    assert len(retro) == 1

    # Verify cross-verification report
    assert response.verification_report is not None
    assert any("944 mm" in f for f in response.verification_report.corroborated_facts)


def test_search_kerala_floods_august_2018_end_to_end(mock_service):
    """Scenario 2: Kerala floods, August 2018 with multi-source verification."""
    service, mock_client = mock_service
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Kerala Floods 2018 Overview",
                "url": "https://reliefweb.int/report/india/kerala-floods-2018",
                "content": "Severe floods affected Kerala in August 2018 following heavy rainfall. Over 300 dead across 14 districts.",
                "score": 0.96,
                "published_date": "2018-08-20",
            },
            {
                "title": "NDMA Deployment Report Kerala",
                "url": "https://ndma.gov.in/kerala-floods",
                "content": "NDMA rescue teams deployed in Kerala where 14 districts were submerged in August 2018.",
                "score": 0.92,
                "published_date": "2018-08-22",
            },
        ]
    }

    response = service.search("Kerala floods August 2018", max_results=3, search_depth="advanced")

    assert response.query == "Kerala floods August 2018"
    assert response.total_results == 2
    assert response.total_retained == 2
    assert response.event_info.location == "Kerala"
    assert response.event_info.event_date_str == "August 2018"


def test_search_missing_date_query(mock_service):
    """Scenario 3: A query with a missing or ambiguous date."""
    service, mock_client = mock_service
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Japan Tsunami Overview",
                "url": "https://reliefweb.int/tsunami-japan",
                "content": "A major tsunami impacted coastal Japan.",
                "score": 0.90,
                "published_date": "2011-03-15",
            }
        ]
    }

    response = service.search("Japan tsunami")
    assert response.query == "Japan tsunami"
    assert response.event_info.event_date_str is None
    # Because query has no date, article cannot be categorized as contemporaneous
    assert response.retained_results[0].temporal_category == "unknown"


def test_search_empty_results(mock_service):
    service, mock_client = mock_service
    mock_client.search.return_value = {"results": []}

    response = service.search("RandomUnknownDisasterQuery9999")
    assert response.total_results == 0
    assert response.results == []
    assert response.total_retained == 0

    formatted = service.format_results_for_display(response)
    assert "No retained search results available" in formatted


def test_invalid_api_key_error(mock_service):
    service, mock_client = mock_service
    mock_client.search.side_effect = InvalidAPIKeyError("Invalid API key provided")

    with pytest.raises(AuthenticationError) as exc_info:
        service.search("Kerala floods August 2018")
    assert "Invalid Tavily API key" in str(exc_info.value)


def test_usage_limit_error(mock_service):
    service, mock_client = mock_service
    mock_client.search.side_effect = UsageLimitExceededError("Monthly credits exhausted")

    with pytest.raises(RateLimitError) as exc_info:
        service.search("Kerala floods August 2018")
    assert "quota or rate limit exceeded" in str(exc_info.value).lower()


def test_bad_request_error(mock_service):
    service, mock_client = mock_service
    mock_client.search.side_effect = BadRequestError("Bad parameter")

    with pytest.raises(InvalidQueryError) as exc_info:
        service.search("Kerala floods")
    assert "rejected" in str(exc_info.value).lower()


def test_network_or_general_api_error(mock_service):
    service, mock_client = mock_service
    mock_client.search.side_effect = ConnectionError("Failed to reach api.tavily.com")

    with pytest.raises(NetworkOrAPIError) as exc_info:
        service.search("Kerala floods")
    assert "Tavily API request failed" in str(exc_info.value)


def test_format_results_for_display(mock_service):
    service, _ = mock_service
    sample_result = SearchResult(
        title="NDMA Kerala Flood Report",
        url="https://ndma.gov.in/kerala-floods",
        domain="ndma.gov.in",
        source_credibility="official_or_academic",
        temporal_category="contemporaneous",
        relevance_explanation="Retained: Official source contemporaneous with the event.",
        content="NDMA deployed rescue personnel across Wayanad and Ernakulam to support local emergency teams.",
        score=0.91,
        published_date="2018-08-22",
    )

    response = SearchResponse(
        query="Kerala floods August 2018",
        actual_search_query="Kerala floods August 2018 disaster news report",
        event_info=DisasterEventMetadata(
            original_query="Kerala floods August 2018",
            disaster_type="floods",
            location="Kerala",
            event_year=2018,
            event_month=8,
            event_date_str="August 2018",
            optimized_search_query="Kerala floods August 2018 disaster news report",
        ),
        total_results=1,
        total_retained=1,
        total_filtered=0,
        answer="Severe flooding in August 2018 impacted all 14 districts of Kerala.",
        results=[sample_result],
        retained_results=[sample_result],
        filtered_results=[],
        verification_report=CrossVerificationReport(
            corroborated_facts=["Widespread inundation reported across districts."],
            single_source_claims=["NDMA deployment noted by ndma.gov.in."],
            conflicting_claims=[],
            limitations=["Search relevance scores indicate keyword match, not factual certainty."],
        ),
        synthesized_incident_summary="Incident Overview: Kerala experienced severe flooding in August 2018.",
        response_time=0.62,
    )

    output = service.format_results_for_display(response)
    assert "DISASTER INTELLIGENCE & SOURCE VERIFICATION REPORT" in output
    assert "Kerala floods August 2018" in output
    assert "TAVILY SYNTHESIZED OVERVIEW:" in output
    assert "EVIDENCE-BASED INCIDENT SUMMARY:" in output
    assert "MULTI-SOURCE CROSS-VERIFICATION ANALYSIS:" in output
    assert "NDMA Kerala Flood Report" in output
    assert "https://ndma.gov.in/kerala-floods" in output
    assert "Wayanad" in output
    # Ensure key is not present anywhere in formatted display
    assert "tvly-mock-valid-key" not in output
