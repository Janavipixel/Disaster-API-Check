"""
ChromaDB persistent vector store wrapper.

Stores chunk embeddings and metadata. Supports:
  - Adding chunks (upsert, so re-indexing is safe)
  - Similarity search by query text or pre-computed embedding
  - Metadata filtering (by hazard type, region, etc.)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rag.chunker import Chunk
from rag.embedder import Embedder

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "disaster_intelligence"
DEFAULT_PERSIST_DIR = os.environ.get(
    "CHROMA_PERSIST_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "chroma_db"),
)


class VectorStore:
    """
    Wrapper around ChromaDB for persistent chunk storage and retrieval.

    Parameters
    ----------
    persist_dir : str | Path
        Directory where ChromaDB stores its data.
    collection_name : str
        Name of the ChromaDB collection.
    embedder : Embedder
        Shared embedder instance.
    """

    def __init__(
        self,
        embedder: Embedder,
        persist_dir: str | Path = DEFAULT_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION,
    ):
        self.embedder = embedder
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init(self):
        if self._client is not None:
            return
        import chromadb  # type: ignore
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB collection '%s' ready. Documents: %d",
            self.collection_name,
            self._collection.count(),
        )

    @property
    def collection(self):
        self._init()
        return self._collection

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_chunks(self, chunks: List[Chunk], batch_size: int = 100) -> int:
        """
        Embed and upsert chunks into ChromaDB.

        Returns
        -------
        int
            Number of chunks upserted.
        """
        if not chunks:
            return 0

        total = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]
            ids = [c.chunk_id for c in batch]
            metadatas = [c.to_metadata() for c in batch]
            embeddings = self.embedder.embed(texts)

            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            total += len(batch)
            logger.debug("Upserted batch %d/%d (%d chunks)", i // batch_size + 1, -(-len(chunks) // batch_size), len(batch))

        logger.info("Upserted %d chunks into '%s'", total, self.collection_name)
        return total

    # ── Read ──────────────────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Retrieve the top-n most relevant chunks for a query.

        Parameters
        ----------
        query_text : str
            The user's question or search string.
        n_results : int
            Number of chunks to return.
        where : dict | None
            Optional ChromaDB metadata filter, e.g. {"region": "Bangladesh"}.

        Returns
        -------
        List[Dict]
            Each dict has: chunk_id, text, metadata, distance, relevance_score.
        """
        query_embedding = self.embedder.embed_one(query_text)

        kwargs: Dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, self.collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)

        output = []
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to a 0-1 relevance score
            relevance = max(0.0, 1.0 - dist / 2.0)
            output.append(
                {
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": meta,
                    "distance": dist,
                    "relevance_score": round(relevance, 4),
                }
            )
        return output

    def count(self) -> int:
        """Return the total number of chunks in the collection."""
        return self.collection.count()

    def clear(self) -> None:
        """Delete the entire collection (use with caution)."""
        if self._client:
            self._client.delete_collection(self.collection_name)
            self._collection = None
            logger.warning("Collection '%s' cleared.", self.collection_name)
