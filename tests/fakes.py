"""Shared deterministic test doubles — no network, no live API calls."""

import hashlib

import numpy as np
import requests


class FakeEmbedder:
    """Deterministic hashed bag-of-words 'embedding'. Stands in for
    sentence-transformers, which downloads model weights from
    huggingface.co on first use — unreachable in this project's build
    sandbox. Uses hashlib (not the built-in hash(), which Python
    randomizes per process) so results are identical on every run."""

    dimension = 64

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype="float32")
        for i, text in enumerate(texts):
            for word in text.lower().split():
                digest = hashlib.md5(word.encode()).hexdigest()
                vectors[i, int(digest, 16) % self.dimension] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vectors / norms).astype("float32")


class FakeResponse:
    """Stand-in for requests.Response — raises like the real thing on 4xx/5xx
    so error-handling paths (e.g. Semantic Scholar 429) are exercised
    correctly instead of silently no-op'ing."""

    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._payload


class FakeSearchProvider:
    """Test double for a SearchAgent web-search provider. Configurable to
    return documents, return nothing, raise, or report itself unconfigured —
    which is everything the agent's ordering / fallback / skip logic branches
    on. Records how many times `search` was actually called so tests can prove
    a provider was (or wasn't) reached."""

    def __init__(
        self,
        name="fake",
        *,
        requires_key=False,
        configured=True,
        documents=None,
        error=None,
    ):
        self.name = name
        self.requires_key = requires_key
        self._configured = configured
        self._documents = documents if documents is not None else []
        self._error = error
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def search(self, query, max_results, timeout):
        self.calls += 1
        if self._error is not None:
            raise self._error
        # Fresh Document instances each call, like a real provider — the graph
        # mutates doc.sub_question per sub-question, so callers must not share
        # one object across calls.
        return [doc.model_copy() for doc in self._documents]
