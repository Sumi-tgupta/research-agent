"""Unit tests for the enterprise embedding service singleton manager."""

from app.embedding_service import get_default_embedder, reset_default_embedder, LocalEmbedder
from tests.fakes import FakeEmbedder


def test_reset_default_embedder():
    reset_default_embedder()
    from app.embedding_service import _cached_embedder
    assert _cached_embedder is None


def test_vector_store_default_embedder_fallback():
    from app.vector_store import VectorStore
    fake = FakeEmbedder()
    store = VectorStore(embedder=fake)
    assert store._embedder == fake
