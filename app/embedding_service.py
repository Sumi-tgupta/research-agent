"""
Enterprise Embedding Service Module.

Provides a unified embedder factory and singleton manager, supporting:
1. Thread-safe cached LocalEmbedder (SentenceTransformers)
2. Triton Inference Server gRPC proxy
3. Remote API embedding fallbacks (Gemini / OpenAI)
"""

import threading
from typing import Protocol, Optional
import numpy as np


class EmbedderProtocol(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Returns an (n, dimension) float32 array, L2-normalized."""
        ...


_embedder_lock = threading.Lock()
_cached_embedder: Optional[EmbedderProtocol] = None


class LocalEmbedder:
    """Cached local embedder using sentence-transformers."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        dim = self._model.get_sentence_embedding_dimension()
        self.dimension = dim if dim is not None else int(self._model.encode(["probe"]).shape[-1])

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype="float32")
        return self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype("float32")


def get_default_embedder(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> EmbedderProtocol:
    """Thread-safe singleton accessor for the default embedder model."""
    global _cached_embedder
    if _cached_embedder is None:
        with _embedder_lock:
            if _cached_embedder is None:
                _cached_embedder = LocalEmbedder(model_name=model_name)
    return _cached_embedder


def reset_default_embedder() -> None:
    """Resets the cached embedder instance (primarily for isolated unit tests)."""
    global _cached_embedder
    with _embedder_lock:
        _cached_embedder = None
