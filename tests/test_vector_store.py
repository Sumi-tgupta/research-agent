"""
Unlike the Phase 1 agent tests, these run for real — no mocking. FAISS and
the dedup/ranking math are all local, so the only thing swapped out is the
embedder: sentence-transformers needs to download model weights from
huggingface.co on first use, and this build sandbox can't reach that
domain. `FakeEmbedder` below is a deterministic hashed-bag-of-words
stand-in — it captures "similar text -> similar vector" well enough to
prove the VectorStore logic itself is correct. Swap in `LocalEmbedder` from
app.vector_store for the real thing once you have internet access to
download the model (a one-time ~80MB download, then it's cached locally).
"""

import numpy as np

from app.schemas import Document, SourceType
from app.vector_store import VectorStore
from tests.fakes import FakeEmbedder


def _doc(title: str, abstract: str = "", url: str = "https://example.com") -> Document:
    return Document(title=title, abstract=abstract, source=SourceType.WEB, url=url)


# ---------------------------------------------------------------- Dedup

def test_dedup_keeps_clearly_distinct_documents():
    store = VectorStore(FakeEmbedder())
    docs = [
        _doc("Transformer architectures for language modeling", "Attention mechanisms in deep learning."),
        _doc("Photosynthesis in C4 plants", "Carbon fixation pathways in tropical grasses."),
    ]
    assert len(store.add_and_dedupe(docs)) == 2


def test_dedup_drops_near_duplicate_added_later():
    store = VectorStore(FakeEmbedder())
    original = _doc(
        "Attention is all you need for sequence modeling",
        "We propose the Transformer a model architecture based on attention mechanisms",
    )
    near_duplicate = _doc(
        "Attention is all you need for sequence modeling",
        "We propose the Transformer a model architecture based on attention mechanisms alone",
    )
    unrelated = _doc("Soil microbiome diversity in temperate forests", "A survey of fungal communities.")

    assert len(store.add_and_dedupe([original])) == 1
    second_batch_kept = store.add_and_dedupe([near_duplicate, unrelated])

    assert len(second_batch_kept) == 1
    assert second_batch_kept[0].title == "Soil microbiome diversity in temperate forests"


def test_dedup_catches_duplicates_within_the_same_batch():
    store = VectorStore(FakeEmbedder())
    dup_title = "Reinforcement learning from human feedback for large language models"
    docs = [
        _doc(dup_title, "A survey of RLHF techniques."),
        _doc(dup_title, "A survey of RLHF techniques."),
        _doc("Coral reef bleaching under ocean acidification", "Marine biology field study."),
    ]
    assert len(store.add_and_dedupe(docs)) == 2


def test_dedup_threshold_is_configurable():
    store = VectorStore(FakeEmbedder())
    store.add_and_dedupe([_doc("Quantum error correction surface codes", "Fault tolerant quantum computing.")])
    somewhat_similar = _doc("Quantum error correction using codes", "Fault tolerant computing approaches.")

    # A very strict threshold should NOT treat this as a duplicate...
    kept_strict = store.add_and_dedupe([somewhat_similar], similarity_threshold=0.999)
    assert len(kept_strict) == 1


# ---------------------------------------------------------------- Ranking

def test_relevance_ranking_orders_by_similarity_to_query():
    store = VectorStore(FakeEmbedder())
    on_topic = _doc(
        "Retrieval augmented generation for open domain question answering",
        "Combines a retriever with a generator to ground language model outputs in documents.",
    )
    off_topic = _doc(
        "Sourdough bread fermentation chemistry",
        "How wild yeast and lactic acid bacteria interact during proofing.",
    )

    ranked = store.rank_by_relevance(
        "retrieval augmented generation for question answering",
        [off_topic, on_topic],  # deliberately passed in the "wrong" order
    )

    assert ranked[0].title == on_topic.title
    assert ranked[0].relevance_score > ranked[1].relevance_score


def test_relevance_ranking_respects_top_k():
    store = VectorStore(FakeEmbedder())
    docs = [_doc(f"Document number {i} about lizards") for i in range(5)]
    assert len(store.rank_by_relevance("lizards", docs, top_k=2)) == 2


def test_relevance_ranking_handles_empty_input():
    store = VectorStore(FakeEmbedder())
    assert store.rank_by_relevance("anything", []) == []
