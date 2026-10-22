"""
Content-hash and URL-based deduplication for scraped documents.
Provides detailed diagnostic counters for URL duplicates, content-hash duplicates,
invalid documents, and genuinely new documents.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from processor.validator import DisasterDocument

logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Tracks seen content hashes to avoid storing duplicate documents.
    Also tracks seen source URLs to avoid duplicate storage.
    Maintains diagnostic counters for all processed items.
    """

    def __init__(
        self,
        seen_hashes: Optional[Set[str]] = None,
        seen_urls: Optional[Set[str]] = None,
    ):
        self._hashes: Set[str] = seen_hashes or set()
        self._urls: Set[str] = seen_urls or set()
        self.stats: Dict[str, int] = {
            "total_checked": 0,
            "genuinely_new": 0,
            "url_duplicates": 0,
            "hash_duplicates": 0,
            "invalid_documents": 0,
        }

    @classmethod
    def from_jsonl(cls, path: Path) -> "Deduplicator":
        """Load existing hashes and URLs from a JSONL file."""
        hashes: Set[str] = set()
        urls: Set[str] = set()
        if not path.exists():
            return cls(hashes, urls)

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if h := obj.get("content_hash"):
                        hashes.add(h)
                    if u := obj.get("source_url"):
                        urls.add(u)
                except json.JSONDecodeError:
                    continue

        logger.info(
            "Deduplicator loaded %d hashes, %d URLs from %s",
            len(hashes),
            len(urls),
            path,
        )
        return cls(hashes, urls)

    def check_duplicate(self, doc: DisasterDocument) -> Tuple[bool, str]:
        """
        Check if a document is a duplicate and return the exact reason.

        Returns
        -------
        Tuple[bool, str]
            (is_duplicate, reason)
            reason is one of:
              - 'url_duplicate': source_url has already been seen
              - 'hash_duplicate': content_hash has already been seen with another URL
              - 'new': document is genuinely new
        """
        if not isinstance(doc, DisasterDocument):
            return True, "invalid"

        if doc.source_url in self._urls:
            return True, "url_duplicate"

        if doc.content_hash in self._hashes:
            return True, "hash_duplicate"

        return False, "new"

    def is_duplicate(self, doc: DisasterDocument) -> bool:
        """Return True if this document's content or URL was already seen."""
        is_dup, _ = self.check_duplicate(doc)
        return is_dup

    def register(self, doc: DisasterDocument) -> None:
        """Mark a document as seen."""
        self._hashes.add(doc.content_hash)
        self._urls.add(doc.source_url)

    def reset_stats(self) -> None:
        """Reset the diagnostic counters."""
        self.stats = {
            "total_checked": 0,
            "genuinely_new": 0,
            "url_duplicates": 0,
            "hash_duplicates": 0,
            "invalid_documents": 0,
        }

    def filter_new(self, docs: List[DisasterDocument]) -> List[DisasterDocument]:
        """
        Filter a list of documents, keeping only genuinely new ones.
        Updates and logs diagnostic counts for:
          - genuinely_new
          - url_duplicates
          - hash_duplicates
          - invalid_documents
        """
        self.reset_stats()
        new_docs: List[DisasterDocument] = []

        for doc in docs:
            self.stats["total_checked"] += 1

            if not isinstance(doc, DisasterDocument):
                self.stats["invalid_documents"] += 1
                logger.warning("Skipping invalid document object: %r", doc)
                continue

            is_dup, reason = self.check_duplicate(doc)
            if is_dup:
                if reason == "url_duplicate":
                    self.stats["url_duplicates"] += 1
                    logger.debug("Duplicate URL skipped: %s", doc.source_url)
                elif reason == "hash_duplicate":
                    self.stats["hash_duplicates"] += 1
                    logger.debug(
                        "Duplicate content-hash skipped for URL %s (hash: %s)",
                        doc.source_url,
                        doc.content_hash[:12],
                    )
            else:
                self.register(doc)
                new_docs.append(doc)
                self.stats["genuinely_new"] += 1

        logger.info(
            "Deduplication summary: %d total checked | %d genuinely new | "
            "%d URL duplicates | %d content-hash duplicates | %d invalid",
            self.stats["total_checked"],
            self.stats["genuinely_new"],
            self.stats["url_duplicates"],
            self.stats["hash_duplicates"],
            self.stats["invalid_documents"],
        )
        return new_docs
