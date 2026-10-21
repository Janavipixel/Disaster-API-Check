"""
Text chunker for the RAG pipeline.

Splits long documents into overlapping chunks suitable for embedding.
Preserves sentence boundaries where possible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class Chunk:
    """A single text chunk ready for embedding."""
    chunk_id: str           # "{document_id}_chunk_{index}"
    document_id: str
    text: str
    chunk_index: int
    total_chunks: int
    source_url: str
    title: str
    publisher: str | None = None
    hazard_types: List[str] = field(default_factory=list)
    region: str | None = None
    event_date: str | None = None
    published_at: str | None = None
    tags: List[str] = field(default_factory=list)

    def to_metadata(self) -> dict:
        """Serialise chunk metadata for ChromaDB (string/int/float/bool only)."""
        return {
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "source_url": self.source_url,
            "title": self.title,
            "publisher": self.publisher or "",
            "hazard_types": ",".join(self.hazard_types),
            "region": self.region or "",
            "event_date": self.event_date or "",
            "published_at": self.published_at or "",
            "tags": ",".join(self.tags),
        }


# ─── Sentence splitter (no NLTK needed) ──────────────────────────────────────
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences using punctuation heuristics."""
    return _SENT_BOUNDARY.split(text.strip())


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> List[str]:
    """
    Split text into overlapping chunks of approximately `chunk_size` words.

    Strategy:
      1. Split into sentences.
      2. Greedily accumulate sentences until chunk_size is reached.
      3. Back up `overlap` words for the next chunk.

    Parameters
    ----------
    text : str
        The full document text.
    chunk_size : int
        Target number of words per chunk.
    overlap : int
        Number of words to repeat at the start of the next chunk.

    Returns
    -------
    List[str]
        List of text chunks.
    """
    if not text.strip():
        return []

    sentences = _split_sentences(text)
    chunks: List[str] = []
    current_words: List[str] = []

    for sentence in sentences:
        s_words = sentence.split()
        if not s_words:
            continue

        # If a single sentence exceeds chunk_size, split it into word-level chunks
        if len(s_words) > chunk_size:
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = current_words[-overlap:] if overlap > 0 else []

            step = max(1, chunk_size - overlap)
            idx = 0
            while idx < len(s_words):
                end_idx = idx + chunk_size
                chunk_slice = s_words[idx:end_idx]
                if end_idx >= len(s_words):
                    current_words = chunk_slice
                    break
                chunks.append(" ".join(chunk_slice))
                idx += step
            continue

        # If adding this sentence exceeds chunk_size, flush
        if len(current_words) + len(s_words) > chunk_size and current_words:
            chunks.append(" ".join(current_words))
            # Overlap: keep last `overlap` words
            current_words = current_words[-overlap:] if overlap > 0 else []

        current_words.extend(s_words)

    # Flush remainder
    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def chunk_document(doc, chunk_size: int = 512, overlap: int = 64) -> List[Chunk]:
    """
    Chunk a DisasterDocument into Chunk objects with full metadata.

    Parameters
    ----------
    doc : DisasterDocument
        A validated scraper document.
    chunk_size : int
        Target words per chunk.
    overlap : int
        Word overlap between consecutive chunks.
    """
    text_parts = chunk_text(doc.content, chunk_size=chunk_size, overlap=overlap)

    if not text_parts:
        return []

    total = len(text_parts)
    chunks: List[Chunk] = []

    for i, text in enumerate(text_parts):
        chunk_id = f"{doc.document_id}_chunk_{i:04d}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_id=doc.document_id,
                text=text,
                chunk_index=i,
                total_chunks=total,
                source_url=doc.source_url,
                title=doc.title,
                publisher=doc.publisher,
                hazard_types=doc.hazard_types,
                region=doc.region,
                event_date=doc.event_date,
                published_at=doc.published_at,
                tags=doc.tags,
            )
        )
    return chunks


def chunk_documents(docs, chunk_size: int = 512, overlap: int = 64) -> List[Chunk]:
    """Chunk multiple documents."""
    all_chunks: List[Chunk] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc, chunk_size=chunk_size, overlap=overlap))
    return all_chunks
