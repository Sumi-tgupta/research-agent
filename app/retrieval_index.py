"""
LlamaIndex-backed retrieval over the full set of retrieved documents — used
by the Writer to pull supplementary supporting excerpts beyond what the
Fact Checker extracted as discrete claims (specific numbers, methodology
details, or other nuance that's useful for writing but didn't rise to the
level of a standalone verified claim).

This is a nice-to-have layered on top of verified_claims, not a
replacement for it: everything the Writer treats as an established fact
still comes from Phase 3's fact-checked claims. Supplementary excerpts are
framed to the Writer as unverified background color, not verified fact
(see agents/writer_agent.py's prompt).

Uses the same kind of local embedding model as vector_store.py — a
separate loaded instance (see the note in graph.py about why these aren't
shared across nodes yet), so this adds no API dependency of its own beyond
the one-time model download.
"""

import faiss
from llama_index.core import Document as LlamaDocument
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.vector_stores.faiss import FaissVectorStore

from app.schemas import Document

DEFAULT_EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _default_embed_model() -> BaseEmbedding:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # lazy:
    # avoid requiring torch just to import this module when a fake
    # embed_model is injected for testing.

    return HuggingFaceEmbedding(model_name=DEFAULT_EMBEDDING_MODEL_NAME)


def build_retrieval_index(
    documents: list[Document],
    embed_model: BaseEmbedding | None = None,
) -> VectorStoreIndex | None:
    """Returns None if there's nothing to index. Raises if the embedding
    model can't be loaded (e.g. no internet on first run) — callers should
    catch that and treat it as "no supplementary excerpts available", not
    a reason to fail the whole Writer stage."""
    if not documents:
        return None

    model = embed_model or _default_embed_model()
    # Derived from the actual model in use (not hardcoded) so this works
    # correctly whether it's the real ~384-dim model or a fake test embedder.
    dimension = len(model.get_query_embedding("dimension probe"))

    llama_docs = [
        LlamaDocument(
            text=f"{doc.title}. {doc.abstract or doc.snippet or ''}",
            metadata={"title": doc.title, "url": doc.url, "sub_question": doc.sub_question or ""},
        )
        for doc in documents
    ]

    storage_context = StorageContext.from_defaults(vector_store=FaissVectorStore(faiss_index=faiss.IndexFlatIP(dimension)))
    return VectorStoreIndex.from_documents(llama_docs, storage_context=storage_context, embed_model=model)


def retrieve_supplementary_excerpts(index: VectorStoreIndex | None, query: str, top_k: int = 3) -> list[str]:
    """Empty list if there's no index (nothing to retrieve from), rather
    than raising — this is supplementary for the Writer, never required."""
    if index is None:
        return []
    nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    return [node.get_content() for node in nodes]
