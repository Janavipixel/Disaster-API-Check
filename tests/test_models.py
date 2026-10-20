"""
Unit tests for data models and response parsing.
"""

from src.models import SearchResponse, SearchResult


def test_search_result_creation():
    item = SearchResult(
        title="Kerala Floods 2018: Death Toll and Relief Operations",
        url="https://example.com/kerala-floods-2018",
        content="Heavy rains caused severe flooding in Kerala during August 2018.",
        score=0.98,
        published_date="2018-08-20",
    )
    assert item.title == "Kerala Floods 2018: Death Toll and Relief Operations"
    assert item.url == "https://example.com/kerala-floods-2018"
    assert "heavy rains" in item.content.lower()
    assert item.score == 0.98


def test_search_response_from_tavily_payload():
    payload = {
        "results": [
            {
                "title": "2018 Kerala floods - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/2018_Kerala_floods",
                "content": "In August 2018, severe floods affected the south Indian state of Kerala.",
                "score": 0.952,
                "published_date": "2018-08-25",
            },
            {
                "title": "Disaster Management Report on Kerala",
                "url": "https://example.org/report",
                "content": "Detailed overview of the meteorological situation.",
                "score": "0.871",  # Test string score conversion
            },
        ]
    }

    response = SearchResponse.from_tavily_payload(
        query="Kerala floods August 2018",
        payload=payload,
        response_time=0.45,
    )

    assert response.query == "Kerala floods August 2018"
    assert response.total_results == 2
    assert len(response.results) == 2
    assert response.results[0].title == "2018 Kerala floods - Wikipedia"
    assert response.results[1].score == 0.871
    assert response.response_time == 0.45
    # Verification boundaries
    assert response.is_verified_ground_truth is False
    assert "not be assumed as verified ground truth" in response.disclaimer
    assert response.answer is None


def test_search_response_with_synthesized_answer():
    payload = {
        "answer": "The 2018 Kerala floods were caused by unprecedented monsoon rainfall between August 1 and 19.",
        "results": [
            {
                "title": "Kerala Flood Summary",
                "url": "https://example.com/summary",
                "content": "Overview of flood impact.",
            }
        ],
    }
    response = SearchResponse.from_tavily_payload(query="Kerala floods", payload=payload)
    assert response.answer is not None
    assert "unprecedented monsoon" in response.answer


def test_search_response_empty_payload():
    payload = {"results": []}
    response = SearchResponse.from_tavily_payload(
        query="UnlikelyDisasterEventXYZ999",
        payload=payload,
    )
    assert response.total_results == 0
    assert response.results == []


def test_search_response_serialization():
    payload = {
        "results": [
            {
                "title": "Test Title",
                "url": "https://test.org",
                "content": "Test snippet.",
            }
        ]
    }
    response = SearchResponse.from_tavily_payload(query="Test", payload=payload)
    dumped = response.model_dump()
    assert dumped["query"] == "Test"
    assert len(dumped["results"]) == 1
    assert "is_verified_ground_truth" in dumped


def test_gdacs_event_model_serialization():
    from src.models import GDACSEvent, GDACSQueryResponse
    event = GDACSEvent(
        event_id="1000212",
        event_type="FL",
        event_type_name="Flood",
        name="Flood in India",
        alert_level="Orange",
        country="India",
        iso3="IND",
        longitude=76.403,
        latitude=9.919,
        severity=0.0,
    )
    dumped = event.model_dump()
    assert dumped["event_id"] == "1000212"
    assert dumped["event_type"] == "FL"
    assert dumped["event_type_name"] == "Flood"
    assert dumped["country"] == "India"
    assert dumped["latitude"] == 9.919

    query_resp = GDACSQueryResponse(count=1, events=[event])
    resp_dumped = query_resp.model_dump()
    assert resp_dumped["count"] == 1
    assert len(resp_dumped["events"]) == 1
    assert "provenance" in resp_dumped["disclaimer"].lower() or "gdacs" in resp_dumped["disclaimer"].lower()
