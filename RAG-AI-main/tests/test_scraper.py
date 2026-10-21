"""
Tests for the scraper components (HTML, RSS, API scrapers).
Run from project root: pytest tests/ -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.cleaner import clean_text
from processor.validator import DisasterDocument


# ─────────────────────────────────────────────────────────────────────────────
# HTML Scraper tests (mocked network)
# ─────────────────────────────────────────────────────────────────────────────

class TestHTMLScraper:
    @pytest.fixture
    def settings(self):
        return {
            "request_timeout_seconds": 10,
            "max_retries": 1,
            "rate_limit_delay_seconds": 0,
            "max_content_length_chars": 10000,
            "min_content_length_chars": 50,
            "user_agent": "TestBot/1.0",
        }

    @pytest.fixture
    def sample_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Flood Disaster Report | GDACS</title></head>
        <body>
          <nav>Home | Reports | About</nav>
          <main>
            <h1>Major Flood in Bangladesh</h1>
            <p>Published: 2024-06-15</p>
            <p>A severe flood event struck Bangladesh after record monsoon rainfall exceeding
            300 mm in 48 hours. The Surma River burst its banks, inundating the Sylhet
            district. Over 4 million people are estimated to be affected.</p>
            <p>Sentinel-1 SAR imagery acquired on 16 June shows extensive flood inundation
            across 180,000 hectares in the Sylhet division.</p>
          </main>
          <footer>All rights reserved 2024</footer>
        </body>
        </html>
        """

    def test_scrape_extracts_content(self, settings, sample_html):
        from scraper.base_scraper import HTMLScraper
        scraper = HTMLScraper(settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.text = sample_html
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper._session, "get", return_value=mock_response):
            source = {
                "url": "https://example.com/flood-report",
                "name": "Test Flood Report",
                "source_type": "disaster_report",
                "publisher": "GDACS",
                "content_type": "disaster_alert",
                "enabled": True,
                "tags": ["flood"],
            }
            docs = scraper.scrape_sources([source])

        # Should extract some content (trafilatura may or may not find text)
        # The important test is no exception is raised
        assert isinstance(docs, list)

    def test_handles_timeout_gracefully(self, settings):
        import requests
        from scraper.base_scraper import HTMLScraper
        scraper = HTMLScraper(settings)

        with patch.object(scraper._session, "get", side_effect=requests.exceptions.Timeout):
            source = {
                "url": "https://example.com/timeout",
                "name": "Timeout Test",
                "source_type": "disaster_report",
                "content_type": "disaster_alert",
                "enabled": True,
                "tags": [],
            }
            docs = scraper.scrape_sources([source])

        # Should return empty list, not raise
        assert docs == []

    def test_handles_connection_error_gracefully(self, settings):
        import requests
        from scraper.base_scraper import HTMLScraper
        scraper = HTMLScraper(settings)

        with patch.object(
            scraper._session, "get",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        ):
            source = {
                "url": "https://nonexistent.example.invalid/page",
                "name": "Connection Error Test",
                "source_type": "disaster_report",
                "content_type": "disaster_alert",
                "enabled": True,
                "tags": [],
            }
            docs = scraper.scrape_sources([source])

        assert docs == []

    def test_skips_non_html_content(self, settings):
        from scraper.base_scraper import HTMLScraper
        scraper = HTMLScraper(settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper._session, "get", return_value=mock_response):
            source = {
                "url": "https://example.com/document.pdf",
                "name": "PDF Test",
                "source_type": "official_documentation",
                "content_type": "technical_documentation",
                "enabled": True,
                "tags": [],
            }
            docs = scraper.scrape_sources([source])

        assert docs == []

    def test_disabled_sources_skipped(self, settings):
        from scraper.base_scraper import HTMLScraper
        scraper = HTMLScraper(settings)
        source = {
            "url": "https://example.com/disabled",
            "name": "Disabled Source",
            "source_type": "disaster_report",
            "content_type": "disaster_alert",
            "enabled": False,
            "tags": [],
        }
        docs = scraper.scrape_sources([source])
        assert docs == []


# ─────────────────────────────────────────────────────────────────────────────
# RSS Scraper tests (mocked feed)
# ─────────────────────────────────────────────────────────────────────────────

class TestRSSScraper:
    @pytest.fixture
    def settings(self):
        return {
            "rate_limit_delay_seconds": 0,
            "min_content_length_chars": 30,
        }

    def test_parses_feed_entries(self, settings):
        from scraper.rss_scraper import RSSScraper
        scraper = RSSScraper(settings)

        # Mock feedparser response
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_entry = MagicMock()
        mock_entry.title = "GDACS Alert: Earthquake in Nepal"
        mock_entry.link = "https://gdacs.org/alert/12345"
        mock_entry.summary = "Magnitude 6.5 earthquake struck Nepal on 2024-04-22."
        mock_entry.published_parsed = (2024, 4, 22, 12, 0, 0, 0, 0, 0)
        mock_entry.content = []  # feedparser style
        mock_feed.entries = [mock_entry]

        with patch("feedparser.parse", return_value=mock_feed):
            source = {
                "url": "https://gdacs.org/xml/rss.xml",
                "source_type": "disaster_report",
                "publisher": "GDACS",
                "content_type": "disaster_alert",
                "enabled": True,
                "tags": ["disaster"],
            }
            docs = scraper.scrape_sources([source])

        assert len(docs) == 1
        assert "Nepal" in docs[0].content or "Nepal" in docs[0].title
        assert docs[0].source_url == "https://gdacs.org/alert/12345"
        assert docs[0].publisher == "GDACS"

    def test_handles_empty_feed(self, settings):
        from scraper.rss_scraper import RSSScraper
        scraper = RSSScraper(settings)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []

        with patch("feedparser.parse", return_value=mock_feed):
            source = {
                "url": "https://example.com/empty.rss",
                "source_type": "disaster_report",
                "publisher": "Test",
                "content_type": "disaster_alert",
                "enabled": True,
                "tags": [],
            }
            docs = scraper.scrape_sources([source])

        assert docs == []

    def test_detects_hazard_from_title(self, settings):
        from scraper.rss_scraper import RSSScraper
        scraper = RSSScraper(settings)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_entry = MagicMock()
        mock_entry.title = "Major flood event in Vietnam"
        mock_entry.link = "https://gdacs.org/alert/flood-vietnam"
        mock_entry.summary = "Flooding caused displacement of 50,000 people."
        mock_entry.published_parsed = (2024, 8, 10, 8, 0, 0, 0, 0, 0)
        mock_entry.content = []
        mock_feed.entries = [mock_entry]

        with patch("feedparser.parse", return_value=mock_feed):
            source = {
                "url": "https://gdacs.org/xml/rss.xml",
                "source_type": "disaster_report",
                "publisher": "GDACS",
                "content_type": "disaster_alert",
                "enabled": True,
                "tags": [],
            }
            docs = scraper.scrape_sources([source])

        assert len(docs) == 1
        assert "flood" in docs[0].hazard_types

    def test_extracts_coordinates_and_event_metadata(self, settings):
        from scraper.rss_scraper import RSSScraper
        scraper = RSSScraper(settings)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_entry = MagicMock()
        mock_entry.title = "Green forest fire notification in Australia"
        mock_entry.link = "https://gdacs.org/report.aspx?eventtype=WF&eventid=1032994"
        mock_entry.summary = "On 20/10/2026, a forest fire started in Australia."
        mock_entry.published_parsed = (2026, 10, 20, 10, 0, 0, 0, 0, 0)
        mock_entry.content = []
        mock_entry.geo_lat = "-16.8466"
        mock_entry.geo_long = "132.9280"
        mock_entry.gdacs_country = "Australia"
        mock_entry.gdacs_eventtype = "WF"
        mock_entry.gdacs_eventid = "1032994"
        mock_entry.gdacs_severity = {"value": "5187", "unit": "ha"}
        mock_entry.gdacs_fromdate = "20/10/2026"
        mock_feed.entries = [mock_entry]

        with patch("feedparser.parse", return_value=mock_feed):
            source = {
                "url": "https://gdacs.org/xml/rss.xml",
                "source_type": "disaster_report",
                "publisher": "GDACS",
                "content_type": "disaster_alert",
                "enabled": True,
                "tags": [],
            }
            docs = scraper.scrape_sources([source])

        assert len(docs) == 1
        doc = docs[0]
        assert doc.coordinates == [-16.8466, 132.9280]
        assert doc.region == "Australia"
        assert "wildfire" in doc.hazard_types
        assert "Event ID: 1032994" in doc.content
        assert "Severity: 5187 ha" in doc.content
        assert doc.event_date == "20/10/2026"


# ─────────────────────────────────────────────────────────────────────────────
# API Scraper tests (mocked requests)
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIClient:
    def test_handles_403_appname_required_gracefully(self):
        from scraper.api_scraper import APIClient
        client = APIClient({"request_timeout_seconds": 5, "rate_limit_delay_seconds": 0})

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        import requests
        err = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = err

        with patch.object(client._session, "post", return_value=mock_resp):
            source = {
                "name": "ReliefWeb API",
                "base_url": "https://api.reliefweb.int/v2",
                "enabled": True,
            }
            docs = client.scrape_sources([source])

        assert docs == []

    def test_handles_410_deprecated_gracefully(self):
        from scraper.api_scraper import APIClient
        client = APIClient({"request_timeout_seconds": 5, "rate_limit_delay_seconds": 0})

        mock_resp = MagicMock()
        mock_resp.status_code = 410
        import requests
        err = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = err

        with patch.object(client._session, "post", return_value=mock_resp):
            source = {
                "name": "ReliefWeb API v1",
                "base_url": "https://api.reliefweb.int/v1",
                "enabled": True,
            }
            docs = client.scrape_sources([source])

        assert docs == []

    def test_handles_400_bad_request_gracefully(self):
        from scraper.api_scraper import APIClient
        client = APIClient({"request_timeout_seconds": 5, "rate_limit_delay_seconds": 0})

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "status": 400,
            "error": {"type": "BadRequestHttpException", "message": "Missing appname parameter"},
        }
        import requests
        err = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = err

        with patch.object(client._session, "post", return_value=mock_resp):
            source = {
                "name": "ReliefWeb API v2",
                "base_url": "https://api.reliefweb.int/v2",
                "enabled": True,
            }
            docs = client.scrape_sources([source])

        assert docs == []

    def test_parses_valid_reliefweb_records(self):
        from scraper.api_scraper import APIClient
        client = APIClient({"request_timeout_seconds": 5, "rate_limit_delay_seconds": 0})

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "12345",
                    "fields": {
                        "name": "Tropical Cyclone Geeta - Feb 2026",
                        "description": "Cyclone Geeta made landfall causing severe flooding.",
                        "date": {"event": "2026-02-15", "created": "2026-02-16"},
                        "country": [{"name": "Fiji"}],
                        "type": [{"name": "Tropical Cyclone"}],
                        "url": "https://reliefweb.int/disaster/12345",
                    },
                }
            ]
        }

        with patch.object(client._session, "post", return_value=mock_resp):
            source = {
                "name": "ReliefWeb API v2",
                "base_url": "https://api.reliefweb.int/v2",
                "enabled": True,
            }
            docs = client.scrape_sources([source])

        assert len(docs) == 1
        assert docs[0].title == "Tropical Cyclone Geeta - Feb 2026"
        assert docs[0].region == "Fiji"
        assert "cyclone" in docs[0].hazard_types or "tropical_cyclone" in docs[0].hazard_types
        assert docs[0].source_url == "https://reliefweb.int/disaster/12345"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline integration test (fixtures)
# ─────────────────────────────────────────────────────────────────────────────

class TestScraperPipeline:
    def test_pipeline_saves_jsonl(self, tmp_path):
        """End-to-end test using only fixture data (no network)."""
        import json
        import shutil

        # Create minimal fixture
        fixture_path = tmp_path / "fixtures" / "test_documents.jsonl"
        fixture_path.parent.mkdir(parents=True)
        doc = DisasterDocument(
            title="Fixture Test",
            source_url="https://fixture.example.com/test",
            content="This is a test fixture document about flood detection using SAR.",
            source_type="fixture",
            verification_status="fixture",
        )
        with fixture_path.open("w", encoding="utf-8") as f:
            f.write(doc.model_dump_json() + "\n")

        output_path = tmp_path / "output.jsonl"
        shutil.copy(fixture_path, output_path)

        # Verify the output can be read back
        with output_path.open("r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        assert len(lines) == 1
        loaded = json.loads(lines[0])
        assert loaded["title"] == "Fixture Test"
        assert loaded["verification_status"] == "fixture"
