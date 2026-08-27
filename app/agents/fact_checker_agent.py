"""
Fact Checker Agent — cross-references claims relevant to a sub-question
against the sources retrieved for it, flags disagreement between sources,
and derives a confidence signal from how many independent sources agree.

There's no draft to check yet at this point in the pipeline (Writer is
Phase 4) — this checks the *sources* against each other before writing
starts, so the Writer works from claims that are already attributed and
flagged for disagreement, rather than raw undifferentiated documents.

This is the highest hallucination-risk stage in the project plan, so the
LLM's job is deliberately narrow: extract candidate claims and say which
numbered source supports/contradicts each one. Everything downstream of
that — the verdict (corroborated / single-source / contradicted /
unverified) and the numeric confidence — is computed in plain Python from
those counts, not asked of the LLM. That keeps the one thing we can't
verify (does source N actually say this?) as small as possible, and makes
the parts we can verify auditable and unit-testable without a live model.

A lightweight second check ("groundedness") reuses the local embeddings
from vector_store.py to catch a specific, different failure mode: the LLM
citing a source that doesn't actually seem to discuss the claim. It's a
sanity net on top of the LLM's own attribution, not a replacement for it.

Hardening (Phase 7): the Gemini call is wrapped in exponential backoff,
retrying only a 429 or 5xx response — see retry.py. A bad key or a
malformed-request-style error fails immediately and falls straight
through to the existing "return empty claims, report the error" path.
"""

from pydantic import BaseModel, Field

from app.llm_clients import get_gemini_client
from app.model_router import Tier, generate_structured
from app.schemas import ClaimVerdict, Document, VerifiedClaim
from app.vector_store import Embedder

MAX_SOURCE_EXCERPT_CHARS = 600
GROUNDEDNESS_FLAG_THRESHOLD = 0.15


class _LLMClaim(BaseModel):
    text: str
    supporting_source_numbers: list[int] = Field(default_factory=list)
    contradicting_source_numbers: list[int] = Field(default_factory=list)


class _LLMFactCheckOutput(BaseModel):
    claims: list[_LLMClaim] = Field(default_factory=list)


FACT_CHECK_PROMPT = """You are the fact-checking stage of a multi-agent research system that produces publication-quality reports. Work ONLY from the numbered sources below — do not use outside knowledge.

Question this is checking: {sub_question}

Sources:
{numbered_sources}

Extract 2-5 specific factual claims that directly address the question, using only what these sources actually say. For each claim, list which source numbers support it and which contradict it. If two sources disagree about something material to the question, that disagreement is itself worth a claim, with the disagreeing sources listed as contradicting each other. Leave a source uncited if it's too vague or off-topic to support anything specific.
"""


def _format_sources(sources: list[Document]) -> str:
    parts = []
    for i, doc in enumerate(sources, start=1):
        body = (doc.abstract or doc.snippet or "(no excerpt available)")[:MAX_SOURCE_EXCERPT_CHARS]
        parts.append(f"Source {i} ({doc.source.value}): {doc.title}\n{body}")
    return "\n\n".join(parts)


def _derive_verdict(supporting_count: int, contradicting_count: int) -> ClaimVerdict:
    if contradicting_count > 0:
        return ClaimVerdict.CONTRADICTED
    if supporting_count >= 2:
        return ClaimVerdict.CORROBORATED
    if supporting_count == 1:
        return ClaimVerdict.SINGLE_SOURCE
    return ClaimVerdict.UNVERIFIED


def _derive_confidence(supporting_count: int, contradicting_count: int) -> float:
    """A simple, transparent heuristic based on source counts — not a
    calibrated probability. Contradicted claims are capped low regardless
    of how many sources support them: an unresolved disagreement shouldn't
    be reported with false confidence just because one side has more
    sources."""
    if contradicting_count > 0:
        return 0.2 if supporting_count > contradicting_count else 0.0
    return {0: 0.0, 1: 0.4, 2: 0.7}.get(supporting_count, 0.9)


def check_groundedness(claim_text: str, sources: list[Document], embedder: Embedder) -> float:
    """Cosine similarity between the claim and its cited sources' text.
    Returns 1.0 (trivially grounded) if there's nothing to check against,
    so callers only need to act when this comes back low."""
    if not sources:
        return 1.0
    source_texts = [f"{d.title}. {d.abstract or d.snippet or ''}" for d in sources]
    claim_vector = embedder.embed([claim_text])[0]
    source_vectors = embedder.embed(source_texts)
    return float((source_vectors @ claim_vector).max())


class FactCheckerAgent:
    def __init__(self, embedder: Embedder | None = None):
        """`embedder` is optional — without one, groundedness checking is
        skipped and claims rely solely on the LLM's own source attribution.
        Pass a real embedder (e.g. LocalEmbedder) to enable the sanity net."""
        self._embedder = embedder

    def run(
        self,
        sub_question: str,
        documents: list[Document],
        max_sources: int = 6,
    ) -> tuple[list[VerifiedClaim], list[str]]:
        """Returns (claims, errors). Never fabricates a fallback claim — if
        fact-checking can't run, it returns an empty list plus a clear
        error rather than guessing at what the sources say. Claim extraction
        is a "light" stage: it prefers Groq's fast model and falls back to
        Gemini via the model router (see model_router.py)."""
        sources = documents[:max_sources]
        if not sources:
            return [], []

        warnings: list[str] = []
        try:
            llm_output = generate_structured(
                FACT_CHECK_PROMPT.format(
                    sub_question=sub_question,
                    numbered_sources=_format_sources(sources),
                ),
                tier=Tier.LIGHT,
                schema=_LLMFactCheckOutput,
                warnings=warnings,
                gemini_client_factory=get_gemini_client,
            )
        except Exception as exc:
            return [], [f"Fact-checking failed for '{sub_question}': {exc}"]

        claims: list[VerifiedClaim] = []
        for llm_claim in llm_output.claims:
            supporting = [sources[i - 1] for i in llm_claim.supporting_source_numbers if 1 <= i <= len(sources)]
            contradicting = [sources[i - 1] for i in llm_claim.contradicting_source_numbers if 1 <= i <= len(sources)]
            verdict = _derive_verdict(len(supporting), len(contradicting))
            confidence = _derive_confidence(len(supporting), len(contradicting))
            note = None

            if self._embedder is not None and supporting:
                groundedness = check_groundedness(llm_claim.text, supporting, self._embedder)
                if groundedness < GROUNDEDNESS_FLAG_THRESHOLD:
                    note = "Low similarity between this claim and its cited source(s) — worth double-checking manually."
                    confidence = min(confidence, 0.3)

            claims.append(
                VerifiedClaim(
                    text=llm_claim.text,
                    sub_question=sub_question,
                    supporting_sources=supporting,
                    contradicting_sources=contradicting,
                    verdict=verdict,
                    confidence=confidence,
                    note=note,
                )
            )

        return claims, warnings
