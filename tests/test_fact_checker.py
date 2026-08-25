"""
Tests for the Fact Checker — the project plan flags this as the highest
hallucination-risk phase, so this leans harder on realistic scenarios than
the earlier test files: an actual corroboration case, an actual
contradiction case, and the groundedness sanity net, not just structural
"does it run" checks.

`_derive_verdict` / `_derive_confidence` are pure functions (no LLM, no
mocking needed) — deliberately, so the one part of this phase that decides
what gets reported as "confirmed by 2 sources" vs "sources disagree" is
fully unit-tested and auditable independent of whatever a live model does.
`check_groundedness` similarly runs for real against the local FakeEmbedder.
Only the actual Gemini call is mocked.
"""

from unittest.mock import MagicMock

import requests

from app.agents.fact_checker_agent import (
    FactCheckerAgent,
    _derive_confidence,
    _derive_verdict,
    check_groundedness,
)
from app.schemas import ClaimVerdict, Document, SourceType
from tests.fakes import FakeEmbedder


def _doc(title: str, abstract: str, url: str = "https://example.com") -> Document:
    return Document(title=title, abstract=abstract, source=SourceType.WEB, url=url)


def _fake_gemini_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


# ------------------------------------------------------- Pure verdict/confidence logic

def test_verdict_derivation():
    assert _derive_verdict(0, 0) == ClaimVerdict.UNVERIFIED
    assert _derive_verdict(1, 0) == ClaimVerdict.SINGLE_SOURCE
    assert _derive_verdict(2, 0) == ClaimVerdict.CORROBORATED
    assert _derive_verdict(5, 0) == ClaimVerdict.CORROBORATED
    assert _derive_verdict(0, 1) == ClaimVerdict.CONTRADICTED
    # contradicting sources always flip the verdict, regardless of how
    # many sources support the claim — an unresolved disagreement isn't
    # "corroborated" just because one side has more sources
    assert _derive_verdict(4, 1) == ClaimVerdict.CONTRADICTED


def test_confidence_derivation():
    assert _derive_confidence(0, 0) == 0.0
    assert _derive_confidence(1, 0) == 0.4
    assert _derive_confidence(2, 0) == 0.7
    assert _derive_confidence(10, 0) == 0.9  # capped, not literally 1.0
    assert _derive_confidence(1, 1) == 0.0   # evenly contested -> no false confidence
    assert _derive_confidence(3, 1) == 0.2   # majority support, but still capped low
    assert _derive_confidence(1, 3) == 0.0


# ------------------------------------------------------------------- Groundedness

def test_groundedness_high_for_matching_claim_and_source():
    source = _doc(
        "Coral reef bleaching under ocean acidification",
        "Rising ocean temperatures and acidification are major drivers of coral reef bleaching events worldwide.",
    )
    claim = "Rising ocean temperatures and acidification contribute to coral reef bleaching."
    assert check_groundedness(claim, [source], FakeEmbedder()) > 0.5


def test_groundedness_low_for_unrelated_claim_and_source():
    source = _doc(
        "Coral reef bleaching under ocean acidification",
        "Rising ocean temperatures and acidification are major drivers of coral reef bleaching events worldwide.",
    )
    claim = "Municipal zoning regulations restrict commercial construction downtown."
    assert check_groundedness(claim, [source], FakeEmbedder()) < 0.15


def test_groundedness_returns_one_with_no_sources():
    assert check_groundedness("any claim", [], FakeEmbedder()) == 1.0


# ------------------------------------------------------------- FactCheckerAgent, mocked LLM

def test_corroborated_claim_when_two_sources_agree(mocker):
    sources = [
        _doc("Microplastics in fish digestive tracts", "Survey of 12 marine fish species found microplastic particles in gut contents.", "https://a.com"),
        _doc("Plastic ingestion in coastal fish populations", "Independent sampling confirmed microplastic presence in digestive tracts across multiple species.", "https://b.com"),
    ]
    mocker.patch(
        "app.agents.fact_checker_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"claims": [{"text": "Microplastics have been found in the digestive tracts of multiple marine fish species.", '
            '"supporting_source_numbers": [1, 2], "contradicting_source_numbers": []}]}'
        ),
    )

    claims, errors = FactCheckerAgent().run("do microplastics accumulate in fish tissue", sources)

    assert errors == []
    assert len(claims) == 1
    claim = claims[0]
    assert claim.verdict == ClaimVerdict.CORROBORATED
    assert claim.confidence == 0.7
    assert len(claim.supporting_sources) == 2
    assert claim.contradicting_sources == []


def test_contradicted_claim_when_sources_disagree(mocker):
    sources = [
        _doc("Caffeine pharmacokinetics review", "This review states caffeine's elimination half-life in healthy adults is approximately 5 hours.", "https://a.com"),
        _doc("Individual variation in caffeine metabolism", "This study reports half-life closer to 9-10 hours in slow CYP1A2 metabolizers.", "https://b.com"),
    ]
    mocker.patch(
        "app.agents.fact_checker_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"claims": [{"text": "Caffeine\'s elimination half-life in healthy adults is approximately 5 hours.", '
            '"supporting_source_numbers": [1], "contradicting_source_numbers": [2]}]}'
        ),
    )

    claims, errors = FactCheckerAgent().run("what is caffeine's half-life in adults", sources)

    assert errors == []
    assert len(claims) == 1
    claim = claims[0]
    assert claim.verdict == ClaimVerdict.CONTRADICTED
    assert claim.confidence == 0.0
    assert claim.supporting_sources[0].url == "https://a.com"
    assert claim.contradicting_sources[0].url == "https://b.com"


def test_out_of_range_source_numbers_are_dropped_not_crashed(mocker):
    sources = [_doc("Only source", "The only real source provided.", "https://a.com")]
    mocker.patch(
        "app.agents.fact_checker_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"claims": [{"text": "A claim citing a source that does not exist.", '
            '"supporting_source_numbers": [1, 7], "contradicting_source_numbers": [99]}]}'
        ),
    )

    claims, errors = FactCheckerAgent().run("test", sources)

    assert errors == []
    assert len(claims) == 1
    # index 7 and 99 are out of range for a 1-source list and should be
    # silently dropped rather than raising an IndexError
    assert len(claims[0].supporting_sources) == 1
    assert claims[0].contradicting_sources == []
    assert claims[0].verdict == ClaimVerdict.SINGLE_SOURCE


def test_no_sources_short_circuits_without_calling_gemini(mocker):
    gemini_mock = mocker.patch("app.agents.fact_checker_agent.get_gemini_client")

    claims, errors = FactCheckerAgent().run("test", [])

    assert claims == []
    assert errors == []
    gemini_mock.assert_not_called()


def test_missing_gemini_key_returns_empty_claims_with_clear_error(mocker):
    mocker.patch("app.agents.fact_checker_agent.get_gemini_client", return_value=None)

    claims, errors = FactCheckerAgent().run("test", [_doc("T", "abstract")])

    assert claims == []
    assert any("GEMINI_API_KEY" in e for e in errors)


def test_malformed_llm_response_returns_empty_claims_not_a_crash(mocker):
    mocker.patch(
        "app.agents.fact_checker_agent.get_gemini_client",
        return_value=_fake_gemini_client("not valid json"),
    )

    claims, errors = FactCheckerAgent().run("test", [_doc("T", "abstract")])

    assert claims == []
    assert any("Fact-checking failed" in e for e in errors)


# --------------------------------------------------- Groundedness net wired into the agent

def test_agent_flags_low_groundedness_claim_when_embedder_provided(mocker):
    source = _doc(
        "Coral reef bleaching under ocean acidification",
        "Rising ocean temperatures and acidification are major drivers of coral reef bleaching events worldwide.",
    )
    # The LLM claims this source supports an unrelated statement — exactly
    # the failure mode the groundedness net exists to catch.
    mocker.patch(
        "app.agents.fact_checker_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"claims": [{"text": "Municipal zoning regulations restrict commercial construction downtown.", '
            '"supporting_source_numbers": [1], "contradicting_source_numbers": []}]}'
        ),
    )

    claims, errors = FactCheckerAgent(embedder=FakeEmbedder()).run("test", [source])

    assert errors == []
    assert len(claims) == 1
    assert claims[0].note is not None
    assert claims[0].confidence <= 0.3


def test_agent_skips_groundedness_check_without_an_embedder(mocker):
    """No embedder passed -> the agent trusts the LLM's own attribution
    without the extra sanity net, rather than failing."""
    source = _doc("Coral reef bleaching", "Ocean acidification drives coral bleaching.")
    mocker.patch(
        "app.agents.fact_checker_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"claims": [{"text": "Unrelated statement about zoning law.", '
            '"supporting_source_numbers": [1], "contradicting_source_numbers": []}]}'
        ),
    )

    claims, errors = FactCheckerAgent(embedder=None).run("test", [source])

    assert errors == []
    assert claims[0].note is None
    assert claims[0].confidence == 0.4  # plain single-source confidence, un-downgraded


# --------------------------------------------------------------- retry/backoff

class _FakeHTTPResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_fact_checker_retries_a_transient_server_error_then_succeeds(mocker):
    mocker.patch("app.retry.time.sleep")  # skip real backoff delays
    client = MagicMock()
    client.models.generate_content.side_effect = [
        requests.HTTPError(response=_FakeHTTPResponse(503)),
        MagicMock(
            text='{"claims": [{"text": "Recovered claim.", "supporting_source_numbers": [1], '
            '"contradicting_source_numbers": []}]}'
        ),
    ]
    mocker.patch("app.agents.fact_checker_agent.get_gemini_client", return_value=client)

    claims, errors = FactCheckerAgent().run("test", [_doc("A Source", "An abstract.")])

    assert errors == []
    assert len(claims) == 1
    assert claims[0].text == "Recovered claim."
    assert client.models.generate_content.call_count == 2
