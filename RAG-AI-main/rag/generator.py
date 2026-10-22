"""
RAG Answer Generator.

Takes retrieved chunks and a user question, builds a grounded prompt,
and calls an LLM to produce an evidence-based answer with source citations.

Supports:
  - Google Gemini   (GOOGLE_API_KEY)
  - OpenAI GPT      (OPENAI_API_KEY)
  - Offline fallback (no API key — returns formatted context with clean guidance)

The system works without any API key in offline/demo mode.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt template
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior disaster intelligence analyst specialising in satellite imagery, \
SAR (Synthetic Aperture Radar), flood mapping, change detection, and humanitarian response. \
Answer the user's question using ONLY the provided verified satellite observations and source documents. \
Strict rules:
1. Answer using ONLY facts explicitly stated in the provided documents and verified satellite observations.
2. Differentiate between:
   - Verified Copernicus Satellite Observations: high-authority physical instrument measurements (backscatter change, delineated flood area in km², priority inspection zones). Cite as [SATELLITE: Copernicus Sentinel-1].
   - External Reports: news, GDACS, and ReliefWeb situation reports. Cite as [SOURCE N].
3. If the documents and satellite data do not contain enough information to answer confidently, \
say so clearly ("Insufficient evidence in provided data") — do NOT extrapolate, invent coordinates, \
speculate on damage extents, or guess casualty counts.
4. When source documents present conflicting or varying reports (e.g. differing fatality counts, \
discrepant affected population figures, conflicting dates, or differing flood extents), \
you must explicitly highlight the disagreement, report the differing figures with their respective \
source citations, and NOT arbitrarily choose or guess which one is correct.
5. Corroborate external reports with satellite measurements where possible (e.g., comparing reported flood boundaries against satellite delineated km²).
6. Be concise, precise, and technically accurate."""

USER_PROMPT_TEMPLATE = """\
{satellite_section}

## Retrieved Source Documents

{context}

## Operational Request Context
{operational_context}

## Question

{question}

## Instructions

Answer the question using the verified satellite observations and source documents above. \
Reference specific external sources with [SOURCE N] and satellite data with [SATELLITE: Copernicus Sentinel-1]. \
If the sources provide conflicting facts, figures, or dates, explicitly state the conflict \
and attribute each figure to its source rather than choosing one. \
If the evidence is insufficient to answer completely, acknowledge the limitations clearly. \
End your answer with a "## Sources" section listing each cited source's title and URL.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Response dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RAGResponse:
    question: str
    answer: str
    sources: List[dict]          # [{title, url, relevance_score, chunk_id}]
    model_used: str
    chunk_count: int
    offline_mode: bool = False
    error: Optional[str] = None
    cited_sources: List[dict] = field(default_factory=list)
    uncertainty_or_limitations: Optional[str] = None

    def display(self) -> str:
        """Formatted string for terminal display (safe for all console encodings)."""
        divider = "=" * 70
        source_lines = "\n".join(
            f"  [{i+1}] {s['title']}\n      {s['url']}"
            for i, s in enumerate(self.sources)
        )
        if not source_lines:
            source_lines = "  (No sources retrieved)"

        uncertainty_block = ""
        if self.uncertainty_or_limitations:
            uncertainty_block = f"\n[!] UNCERTAINTY & LIMITATIONS:\n{self.uncertainty_or_limitations}\n"

        mode_str = "[OFFLINE MODE] No LLM called" if self.offline_mode else f"[MODEL: {self.model_used}]"
        return (
            f"\n{divider}\n"
            f"[QUESTION] {self.question}\n\n"
            f"{mode_str}\n"
            f"{divider}\n"
            f"[ANSWER]\n\n{self.answer}\n"
            f"{uncertainty_block}\n"
            f"[SOURCES] ({self.chunk_count} chunks retrieved)\n{source_lines}\n"
            f"{divider}\n"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Generator
# ─────────────────────────────────────────────────────────────────────────────

class Generator:
    """
    Wraps LLM calls for the RAG answer generation step.

    Auto-selects backend based on available API keys:
      1. Google Gemini  (GOOGLE_API_KEY)
      2. OpenAI GPT     (OPENAI_API_KEY)
      3. Offline mode   (no key — returns context without LLM)
    """

    def __init__(self, model: Optional[str] = None):
        self._model_override = model
        self._backend, self._model_name = self._detect_backend()

    # ── Backend detection ─────────────────────────────────────────────────────

    def _detect_backend(self):
        if os.environ.get("GOOGLE_API_KEY"):
            model = self._model_override or "gemini-1.5-flash"
            logger.info("Generator: using Google Gemini (%s)", model)
            return "gemini", model

        if os.environ.get("OPENAI_API_KEY"):
            model = self._model_override or "gpt-4o-mini"
            logger.info("Generator: using OpenAI (%s)", model)
            return "openai", model

        logger.info(
            "Generator: no API key found — running in OFFLINE mode. "
            "Set GOOGLE_API_KEY or OPENAI_API_KEY in .env to enable LLM answers."
        )
        return "offline", "offline"

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        question: str,
        chunks: List[dict],
        context: str,
        disaster_context: Optional[dict] = None,
        satellite_evidence: Optional[Any] = None,
    ) -> RAGResponse:
        """
        Generate a grounded answer with citations, satellite evidence, and uncertainty handling.

        Parameters
        ----------
        question : str
            The user's question.
        chunks : List[dict]
            Retrieved chunks (from Retriever.retrieve).
        context : str
            Pre-formatted context string (from Retriever.format_context).
        disaster_context : Optional[dict]
            Operational context from satellite or disaster feed (e.g. Copernicus).
        satellite_evidence : Optional[Any]
            Verified SatelliteEvidence instance from the satellite processing pipeline.

        Returns
        -------
        RAGResponse
            Structured response with answer, sources, and metadata.
        """
        sources = self._extract_sources(chunks)

        # Include satellite evidence as a top-level verified source if present
        sat_section = ""
        if satellite_evidence:
            sat_section = (
                satellite_evidence.to_context_string()
                if hasattr(satellite_evidence, "to_context_string")
                else str(satellite_evidence)
            )
            sat_url = "https://documentation.dataspace.copernicus.eu/"
            sat_name = getattr(satellite_evidence, "event_name", "Copernicus Sentinel-1 SAR Observation")
            sources.insert(0, {
                "title": f"Copernicus Sentinel-1 SAR — {sat_name}",
                "url": sat_url,
                "relevance_score": 1.0,
                "chunk_id": f"sat_{getattr(satellite_evidence, 'event_id', 'sar')}",
            })

        # Empty retrieval & no satellite data handling
        if not chunks and not satellite_evidence:
            empty_msg = (
                "Insufficient evidence in the knowledge base or satellite observation stream "
                "to answer this question. No relevant disaster records or technical documentation were retrieved. "
                "Please verify that the scraper has run and indexed the required topics."
            )
            return RAGResponse(
                question=question,
                answer=empty_msg,
                sources=[],
                model_used=self._model_name if self._backend != "offline" else "offline",
                chunk_count=0,
                offline_mode=self._backend == "offline",
                uncertainty_or_limitations="Zero relevant document chunks or satellite observations available.",
            )

        op_ctx_str = "None provided."
        if disaster_context:
            op_ctx_str = "\n".join(f"- {k}: {v}" for k, v in disaster_context.items())

        combined_offline_context = context
        if sat_section:
            combined_offline_context = f"{sat_section}\n\n{context}"

        if self._backend == "offline":
            answer = self._offline_answer(combined_offline_context)
            uncertainty = self._detect_uncertainties(answer, chunks)
            return RAGResponse(
                question=question,
                answer=answer,
                sources=sources,
                model_used="offline",
                chunk_count=len(chunks),
                offline_mode=True,
                cited_sources=sources,
                uncertainty_or_limitations=uncertainty,
            )

        full_prompt = USER_PROMPT_TEMPLATE.format(
            satellite_section=sat_section or "## Verified Copernicus Satellite Observations\nNo direct satellite overpass data provided for this query.",
            context=context,
            operational_context=op_ctx_str,
            question=question,
        )

        error_msg = None
        answer = ""
        try:
            if self._backend == "gemini":
                answer = self._call_gemini(full_prompt)
            elif self._backend == "openai":
                answer = self._call_openai(full_prompt)
            else:
                answer = combined_offline_context
        except Exception as exc:
            logger.error("LLM API call failed: %s", exc)
            error_msg = str(exc)
            # Graceful fallback to formatted context
            answer = (
                f"[OFFLINE FALLBACK] LLM Generation Unavailable ({exc}).\n\n"
                f"Operating in offline evidence mode. Below are the verified source documents "
                f"and satellite observations for your question:\n\n{combined_offline_context}"
            )

        cited_sources = self._extract_cited_sources(answer, sources)
        uncertainty = self._detect_uncertainties(answer, chunks)

        return RAGResponse(
            question=question,
            answer=answer,
            sources=sources,
            model_used=self._model_name,
            chunk_count=len(chunks),
            offline_mode=bool(error_msg),
            error=error_msg,
            cited_sources=cited_sources or sources,
            uncertainty_or_limitations=uncertainty,
        )

    # ── LLM backends ──────────────────────────────────────────────────────────

    def _call_gemini(self, prompt: str) -> str:
        import google.generativeai as genai  # type: ignore
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is not set.")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(prompt)
        if response.text:
            return response.text.strip()
        return "Gemini returned an empty response."

    def _call_openai(self, prompt: str) -> str:
        from openai import OpenAI  # type: ignore
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self._model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        content = response.choices[0].message.content
        if content:
            return content.strip()
        return "OpenAI returned an empty response."

    def _offline_answer(self, context: str) -> str:
        return (
            "[OFFLINE MODE] No LLM API key configured.\n\n"
            "The following source documents were retrieved from the knowledge base "
            "and are relevant to your question. Set GOOGLE_API_KEY or OPENAI_API_KEY "
            "in your .env file to get an AI-generated answer.\n\n"
            "--- RETRIEVED CONTEXT ---\n\n"
            + context
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_sources(chunks: List[dict]) -> List[dict]:
        """Deduplicate sources from retrieved chunks."""
        seen_urls = set()
        sources = []
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            url = meta.get("source_url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                sources.append(
                    {
                        "title": meta.get("title", "Unknown"),
                        "url": url,
                        "relevance_score": chunk.get("relevance_score", 0),
                        "chunk_id": chunk.get("chunk_id", ""),
                    }
                )
        return sources

    @staticmethod
    def _extract_cited_sources(answer: str, sources: List[dict]) -> List[dict]:
        """Identify which sources were explicitly referenced by [SOURCE N] in the answer."""
        matches = re.findall(r"\[SOURCE\s*(\d+)\]", answer, re.IGNORECASE)
        cited_indices = set()
        for m in matches:
            try:
                idx = int(m) - 1
                if 0 <= idx < len(sources):
                    cited_indices.add(idx)
            except ValueError:
                pass
        if not cited_indices:
            return sources
        return [sources[i] for i in sorted(cited_indices)]

    @staticmethod
    def _detect_uncertainties(answer: str, chunks: List[dict]) -> Optional[str]:
        """Detect any uncertainty, missing evidence, or conflicting reports."""
        notes = []
        answer_lower = answer.lower()
        if any(term in answer_lower for term in ["insufficient evidence", "do not contain enough", "not mentioned in", "unclear from", "does not specify"]):
            notes.append("The retrieved evidence does not fully cover all aspects of the query.")
        if any(term in answer_lower for term in ["conflict", "discrepanc", "differing", "disagree", "varies between"]):
            notes.append("Conflicting reports or discrepant figures were detected across sources.")
        if chunks and all(c.get("relevance_score", 0.0) < 0.35 for c in chunks):
            notes.append("Low overall semantic similarity between the question and stored documents.")
        return " | ".join(notes) if notes else None

