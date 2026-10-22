# 🛰️ Disaster Intelligence — Scraper + RAG Module
 
**Project:** Disaster Intelligence using Satellite Imagery and AI  
**Role in project:** This module provides the knowledge base for the team's larger pipeline. It collects disaster reports and technical documentation, indexes them, and answers questions with source citations.

---

## What This Module Does

```
Trusted Sources (GDACS, ReliefWeb, Copernicus, NASA, GEE)
    │
    ▼
Web Scraper + RSS + REST API
    │  (Trafilatura, feedparser, requests)
    ▼
Clean, Validate, Deduplicate  →  data/raw_documents.jsonl
    │  (Pydantic schema)
    ▼
Text Chunking  →  overlapping word-level chunks
    │
    ▼
Embedding (sentence-transformers, all-MiniLM-L6-v2, local/offline)
    │
    ▼
ChromaDB (persistent vector index)  ←─ data/chroma_db/
    │
    ▼
RAG Retriever (cosine similarity + keyword re-scoring)
    │
    ▼
LLM Generator (Gemini / OpenAI / offline fallback)
    │
    ▼
Answer + Source Citations
```

---

## Quick Start (5 minutes)

### 1. Set up your environment

```bash
cd disaster-rag
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

> **Note:** `sentence-transformers` will download the embedding model (~90 MB) on first run. This is automatic and cached locally.

### 2. Configure API keys (optional)

```bash
copy .env.example .env     # Windows
# cp .env.example .env     # macOS/Linux
```

Edit `.env` and fill in at least one:
- `GOOGLE_API_KEY` — for Gemini answers (free tier available at [ai.google.dev](https://ai.google.dev))
- `OPENAI_API_KEY` — for GPT-4o-mini answers

The system works **without any API key** — it returns the retrieved source documents directly.

### 3. Run the full demo (no internet required)

```bash
python main.py
```

This will:
1. Create 6 realistic offline fixture documents
2. Build the vector index
3. Answer 5 sample disaster-intelligence questions

---

## Step-by-Step Usage

### Step A — Scrape live sources

```bash
# Scrape configured sources (HTML pages, RSS feeds, ReliefWeb API)
python scripts/run_scraper.py

# Overwrite existing output (fresh run)
python scripts/run_scraper.py --fresh

# Use offline fixtures only (no network needed)
python scripts/run_scraper.py --fixtures-only
```

Output: `data/raw_documents.jsonl`

### Step B — Build the vector index

```bash
# Build index from scraped documents
python scripts/build_index.py

# Create offline fixtures and index them (quickest demo)
python scripts/build_index.py --create-fixtures

# Wipe and rebuild the index
python scripts/build_index.py --clear --create-fixtures
```

Output: `data/chroma_db/` (persistent ChromaDB)

### Step C — Ask questions

```bash
# Single question
python scripts/query_rag.py "How does Sentinel-1 detect floods?"

# Filter by region
python scripts/query_rag.py "What disasters occurred recently?" --region Bangladesh

# More chunks for complex questions
python scripts/query_rag.py "Explain SAR change detection for earthquakes" --top-k 15

# Interactive mode
python scripts/query_rag.py --interactive
```

---

## Project Structure

```
disaster-rag/
├── config/
│   └── sources.json          # Add/remove scraping sources here
├── scraper/
│   ├── base_scraper.py       # HTTP + Trafilatura HTML scraper
│   ├── rss_scraper.py        # RSS/Atom feed parser
│   ├── api_scraper.py        # ReliefWeb REST API client
│   ├── tavily_scraper.py     # Optional Tavily search (needs API key)
│   ├── metadata_extractor.py # Optional LLM-based metadata enrichment
│   └── pipeline.py           # Orchestrates all scrapers → JSONL
├── processor/
│   ├── validator.py          # Pydantic schema (DisasterDocument)
│   ├── cleaner.py            # Text cleaning utilities
│   └── deduplicator.py       # Content-hash deduplication
├── rag/
│   ├── chunker.py            # Text chunking (sentence-aware)
│   ├── embedder.py           # sentence-transformers wrapper
│   ├── vector_store.py       # ChromaDB wrapper
│   ├── retriever.py          # Similarity search + keyword re-scoring
│   └── generator.py          # LLM answer generation
├── data/
│   ├── raw_documents.jsonl   # Scraped documents (auto-created)
│   ├── fixtures/             # Offline test documents
│   └── chroma_db/            # Persistent vector index
├── scripts/
│   ├── run_scraper.py        # CLI: scrape → JSONL
│   ├── build_index.py        # CLI: JSONL → vector index
│   └── query_rag.py          # CLI: ask a question
├── tests/
│   ├── test_processor.py     # Validator, cleaner, dedup tests
│   ├── test_rag.py           # Chunker, embedder, vector store tests
│   └── test_scraper.py       # Scraper tests (mocked network)
├── main.py                   # End-to-end demo
├── requirements.txt
├── .env.example
└── README.md
```

---

## Document Schema (JSONL)

Each line in `raw_documents.jsonl` is one JSON object:

```json
{
  "document_id":        "doc_a3f2b1c4...",
  "title":              "Sentinel-1 SAR Flood Mapping Guide",
  "source_url":         "https://...",
  "source_type":        "official_documentation",
  "publisher":          "Copernicus / ESA",
  "hazard_types":       ["flood"],
  "region":             "Bangladesh",
  "coordinates":        [23.685, 90.356],
  "event_date":         "2024-06-15",
  "content_type":       "technical_documentation",
  "published_at":       "2024-06-16",
  "retrieved_at":       "2024-10-20T13:45:00Z",
  "content":            "...(cleaned text)...",
  "content_hash":       "sha256...",
  "verification_status":"pending",
  "tags":               ["SAR", "Sentinel-1"],
  "word_count":         842
}
```

---

## Adding New Sources

Edit `config/sources.json`:

```json
{
  "html_sources": [
    {
      "name": "My New Source",
      "url": "https://example.com/disaster-reports",
      "source_type": "disaster_report",
      "publisher": "Example Org",
      "content_type": "disaster_report",
      "enabled": true,
      "tags": ["disaster", "flood"]
    }
  ]
}
```

For RSS feeds, add to `rss_sources`. For REST APIs (like ReliefWeb), add to `api_sources`.

---

## Running Tests

```bash
# All tests (some require installed packages)
pytest tests/ -v

# Skip tests that need GPU/large model (fast unit tests only)
pytest tests/test_processor.py -v

# With coverage report
pytest tests/ --cov=. --cov-report=term-missing
```

---

## Team Integration API

Other team members can import these modules:

```python
# Get relevant documents for a question programmatically
from rag.embedder import Embedder
from rag.vector_store import VectorStore
from rag.retriever import Retriever
from rag.generator import Generator

embedder = Embedder()
store = VectorStore(embedder=embedder)
retriever = Retriever(vector_store=store)
generator = Generator()

chunks = retriever.retrieve("flood extent in Bangladesh 2024")
context = retriever.format_context(chunks)
response = generator.generate(
    question="What is the flood extent in Bangladesh?",
    chunks=chunks,
    context=context,
)
print(response.answer)
print(response.sources)   # list of {title, url, relevance_score}
```

---

## Sources Configured

| Source | Type | Notes |
|--------|------|-------|
| GDACS | RSS + HTML | Real-time disaster alerts |
| ReliefWeb | API (v1) + RSS | No API key needed |
| Copernicus Data Space | HTML | Sentinel-1 docs |
| NASA Earthdata | HTML | Multi-hazard datasets |
| Google Earth Engine | HTML | SAR processing guides |
| Tavily | Search API | Optional, needs `TAVILY_API_KEY` |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Embedding model slow to load | Normal on first run — it downloads ~90 MB |
| `Vector index is empty` | Run `python scripts/build_index.py --create-fixtures` |
| No LLM answer, just context | Set `GOOGLE_API_KEY` or `OPENAI_API_KEY` in `.env` |
| Scraper returns no documents | Some sites may block bots; use `--fixtures-only` |
| ChromaDB version conflict | Use `chromadb>=0.5.0` |

---

## Ethical & Legal Notes

- This scraper respects `robots.txt` and rate limits (1.5 s between requests by default).
- It does **not** bypass authentication, CAPTCHAs, or anti-bot protections.
- Content is used for academic research only.
- All fetched content is attributed to its original source in the JSONL output.
- GDACS and ReliefWeb data are publicly available under open access terms.
