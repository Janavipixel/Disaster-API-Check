"""
Embedding generator using sentence-transformers (runs fully offline, no API key).

Default model: all-MiniLM-L6-v2 — fast, small, good quality for semantic search.
Model is cached locally after the first download (~90 MB).
"""

from __future__ import annotations

import logging
import os
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
DEFAULT_DEVICE = os.environ.get("EMBEDDING_DEVICE", "cpu")
DEFAULT_BATCH_SIZE = 32


class Embedder:
    """
    Wraps sentence-transformers SentenceTransformer for batch embedding.

    Parameters
    ----------
    model_name : str
        HuggingFace model name. Default: all-MiniLM-L6-v2.
    device : str
        'cpu' or 'cuda'. Default: cpu.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = DEFAULT_DEVICE,
    ):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load(self):
        if self._model is None:
            logger.info("Loading embedding model '%s' on %s ...", self.model_name, self.device)
            from sentence_transformers import SentenceTransformer  # type: ignore
            try:
                self._model = SentenceTransformer(self.model_name, device=self.device)
            except Exception as exc:
                logger.warning(
                    "Standard load of '%s' failed (%s). Retrying with local_files_only=True ...",
                    self.model_name,
                    exc,
                )
                try:
                    self._model = SentenceTransformer(
                        self.model_name, device=self.device, local_files_only=True
                    )
                except Exception:
                    raise exc
            logger.info("Embedding model loaded. Dimension: %d", self.dimension)

    @property
    def dimension(self) -> int:
        self._load()
        if hasattr(self._model, "get_embedding_dimension"):
            return self._model.get_embedding_dimension()
        return self._model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str], batch_size: int = DEFAULT_BATCH_SIZE) -> List[List[float]]:
        """
        Embed a list of strings. Returns a list of float vectors.

        Parameters
        ----------
        texts : List[str]
            Text strings to embed.
        batch_size : int
            Number of texts per forward pass.

        Returns
        -------
        List[List[float]]
            One embedding vector per input text.
        """
        if not texts:
            return []
        self._load()
        logger.debug("Embedding %d texts (batch=%d) ...", len(texts), batch_size)
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 50,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def embed_one(self, text: str) -> List[float]:
        """Embed a single string."""
        return self.embed([text])[0]
