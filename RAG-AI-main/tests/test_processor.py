"""
Tests for the scraper processor components (validator, cleaner, deduplicator).
Run from project root: pytest tests/ -v
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.cleaner import clean_text, clean_title, truncate_content
from processor.deduplicator import Deduplicator
from processor.validator import (
    DisasterDocument,
    SourceType,
    ContentType,
    VerificationStatus,
    detect_hazard_types,
    extract_region,
    make_document_id,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_doc(**kwargs) -> DisasterDocument:
    defaults = dict(
        title="Test Flood Report",
        source_url="https://example.com/flood-report",
        content="Heavy flooding struck Bangladesh after monsoon rains exceeded 300 mm.",
    )
    defaults.update(kwargs)
    return DisasterDocument(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Validator tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDisasterDocument:
    def test_basic_creation(self):
        doc = make_doc()
        assert doc.title == "Test Flood Report"
        assert doc.content_hash != ""
        assert doc.word_count > 0
        assert doc.document_id.startswith("doc_")

    def test_stable_document_id(self):
        id1 = make_document_id("https://example.com/page")
        id2 = make_document_id("https://example.com/page")
        assert id1 == id2
        assert id1.startswith("doc_")

    def test_different_urls_give_different_ids(self):
        id1 = make_document_id("https://example.com/page-a")
        id2 = make_document_id("https://example.com/page-b")
        assert id1 != id2

    def test_content_hash_is_sha256(self):
        doc = make_doc(content="Hello world")
        expected = hashlib.sha256("Hello world".encode()).hexdigest()
        assert doc.content_hash == expected

    def test_word_count(self):
        doc = make_doc(content="one two three four five")
        assert doc.word_count == 5

    def test_invalid_url_raises(self):
        with pytest.raises(Exception):
            make_doc(source_url="not-a-url")

    def test_invalid_coordinates_raise(self):
        with pytest.raises(Exception):
            make_doc(coordinates=[200.0, 0.0])  # lat out of range

    def test_valid_coordinates(self):
        doc = make_doc(coordinates=[23.685, 90.356])
        assert doc.coordinates == [23.685, 90.356]

    def test_hazard_normalisation(self):
        doc = make_doc(hazard_types=["Flood", "Earth Quake"])
        assert "flood" in doc.hazard_types
        assert "earth_quake" in doc.hazard_types

    def test_serialise_to_json(self):
        doc = make_doc()
        json_str = doc.model_dump_json()
        data = json.loads(json_str)
        assert data["title"] == "Test Flood Report"
        assert "content_hash" in data

    def test_null_optional_fields(self):
        doc = make_doc()
        assert doc.region is None
        assert doc.event_date is None
        assert doc.published_at is None
        assert doc.coordinates is None


# ─────────────────────────────────────────────────────────────────────────────
# Hazard detection tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHazardDetection:
    def test_detects_flood(self):
        assert "flood" in detect_hazard_types("Major flood hit the city")

    def test_detects_earthquake(self):
        assert "earthquake" in detect_hazard_types("7.8 magnitude earthquake struck Turkey")

    def test_detects_wildfire(self):
        assert "wildfire" in detect_hazard_types("Wildfire burns 10,000 acres")

    def test_detects_cyclone(self):
        hazards = detect_hazard_types("Cyclone Mocha makes landfall")
        assert "cyclone" in hazards

    def test_empty_text(self):
        assert detect_hazard_types("") == []

    def test_no_hazard(self):
        assert detect_hazard_types("The weather today is sunny and warm") == []

    def test_multiple_hazards(self):
        hazards = detect_hazard_types("Earthquake triggered a tsunami and landslide")
        assert "earthquake" in hazards
        assert "tsunami" in hazards
        assert "landslide" in hazards


# ─────────────────────────────────────────────────────────────────────────────
# Region extraction tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRegionExtraction:
    def test_detects_bangladesh(self):
        assert extract_region("Severe flooding struck Bangladesh") == "Bangladesh"

    def test_detects_turkey(self):
        assert extract_region("Turkey earthquake kills thousands") == "Turkey"

    def test_returns_none_for_unknown(self):
        assert extract_region("Generic text with no country") is None

    def test_case_insensitive(self):
        assert extract_region("major disaster in INDIA") == "India"


# ─────────────────────────────────────────────────────────────────────────────
# Cleaner tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCleaner:
    def test_removes_boilerplate(self):
        text = "Good content.\n\nAccept all cookies and continue browsing."
        cleaned = clean_text(text)
        assert "accept all cookies" not in cleaned.lower()

    def test_collapses_blank_lines(self):
        text = "Line 1\n\n\n\n\nLine 2"
        cleaned = clean_text(text)
        assert "\n\n\n" not in cleaned

    def test_collapses_spaces(self):
        text = "word1    word2     word3"
        cleaned = clean_text(text)
        assert "  " not in cleaned

    def test_clean_title_removes_suffix(self):
        assert clean_title("Flood Report | GDACS") == "Flood Report"
        assert clean_title("Earthquake Update – ReliefWeb") == "Earthquake Update"

    def test_clean_title_empty(self):
        assert clean_title("") == "Untitled"

    def test_truncate_at_limit(self):
        text = "word " * 100  # 500 chars
        truncated = truncate_content(text, max_chars=50)
        assert len(truncated) <= 100  # some slack for truncation message

    def test_truncate_short_text_unchanged(self):
        text = "Short text."
        assert truncate_content(text, max_chars=1000) == text


# ─────────────────────────────────────────────────────────────────────────────
# Deduplicator tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDeduplicator:
    def test_first_doc_is_not_duplicate(self):
        dedup = Deduplicator()
        doc = make_doc()
        assert not dedup.is_duplicate(doc)

    def test_same_doc_twice_is_duplicate(self):
        dedup = Deduplicator()
        doc = make_doc()
        dedup.register(doc)
        assert dedup.is_duplicate(doc)

    def test_different_url_same_content_is_duplicate(self):
        dedup = Deduplicator()
        doc1 = make_doc(source_url="https://example.com/a")
        doc2 = make_doc(source_url="https://example.com/b")  # same content
        dedup.register(doc1)
        # doc2 has same content hash → duplicate
        assert dedup.is_duplicate(doc2)

    def test_filter_new_removes_duplicates(self):
        dedup = Deduplicator()
        doc1 = make_doc(source_url="https://example.com/a")
        doc2 = make_doc(source_url="https://example.com/b", content="Different content here.")
        doc3 = make_doc(source_url="https://example.com/a")  # same URL as doc1
        new_docs = dedup.filter_new([doc1, doc2, doc3])
        assert len(new_docs) == 2

    def test_loads_from_jsonl(self):
        doc = make_doc()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(doc.model_dump_json() + "\n")
            tmp = Path(f.name)
        try:
            dedup = Deduplicator.from_jsonl(tmp)
            assert dedup.is_duplicate(doc)
        finally:
            tmp.unlink()

    def test_one_existing_and_one_new_document(self):
        """Verify that an existing document is skipped and a genuinely new one is saved."""
        existing_doc = make_doc(
            title="Existing Disaster Event",
            source_url="https://example.com/disaster-existing",
            content="This disaster record was already ingested previously in raw_documents.jsonl.",
        )
        new_doc = make_doc(
            title="Genuinely New Flood Alert",
            source_url="https://example.com/disaster-new-alert-2026",
            content="A brand new flood emergency occurred in a previously unreported district.",
        )

        # Pre-populate deduplicator with existing_doc
        dedup = Deduplicator()
        dedup.register(existing_doc)

        # Filter the batch containing both
        filtered = dedup.filter_new([existing_doc, new_doc])

        # Verify only the genuinely new document is accepted
        assert len(filtered) == 1
        assert filtered[0].source_url == new_doc.source_url
        assert filtered[0].title == new_doc.title

        # Verify diagnostic counters
        assert dedup.stats["total_checked"] == 2
        assert dedup.stats["genuinely_new"] == 1
        assert dedup.stats["url_duplicates"] == 1
        assert dedup.stats["hash_duplicates"] == 0
        assert dedup.stats["invalid_documents"] == 0

    def test_diagnostic_breakdown_counts(self):
        """Verify accurate diagnostic reporting across all duplicate categories."""
        doc1 = make_doc(
            title="Doc 1",
            source_url="https://example.com/doc1",
            content="Unique content 1 about cyclone response.",
        )
        doc_same_url = make_doc(
            title="Doc 1 Revisited",
            source_url="https://example.com/doc1",
            content="Updated wording but identical URL.",
        )
        doc_same_content = make_doc(
            title="Doc 1 Mirror",
            source_url="https://example.com/doc1-mirror",
            content="Unique content 1 about cyclone response.",  # identical content hash
        )
        doc_new = make_doc(
            title="Doc 2",
            source_url="https://example.com/doc2",
            content="Completely new technical report on SAR change detection.",
        )

        dedup = Deduplicator()
        dedup.register(doc1)

        filtered = dedup.filter_new([doc_same_url, doc_same_content, doc_new, "not_a_doc"])

        assert len(filtered) == 1
        assert filtered[0].source_url == "https://example.com/doc2"
        assert dedup.stats["total_checked"] == 4
        assert dedup.stats["genuinely_new"] == 1
        assert dedup.stats["url_duplicates"] == 1
        assert dedup.stats["hash_duplicates"] == 1
        assert dedup.stats["invalid_documents"] == 1

    def test_save_new_and_skip_existing_url_and_content_hash(self, tmp_path):
        """
        Verify:
          1. An existing URL is skipped (url_duplicate)
          2. An existing content hash is skipped (hash_duplicate)
          3. One genuinely new document is accepted and appended to JSONL
          4. Record count on disk increases from 1 to 2
        """
        from scraper.pipeline import save_jsonl

        jsonl_path = tmp_path / "test_raw_documents.jsonl"

        # Baseline document on disk
        baseline_doc = make_doc(
            title="Baseline Earthquake Report",
            source_url="https://example.com/earthquake-baseline",
            content="A magnitude 7.0 earthquake occurred in Province A on 2026-01-01.",
        )
        written = save_jsonl([baseline_doc], jsonl_path, append=False)
        assert written == 1

        # Load deduplicator from the saved file
        dedup = Deduplicator.from_jsonl(jsonl_path)
        assert len(dedup._urls) == 1
        assert len(dedup._hashes) == 1

        # Candidate 1: Same URL, different content -> skip as url_duplicate
        candidate_dup_url = make_doc(
            title="Baseline Updated Info",
            source_url="https://example.com/earthquake-baseline",
            content="Completely changed report text for the same exact URL link.",
        )

        # Candidate 2: Different URL, identical content -> skip as hash_duplicate
        candidate_dup_hash = make_doc(
            title="Baseline Mirror Site",
            source_url="https://mirror.example.org/earthquake-copy",
            content="A magnitude 7.0 earthquake occurred in Province A on 2026-01-01.",
        )

        # Candidate 3: Genuinely new URL and content -> must be accepted
        candidate_new = make_doc(
            title="New Tsunami Warning",
            source_url="https://example.com/tsunami-new-2026",
            content="A major tsunami warning issued for coastal districts following offshore tremor.",
        )

        # Filter the 3 candidates
        candidates = [candidate_dup_url, candidate_dup_hash, candidate_new]
        new_docs = dedup.filter_new(candidates)

        # 1. Exactly 1 document accepted
        assert len(new_docs) == 1
        assert new_docs[0].source_url == candidate_new.source_url
        assert new_docs[0].title == candidate_new.title

        # 2. Diagnostic stats match exact duplicate reasons
        assert dedup.stats["total_checked"] == 3
        assert dedup.stats["genuinely_new"] == 1
        assert dedup.stats["url_duplicates"] == 1
        assert dedup.stats["hash_duplicates"] == 1
        assert dedup.stats["invalid_documents"] == 0

        # 3. Save only the genuinely new document to disk
        appended = save_jsonl(new_docs, jsonl_path, append=True)
        assert appended == 1

        # 4. Verify disk contents and record count
        with jsonl_path.open("r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 2
        assert lines[0]["source_url"] == baseline_doc.source_url
        assert lines[1]["source_url"] == candidate_new.source_url

        # 5. Subsequent run with same candidates should yield 0 new docs
        second_run = dedup.filter_new(candidates)
        assert len(second_run) == 0
        assert dedup.stats["genuinely_new"] == 0
        assert dedup.stats["url_duplicates"] == 2  # baseline + candidate_new now in _urls
        assert dedup.stats["hash_duplicates"] == 1
