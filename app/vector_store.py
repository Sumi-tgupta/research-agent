"""
Vector Store — FAISS-backed deduplication and relevance ranking.

Embeddings are computed locally (sentence-transformers), not via an API, so
this adds no rate-limit pressure on the free-tier LLM keys and needs no key
of its own. The embedder is injected (see `Embedder` protocol below) so
tests can swap in a fake, deterministic embedder and run for real —
sentence-transformers downloads model weights from huggingface.co on first
use, which this project's build sandbox couldn't reach, so that path is
verified by shape/logic here and needs a live check in your environment
(see scripts/run_pipeline.py).

Two things this does:
  1. `add_and_dedupe` — skips documents that are near-duplicates of ones
     already seen (e.g. the same paper turning up via both ArXiv and
     Semantic Scholar, or the same page across two sub-questions).
  2. `rank_by_relevance` — scores every document against the *original*
     research question on one consistent scale. This matters because a web
     result's score and Semantic Scholar's fields aren't comparable to each
     other, but cosine similarity to the same query is.
"""

from typing import Protocol

import faiss
import numpy as np

from app.schemas import Document

DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD = 0.90


class Embedder(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Returns an (n, dimension) float32 array, L2-normalized so inner
        product == cosine similarity."""
        ...


from app.embedding_service import LocalEmbedder, get_default_embedder


def _doc_text(doc: Document) -> str:
    body = doc.abstract or doc.snippet or ""
    return f"{doc.title}. {body}".strip()


class VectorStore:
    def __init__(self, embedder: Embedder | None = None):
        self._embedder = embedder if embedder is not None else get_default_embedder()
        self._index = faiss.IndexFlatIP(self._embedder.dimension)
        self.documents: list[Document] = []  # parallel to index rows

    def add_and_dedupe(
        self,
        documents: list[Document],
        similarity_threshold: float = DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
    ) -> list[Document]:
        """Adds documents that aren't near-duplicates of something already
        in the store (including earlier documents in this same call).
        Returns just the documents actually kept."""
        if not documents:
            return []

        vectors = self._embedder.embed([_doc_text(d) for d in documents])
        kept: list[Document] = []

        for doc, vector in zip(documents, vectors):
            row = vector.reshape(1, -1)
            is_duplicate = False
            if self._index.ntotal > 0:
                similarities, _ = self._index.search(row, k=1)
                is_duplicate = bool(similarities[0][0] >= similarity_threshold)
            if not is_duplicate:
                self._index.add(row)
                self.documents.append(doc)
                kept.append(doc)

        return kept

    def rank_by_relevance(
        self,
        query: str,
        documents: list[Document],
        top_k: int | None = None,
    ) -> list[Document]:
        """Sets each document's `relevance_score` to its cosine similarity
        with `query` (overwriting any source-native score) and returns them
        sorted best-first, optionally truncated to `top_k`."""
        if not documents:
            return []

        query_vector = self._embedder.embed([query])[0]
        doc_vectors = self._embedder.embed([_doc_text(d) for d in documents])

        for doc, vector in zip(documents, doc_vectors):
            doc.relevance_score = float(np.dot(query_vector, vector))

        ranked = sorted(documents, key=lambda d: d.relevance_score, reverse=True)
        return ranked[:top_k] if top_k else ranked
