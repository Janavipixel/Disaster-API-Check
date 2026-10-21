# Rapid Post-Disaster Change Intelligence from Multi-Temporal Satellite Data
## Phase 1: Disaster-Specific Tavily Search & Source Verification

This repository hosts the **Phase 1** implementation of the *Rapid Post-Disaster Change Intelligence* system: an intelligent integration with the **Tavily Search API** that extracts disaster incident entities, evaluates source credibility, classifies contemporaneous vs. retrospective reporting, and conducts transparent multi-source cross-verification.

---

## 1. Scope & Verification Boundaries

Phase 1 focuses on automated web intelligence retrieval and rigorous source verification.

- **Included**:
  - Natural-language disaster query entity extraction (incident hazard, location, event date).
  - Targeted search query optimization while preserving the original user query.
  - Strict distinction between disaster event occurrence dates and web article publication dates.
  - Source credibility tiering: official government/academic, established news, general web, and low-value/social noise filtering.
  - Deduplication and content relevance filtering.
  - Transparent cross-source verification (corroborated facts, single-source claims, conflicting figures, and verification limitations).
  - Clean CLI reporting with Unicode-safe terminal wrapping and JSON export.
  - Offline automated test suite with 100% passing tests.
- **Strictly Excluded from Phase 1**:
  - LLM extraction (Gemini / Google AI).
  - Geocoding and bounding box calculation.
  - Satellite data fetching (Sentinel-1 / Sentinel-2).
  - Flood / change detection algorithms.
  - Web dashboard UI.

> **Ground Truth Disclaimer**: News articles and web reports gathered through this search service represent preliminary, unverified media reports. They must be validated against multi-temporal satellite observations in subsequent pipeline phases.

---

## 2. Directory Structure

```text
Disaster/
├── .env.example             # Template for environment configuration
├── .gitignore               # Excludes secrets (.env), caches, and virtual environments
├── requirements.txt         # Project dependencies
├── README.md                # Documentation and run instructions
├── src/
│   ├── __init__.py          # Package initializer
│   ├── config.py            # Environment loading, key validation, and secret masking
│   ├── models.py            # Pydantic schemas (SearchResult, SearchResponse, DisasterEventMetadata, CrossVerificationReport)
│   ├── query_parser.py      # Entity extraction (incident, location, date) & temporal classification
│   ├── verification.py      # Credibility evaluation, deduplication, filtering & cross-verification
│   ├── tavily_client.py     # Core TavilySearchService wrapper & output formatting
│   └── main.py              # CLI entry point (interactive, flags, and JSON modes)
└── tests/
    ├── __init__.py          # Test suite initializer
    ├── test_config.py       # Tests for configuration and key validation
    ├── test_models.py       # Tests for response parsing and schemas
    ├── test_query_parser.py # Tests for incident extraction and temporal categorization
    ├── test_verification.py # Tests for filtering, duplicates, and conflicting claims
    └── test_tavily_client.py# Tests for SDK error handling, empty results, and formatting
```

### Purpose of Each File

| File | Purpose |
| :--- | :--- |
| `src/query_parser.py` | Extracts disaster type, location, and event date from natural language; constructs targeted queries; classifies articles as contemporaneous, retrospective, or unknown. |
| `src/verification.py` | Evaluates source domain credibility, filters low-value/social media domains, deduplicates results, and cross-compares factual claims across sources (corroborated vs. single-source vs. conflicting). |
| `src/models.py` | Strongly-typed Pydantic schemas: `SearchResult`, `SearchResponse`, `DisasterEventMetadata`, and `CrossVerificationReport`. |
| `src/tavily_client.py` | Manages TavilyClient execution, sanitizes web content to prevent terminal glitches, coordinates verification pipeline, and formats human-readable CLI reports. |
| `src/config.py` | Loads `.env` via `python-dotenv`, verifies that `TAVILY_API_KEY` is present and non-placeholder, and provides key masking so secrets never print in logs or outputs. |
| `src/main.py` | CLI entry point supporting direct queries, interactive prompt, `--answer`, `--no-optimize`, and `--json` flags. |

---

## 3. Installation & Setup

### Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- An active Tavily API Key (free tier available at [app.tavily.com](https://app.tavily.com))

### 1. Set Up Virtual Environment (Recommended)
```bash
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 4. Configuration (.env)

1. Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` and configure your key:
   ```env
   TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

---

## 5. How to Run

### Option A: Query via CLI Argument
```bash
python -m src.main "Mumbai floods July 2005" --answer
```
```bash
python -m src.main "Kerala floods August 2018" --answer
```

### Option B: Interactive Mode
```bash
python -m src.main
```

### Option C: JSON Output (for Downstream Pipelines)
```bash
python -m src.main "Kerala floods August 2018" --json
```

---

## 6. Running Automated Tests

Run the full offline test suite (44 tests, 0 API credits used):
```bash
python -m pytest -v
```
All tests use offline fixtures and mocks to verify:
- Domain credibility tiering (including `cbsnews.com` mapped to `established_news`).
- Documented time-window rule (contemporaneous <=12 months post-disaster, pre-event background, and retrospective >12 months).
- Cross-source claim corroboration with unit normalization (`944 millimetres` matching `944 mm`).
- Casualty scale corroboration (`claiming 1094 lives` and `death of over 1,000 people` corroborating a >1,000 fatality scale).
- Discrepancy flagging for conflicting casualty figures (early dispatches vs. final administrative counts).
- Syndicated wire report deduplication across distinct domains.
- Retention of valuable retrospective historical analyses while filtering genuinely irrelevant content.
- Explicit unverified claim marking with empty sources when retrieved snippets lack factual evidence.
- Full ClaimEvidence structure with supporting URLs, domains, and quoted excerpts.
