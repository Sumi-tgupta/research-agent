"""
Tests for the LlamaIndex retrieval layer. Like test_vector_store.py, these
run for real — indexing and retrieval are genuine LlamaIndex/FAISS
operations. Only the embedding model itself is swapped for a deterministic
fake, since the real one (HuggingFaceEmbedding) needs to download weights
from huggingface.co, unreachable in this project's build sandbox.
"""

import hashlib

from llama_index.core.base.embeddings.base import BaseEmbedding

from app.retrieval_index import build_retrieval_index, retrieve_supplementary_excerpts
from app.schemas import Document, SourceType


class FakeLlamaEmbedding(BaseEmbedding):
    """Deterministic hashed bag-of-words embedding implementing
    LlamaIndex's BaseEmbedding interface directly (its abstract methods
    differ from the plain Embedder protocol in vector_store.py, so this is
    a separate small fake rather than a reused one)."""

    dim: int = 64

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in text.lower().split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim
            vector[idx] += 1.0
        norm = sum(v * v for v in vector) ** 0.5 or 1.0
        return [v / norm for v in vector]

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embed(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._embed(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embed(text)


def _doc(title: str, abstract: str, url: str = "https://example.com") -> Document:
    return Document(title=title, abstract=abstract, source=SourceType.WEB, url=url)


def test_build_retrieval_index_returns_none_for_empty_documents():
    assert build_retrieval_index([], embed_model=FakeLlamaEmbedding()) is None


def test_retrieve_returns_empty_list_for_none_index():
    assert retrieve_supplementary_excerpts(None, "anything") == []


def test_retrieval_finds_the_most_relevant_document():
    docs = [
        _doc(
            "Coral bleaching",
            "Coral reefs face bleaching from rising ocean temperatures and acidification.",
        ),
        _doc(
            "Energy policy",
            "Renewable energy subsidies increased significantly across many countries.",
        ),
    ]
    index = build_retrieval_index(docs, embed_model=FakeLlamaEmbedding())

    excerpts = retrieve_supplementary_excerpts(index, "ocean temperatures coral bleaching", top_k=1)

    assert len(excerpts) == 1
    assert "Coral" in excerpts[0]


def test_retrieval_respects_top_k():
    docs = [_doc(f"Document {i} about lizards", "Lizards are reptiles.") for i in range(5)]
    index = build_retrieval_index(docs, embed_model=FakeLlamaEmbedding())

    excerpts = retrieve_supplementary_excerpts(index, "lizards", top_k=2)

    assert len(excerpts) == 2
