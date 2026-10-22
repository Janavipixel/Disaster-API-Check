"""
Optional LLM-based metadata extractor.

Runs AFTER the scraper has already fetched real content.
Uses the LLM to extract structured disaster metadata from text
that the keyword-based methods may have missed.

This is OPTIONAL — the pipeline works perfectly without it.
Enable by setting GOOGLE_API_KEY or OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

from processor.validator import DisasterDocument, detect_hazard_types, extract_region

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Extract structured disaster metadata from the following text.
Return ONLY a valid JSON object with these exact keys:
{{
  "hazard_types": ["list of hazard types from: flood, earthquake, cyclone, wildfire, tsunami, landslide, drought, volcano, storm"],
  "region": "country or region name, or null",
  "event_date": "ISO-8601 date of the disaster event, or null",
  "coordinates": [latitude, longitude] or null,
  "summary": "1-2 sentence summary of the disaster event, or null"
}}

Rules:
- Only include hazard types explicitly mentioned in the text.
- Only include coordinates if explicitly stated — do NOT geocode from place names.
- Return null for any field you cannot determine from the text.
- Do NOT invent information.

TEXT:
{text}
"""


class MetadataExtractor:
    """
    Uses an LLM to enrich disaster documents with structured metadata.
    Falls back gracefully to keyword-based extraction if no API key is available.
    """

    def __init__(self):
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str:
        if os.environ.get("GOOGLE_API_KEY"):
            return "gemini"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return "offline"

    @property
    def is_available(self) -> bool:
        return self._backend != "offline"

    def enrich(self, doc: DisasterDocument) -> DisasterDocument:
        """
        Attempt to enrich a document with LLM-extracted metadata.
        Returns the document unchanged if extraction fails or is unavailable.
        """
        if not self.is_available:
            return doc

        # Only process documents that lack metadata
        if doc.hazard_types and doc.region:
            return doc  # Already has metadata

        snippet = doc.content[:2000]  # Use first 2000 chars for efficiency
        try:
            extracted = self._extract(snippet)
            if not extracted:
                return doc

            # Merge: prefer LLM results, fall back to existing values
            if extracted.get("hazard_types"):
                merged_hazards = list(
                    set(doc.hazard_types or []) | set(extracted["hazard_types"])
                )
                doc = doc.model_copy(update={"hazard_types": merged_hazards})

            if not doc.region and extracted.get("region"):
                doc = doc.model_copy(update={"region": extracted["region"]})

            if not doc.event_date and extracted.get("event_date"):
                doc = doc.model_copy(update={"event_date": extracted["event_date"]})

            if not doc.coordinates and extracted.get("coordinates"):
                coords = extracted["coordinates"]
                if isinstance(coords, list) and len(coords) == 2:
                    doc = doc.model_copy(update={"coordinates": coords})

        except Exception as e:
            logger.debug("Metadata extraction failed for %s: %s", doc.source_url, e)

        return doc

    def enrich_batch(self, docs: List[DisasterDocument]) -> List[DisasterDocument]:
        """Enrich a list of documents."""
        if not self.is_available:
            logger.info("Metadata extractor: offline mode (no API key). Using keyword extraction only.")
            return docs
        logger.info("Enriching %d documents with LLM metadata extraction ...", len(docs))
        return [self.enrich(doc) for doc in docs]

    def _extract(self, text: str) -> Optional[dict]:
        prompt = _EXTRACTION_PROMPT.format(text=text)
        raw = None

        if self._backend == "gemini":
            raw = self._call_gemini(prompt)
        elif self._backend == "openai":
            raw = self._call_openai(prompt)

        if not raw:
            return None

        # Parse JSON from response (handle markdown code blocks)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw)

    def _call_gemini(self, prompt: str) -> Optional[str]:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text

    def _call_openai(self, prompt: str) -> Optional[str]:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
