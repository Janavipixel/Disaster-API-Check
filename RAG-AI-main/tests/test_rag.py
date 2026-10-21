"""
Tests for the RAG pipeline components (chunker, embedder, vector store, retriever).
Run from project root: pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.validator import DisasterDocument
from rag.chunker import Chunk, chunk_document, chunk_documents, chunk_text


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_doc(content: str = None) -> DisasterDocument:
    if content is None:
        content = (
            "Sentinel-1 is a C-band SAR satellite used for flood detection. "
            "It provides all-weather, day-and-night imaging. "
            "Flood pixels are identified by low backscatter values. "
            "The Copernicus Emergency Management Service uses Sentinel-1 data. "
            "Change detection compares pre- and post-event images. "
        ) * 20  # ~1000 words
    return DisasterDocument(
        title="Test SAR Document",
        source_url="https://example.com/sar-test",
        content=content,
        hazard_types=["flood"],
        region="Europe",
        tags=["SAR", "Sentinel-1"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Chunker tests
# ─────────────────────────────────────────────────────────────────────────────

class TestChunker:
    def test_chunk_text_basic(self):
        text = " ".join(f"word{i}" for i in range(1000))
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) > 1
        for chunk in chunks:
            words = chunk.split()
            assert len(words) <= 120  # some tolerance for sentence boundaries

    def test_chunk_text_empty(self):
        assert chunk_text("") == []

    def test_chunk_text_short(self):
        text = "Short text that fits in one chunk."
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == text.strip()

    def test_chunk_overlap(self):
        """Chunks should share some words at boundaries."""
        text = " ".join(f"word{i}." for i in range(200))
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        if len(chunks) >= 2:
            # Last words of chunk[0] should appear at start of chunk[1]
            end_words = set(chunks[0].split()[-10:])
            start_words = set(chunks[1].split()[:10])
            assert len(end_words & start_words) > 0

    def test_chunk_document_returns_chunks(self):
        doc = make_doc()
        chunks = chunk_document(doc, chunk_size=100, overlap=10)
        assert len(chunks) > 1
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_ids_are_unique(self):
        doc = make_doc()
        chunks = chunk_document(doc, chunk_size=100, overlap=10)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_metadata_preserved(self):
        doc = make_doc()
        chunks = chunk_document(doc, chunk_size=100, overlap=10)
        for chunk in chunks:
            assert chunk.source_url == doc.source_url
            assert chunk.title == doc.title
            assert chunk.document_id == doc.document_id
            assert "flood" in chunk.hazard_types
            assert chunk.region == "Europe"

    def test_total_chunks_consistent(self):
        doc = make_doc()
        chunks = chunk_document(doc, chunk_size=100, overlap=10)
        total = len(chunks)
        for chunk in chunks:
            assert chunk.total_chunks == total

    def test_chunk_to_metadata_types(self):
        doc = make_doc()
        chunk = chunk_document(doc, chunk_size=100, overlap=10)[0]
        meta = chunk.to_metadata()
        # ChromaDB requires str/int/float/bool — no lists
        for key, val in meta.items():
            assert isinstance(val, (str, int, float, bool)), \
                f"Metadata key '{key}' has non-primitive type {type(val)}"

    def test_chunk_documents_multiple(self):
        docs = [make_doc() for _ in range(3)]
        all_chunks = chunk_documents(docs, chunk_size=100, overlap=10)
        assert len(all_chunks) > 3  # more chunks than docs


# ─────────────────────────────────────────────────────────────────────────────
# Embedder tests (uses actual model — skipped if not installed)
# ─────────────────────────────────────────────────────────────────────────────

class TestEmbedder:
    @pytest.fixture(autouse=True)
    def check_deps(self):
        pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

    def test_embed_returns_vectors(self):
        from rag.embedder import Embedder
        embedder = Embedder()
        vecs = embedder.embed(["Flood in Bangladesh", "Earthquake in Turkey"])
        assert len(vecs) == 2
        assert len(vecs[0]) > 0  # non-empty vectors

    def test_embed_one(self):
        from rag.embedder import Embedder
        embedder = Embedder()
        vec = embedder.embed_one("Sentinel-1 SAR flood detection")
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)

    def test_embed_normalised(self):
        """Vectors should be approximately unit-length (normalised=True)."""
        import math
        from rag.embedder import Embedder
        embedder = Embedder()
        vec = embedder.embed_one("Test sentence")
        magnitude = math.sqrt(sum(v ** 2 for v in vec))
        assert 0.99 < magnitude < 1.01

    def test_empty_input(self):
        from rag.embedder import Embedder
        embedder = Embedder()
        result = embedder.embed([])
        assert result == []

    def test_dimension(self):
        from rag.embedder import Embedder
        embedder = Embedder()
        assert embedder.dimension > 0


# ─────────────────────────────────────────────────────────────────────────────
# Vector store + retriever integration test (in-memory chroma)
# ─────────────────────────────────────────────────────────────────────────────

class TestVectorStoreRetriever:
    @pytest.fixture(autouse=True)
    def check_deps(self):
        pytest.importorskip("chromadb", reason="chromadb not installed")
        pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

    @pytest.fixture
    def in_memory_store(self, tmp_path):
        from rag.embedder import Embedder
        from rag.vector_store import VectorStore
        embedder = Embedder()
        store = VectorStore(
            embedder=embedder,
            persist_dir=str(tmp_path / "chroma_test"),
            collection_name="test_collection",
        )
        return store

    def test_add_and_count(self, in_memory_store):
        doc = make_doc(content="Sentinel-1 SAR flood detection method.")
        chunks = chunk_document(doc, chunk_size=50, overlap=5)
        added = in_memory_store.add_chunks(chunks)
        assert added > 0
        assert in_memory_store.count() == added

    def test_query_returns_results(self, in_memory_store):
        doc = make_doc(content="Sentinel-1 SAR detects floods using backscatter analysis.")
        chunks = chunk_document(doc, chunk_size=50, overlap=5)
        in_memory_store.add_chunks(chunks)
        results = in_memory_store.query("flood detection SAR", n_results=3)
        assert len(results) > 0
        assert "text" in results[0]
        assert "relevance_score" in results[0]

    def test_retriever_reranks(self, in_memory_store):
        from rag.retriever import Retriever
        doc = make_doc(content="Sentinel-1 detects floods. Earthquake damage assessment via SAR.")
        chunks = chunk_document(doc, chunk_size=50, overlap=5)
        in_memory_store.add_chunks(chunks)
        retriever = Retriever(vector_store=in_memory_store, top_k=5, final_k=3)
        results = retriever.retrieve("SAR flood detection")
        assert len(results) <= 3
        # Results should be sorted by relevance descending
        scores = [r["relevance_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_retriever_empty_store(self, in_memory_store):
        from rag.retriever import Retriever
        retriever = Retriever(vector_store=in_memory_store)
        results = retriever.retrieve("any question")
        assert results == []

    def test_format_context(self, in_memory_store):
        from rag.retriever import Retriever
        doc = make_doc(content="Bangladesh flood 2024 affected millions.")
        chunks = chunk_document(doc, chunk_size=50, overlap=5)
        in_memory_store.add_chunks(chunks)
        retriever = Retriever(vector_store=in_memory_store)
        results = retriever.retrieve("Bangladesh flood")
        context = retriever.format_context(results)
        assert "[SOURCE 1]" in context
        assert "URL:" in context


# ─────────────────────────────────────────────────────────────────────────────
# Generator & LLM integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerator:
    def test_offline_mode_default_when_no_api_keys(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        from rag.generator import Generator
        gen = Generator()
        assert gen._backend == "offline"

        chunks = [
            {
                "chunk_id": "c1",
                "text": "Sentinel-1 SAR detected flood extent of 150,000 hectares.",
                "metadata": {"title": "Copernicus Flood Report", "source_url": "https://example.com/c1"},
                "relevance_score": 0.85,
            }
        ]
        resp = gen.generate("What was the flood extent?", chunks, context="Context block")
        assert resp.offline_mode is True
        assert resp.model_used == "offline"
        assert len(resp.sources) == 1
        assert resp.sources[0]["url"] == "https://example.com/c1"

    def test_empty_chunks_returns_insufficient_evidence(self):
        from rag.generator import Generator
        gen = Generator()
        resp = gen.generate("Unknown disaster in nonexistent region?", [], context="")
        assert "Insufficient evidence" in resp.answer
        assert resp.chunk_count == 0
        assert resp.uncertainty_or_limitations is not None

    def test_gemini_generation_mocked(self, monkeypatch):
        from unittest.mock import MagicMock, patch
        monkeypatch.setenv("GOOGLE_API_KEY", "fake-gemini-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            "According to [SOURCE 1], Sentinel-1 SAR imagery detected flood extents "
            "across 180,000 hectares in Sylhet, Bangladesh.\n\n"
            "## Sources\n[1] GDACS Alert (https://gdacs.org/alert/1)"
        )
        mock_model.generate_content.return_value = mock_response

        with patch("google.generativeai.GenerativeModel", return_value=mock_model):
            from rag.generator import Generator
            gen = Generator(model="gemini-1.5-flash")
            assert gen._backend == "gemini"

            chunks = [
                {
                    "chunk_id": "c1",
                    "text": "Flood footprint 180,000 hectares in Sylhet.",
                    "metadata": {"title": "GDACS Alert", "source_url": "https://gdacs.org/alert/1"},
                    "relevance_score": 0.95,
                }
            ]
            resp = gen.generate("What is the flood footprint?", chunks, context="Retrieved Context")
            assert resp.offline_mode is False
            assert resp.model_used == "gemini-1.5-flash"
            assert "180,000 hectares" in resp.answer
            assert len(resp.cited_sources) == 1
            assert resp.cited_sources[0]["url"] == "https://gdacs.org/alert/1"

    def test_openai_generation_mocked(self, monkeypatch):
        from unittest.mock import MagicMock, patch
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")

        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = (
            "Based on [SOURCE 1], Google Earth Engine uses Sentinel-1 GRD imagery "
            "for backscatter change detection.\n\n"
            "## Sources\n[1] GEE Guide (https://developers.google.com/earth-engine)"
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            from rag.generator import Generator
            gen = Generator(model="gpt-4o-mini")
            assert gen._backend == "openai"

            chunks = [
                {
                    "chunk_id": "c1",
                    "text": "GEE uses Sentinel-1 for change detection.",
                    "metadata": {"title": "GEE Guide", "source_url": "https://developers.google.com/earth-engine"},
                    "relevance_score": 0.90,
                }
            ]
            resp = gen.generate("How does GEE detect change?", chunks, context="Retrieved Context")
            assert resp.offline_mode is False
            assert "backscatter change detection" in resp.answer
            assert resp.cited_sources[0]["title"] == "GEE Guide"

    def test_invalid_api_credentials_fallback(self, monkeypatch):
        from unittest.mock import MagicMock, patch
        monkeypatch.setenv("GOOGLE_API_KEY", "invalid-key")

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API_KEY_INVALID: 403 Forbidden")

        with patch("google.generativeai.GenerativeModel", return_value=mock_model):
            from rag.generator import Generator
            gen = Generator()
            chunks = [
                {
                    "chunk_id": "c1",
                    "text": "Fallback source passage text.",
                    "metadata": {"title": "Report", "source_url": "https://example.com/rep"},
                    "relevance_score": 0.80,
                }
            ]
            resp = gen.generate("Any question?", chunks, context="Sample context block")
            assert resp.offline_mode is True
            assert "LLM Generation Unavailable" in resp.answer
            assert "Sample context block" in resp.answer
            assert resp.error is not None

    def test_detect_conflicting_reports_and_uncertainty(self):
        from rag.generator import Generator
        gen = Generator()
        chunks = [
            {
                "chunk_id": "c1",
                "text": "Death toll reported at 15 by Local Agency.",
                "metadata": {"title": "Report A", "source_url": "https://example.com/a"},
                "relevance_score": 0.70,
            }
        ]
        conflicting_answer = (
            "Source [SOURCE 1] notes 15 fatalities, however there is conflicting information "
            "and differing figures reported across authorities."
        )
        uncertainty = gen._detect_uncertainties(conflicting_answer, chunks)
        assert uncertainty is not None
        assert "Conflicting reports" in uncertainty

    def test_disaster_context_injected_into_prompt(self):
        from rag.retriever import Retriever
        from unittest.mock import MagicMock
        store = MagicMock()
        store.count.return_value = 1
        store.query.return_value = []
        retriever = Retriever(vector_store=store)

        context_dict = {
            "hazard_type": "flood",
            "target_location": "Valencia, Spain",
            "satellite_sensor": "Sentinel-1A IW GRD",
        }
        formatted = retriever.format_context([], disaster_context=context_dict)
        assert "Operational Disaster Context" in formatted
        assert "Valencia, Spain" in formatted
        assert "Sentinel-1A IW GRD" in formatted


# ─────────────────────────────────────────────────────────────────────────────
# Unified DisasterRAGPipeline tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDisasterRAGPipeline:
    @pytest.fixture
    def populated_pipeline(self, tmp_path):
        from rag.embedder import Embedder
        from rag.pipeline import DisasterRAGPipeline
        from rag.vector_store import VectorStore

        embedder = Embedder()
        store_dir = str(tmp_path / "pipeline_chroma")
        store = VectorStore(embedder=embedder, persist_dir=store_dir, collection_name="pipeline_test")

        doc1 = make_doc(
            content=(
                "Sentinel-1 SAR flood monitoring in Bangladesh Sylhet division. "
                "Floods inundated 180,000 hectares on 2024-06-15. "
                "Event ID: 1104099. Severity: 5187 ha. Affected Population: 4000000. "
                "Coordinates: [24.8949, 91.8687]."
            )
        )
        chunks = chunk_document(doc1, chunk_size=80, overlap=10)
        store.add_chunks(chunks)

        pipeline = DisasterRAGPipeline(persist_dir=store_dir)
        pipeline._store = store
        pipeline._embedder = embedder
        return pipeline

    def test_pipeline_end_to_end_query(self, populated_pipeline):
        res = populated_pipeline.query(
            question="What is the flood footprint in Sylhet, Bangladesh?",
            disaster_context={"hazard": "flood", "location": "Sylhet"},
        )
        assert res.question == "What is the flood footprint in Sylhet, Bangladesh?"
        assert len(res.evidence) > 0
        assert len(res.source_urls) > 0
        assert res.timestamps["queried_at"] is not None
        assert len(res.disaster_events) > 0

        # Check extracted disaster event
        ev = res.disaster_events[0]
        assert ev["event_id"] == "1104099"
        assert ev["coordinates"] == [24.8949, 91.8687]
        assert "4000000" in ev["affected_population"]

    def test_pipeline_json_serialization(self, populated_pipeline):
        res = populated_pipeline.query("How does SAR detect floods?")
        data = res.to_dict()
        assert "question" in data
        assert "answer" in data
        assert "evidence" in data
        assert "source_urls" in data
        assert "disaster_events" in data
        assert "timestamps" in data

    def test_pipeline_display_output(self, populated_pipeline):
        res = populated_pipeline.query("How does SAR detect floods?")
        display_str = res.display()
        assert "[QUESTION]" in display_str
        assert "[ANSWER]" in display_str
        assert "[SOURCES]" in display_str
