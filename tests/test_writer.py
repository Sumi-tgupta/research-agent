"""
Tests for the Writer. `_format_material` / `_fallback_draft` are pure
formatting logic tested directly with no mocking. The rest mock only the
Gemini call, and specifically check that revision context and target
language actually make it into the prompt — not just that *some* prompt
gets sent.
"""

from unittest.mock import MagicMock

from app.agents.writer_agent import WriterAgent, _fallback_draft, _format_material
from app.schemas import ClaimVerdict, Document, ResearchPlan, SourceType, SubQuestion, VerifiedClaim


def _plan() -> ResearchPlan:
    return ResearchPlan(
        original_query="impact of microplastics on marine food webs",
        sub_questions=[
            SubQuestion(question="Do microplastics accumulate in fish tissue?", web_query="x", academic_query="y"),
            SubQuestion(question="What are the main sources of ocean microplastics?", web_query="x", academic_query="y"),
        ],
    )


def _claim(sub_question: str, verdict: ClaimVerdict, confidence: float, text: str = "A claim.") -> VerifiedClaim:
    source = Document(title="Some Source", source=SourceType.WEB, url="https://a.com")
    return VerifiedClaim(
        text=text,
        sub_question=sub_question,
        supporting_sources=[source],
        verdict=verdict,
        confidence=confidence,
    )


def _fake_gemini_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


# ------------------------------------------------------------- Pure formatting

def test_format_material_groups_claims_by_subquestion():
    plan = _plan()
    claims = [
        _claim("Do microplastics accumulate in fish tissue?", ClaimVerdict.CORROBORATED, 0.7, "Fish accumulate microplastics."),
    ]
    material = _format_material(plan, claims, None)

    assert "Do microplastics accumulate in fish tissue?" in material
    assert "Fish accumulate microplastics." in material
    assert "corroborated" in material
    # the second sub-question has no claims and should say so, not be silently dropped
    assert "What are the main sources of ocean microplastics?" in material
    assert "No verified claims are available" in material


def test_format_material_includes_numbered_source_list_and_cite_instructions():
    plan = _plan()
    source = Document(title="A Cited Source", source=SourceType.WEB, url="https://a.com")
    claim = VerifiedClaim(
        text="Fish accumulate microplastics.",
        sub_question="Do microplastics accumulate in fish tissue?",
        supporting_sources=[source],
        verdict=ClaimVerdict.CORROBORATED,
        confidence=0.7,
    )
    material = _format_material(plan, [claim], None)

    assert "[1] A Cited Source" in material
    assert "cite as: [1]" in material


def test_format_material_same_source_gets_same_number_across_claims():
    plan = _plan()
    shared_source = Document(title="Shared Source", source=SourceType.WEB, url="https://shared.com")
    claims = [
        VerifiedClaim(
            text="First claim.",
            sub_question="Do microplastics accumulate in fish tissue?",
            supporting_sources=[shared_source],
            verdict=ClaimVerdict.SINGLE_SOURCE,
            confidence=0.4,
        ),
        VerifiedClaim(
            text="Second claim.",
            sub_question="What are the main sources of ocean microplastics?",
            supporting_sources=[shared_source],
            verdict=ClaimVerdict.SINGLE_SOURCE,
            confidence=0.4,
        ),
    ]
    material = _format_material(plan, claims, None)

    # only one numbered entry for the shared source, and both claims cite it as [1]
    assert material.count("[1] Shared Source") == 1
    assert material.count("cite as: [1]") == 2


def test_format_material_contradicting_sources_get_their_own_numbers():
    plan = _plan()
    supporting = Document(title="Supporting Source", source=SourceType.WEB, url="https://a.com")
    contradicting = Document(title="Contradicting Source", source=SourceType.WEB, url="https://b.com")
    claim = VerifiedClaim(
        text="A contested claim.",
        sub_question="Do microplastics accumulate in fish tissue?",
        supporting_sources=[supporting],
        contradicting_sources=[contradicting],
        verdict=ClaimVerdict.CONTRADICTED,
        confidence=0.0,
    )
    material = _format_material(plan, [claim], None)

    assert "cite as: [1]" in material
    assert "disagreed with by: [2]" in material


def test_format_material_omits_source_header_when_no_claims():
    material = _format_material(_plan(), [], None)
    assert "Numbered sources" not in material


def test_format_material_includes_supplementary_excerpts_labeled_as_context():
    plan = _plan()
    excerpts = {"Do microplastics accumulate in fish tissue?": ["Some background detail from a source."]}
    material = _format_material(plan, [], excerpts)

    assert "Some background detail from a source." in material
    assert "unverified context only" in material


def test_fallback_draft_contains_claim_text_and_confidence():
    plan = _plan()
    claims = [_claim("Do microplastics accumulate in fish tissue?", ClaimVerdict.SINGLE_SOURCE, 0.4, "One study found accumulation.")]
    draft = _fallback_draft(plan, claims)

    assert "One study found accumulation." in draft
    assert "single_source" in draft
    assert plan.original_query in draft
    assert "unformatted summary" in draft.lower()


# ------------------------------------------------------------------ WriterAgent

def test_writer_returns_gemini_text_on_success(mocker):
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=_fake_gemini_client("# A Great Report\n\nBody text."))

    draft, errors = WriterAgent().draft(_plan(), [_claim("Do microplastics accumulate in fish tissue?", ClaimVerdict.CORROBORATED, 0.7)])

    assert errors == []
    assert draft == "# A Great Report\n\nBody text."


def test_writer_falls_back_when_no_key(mocker):
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=None)
    claims = [_claim("Do microplastics accumulate in fish tissue?", ClaimVerdict.CORROBORATED, 0.7, "Fish accumulate microplastics.")]

    draft, errors = WriterAgent().draft(_plan(), claims)

    assert "Fish accumulate microplastics." in draft
    assert any("GEMINI_API_KEY" in e for e in errors)


def test_writer_falls_back_when_gemini_raises(mocker):
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("quota exceeded")
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=client)
    claims = [_claim("Do microplastics accumulate in fish tissue?", ClaimVerdict.CORROBORATED, 0.7, "Fish accumulate microplastics.")]

    draft, errors = WriterAgent().draft(_plan(), claims)

    assert "Fish accumulate microplastics." in draft
    assert any("Writer LLM call failed" in e for e in errors)


def test_writer_falls_back_on_empty_response(mocker):
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=_fake_gemini_client("   "))
    claims = [_claim("Do microplastics accumulate in fish tissue?", ClaimVerdict.CORROBORATED, 0.7, "Fish accumulate microplastics.")]

    draft, errors = WriterAgent().draft(_plan(), claims)

    assert "Fish accumulate microplastics." in draft
    assert errors  # not silent


def test_writer_passes_target_language_into_the_prompt(mocker):
    client = _fake_gemini_client("some draft")
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=client)

    WriterAgent().draft(_plan(), [], target_language="Spanish")

    prompt_sent = client.models.generate_content.call_args.kwargs["contents"]
    assert "Spanish" in prompt_sent


def test_writer_includes_revision_context_only_when_both_provided(mocker):
    client = _fake_gemini_client("revised draft")
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=client)

    WriterAgent().draft(
        _plan(),
        [],
        previous_draft="THE OLD DRAFT TEXT",
        feedback="ADD MORE DETAIL ON SOURCES",
    )

    prompt_sent = client.models.generate_content.call_args.kwargs["contents"]
    assert "THE OLD DRAFT TEXT" in prompt_sent
    assert "ADD MORE DETAIL ON SOURCES" in prompt_sent


def test_writer_omits_revision_block_on_first_draft(mocker):
    client = _fake_gemini_client("first draft")
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=client)

    WriterAgent().draft(_plan(), [])

    prompt_sent = client.models.generate_content.call_args.kwargs["contents"]
    assert "This is a revision" not in prompt_sent


def test_writer_retries_a_transient_rate_limit_then_succeeds(mocker):
    mocker.patch("app.retry.time.sleep")  # skip real backoff delays

    class _FakeAPIError(Exception):
        def __init__(self, code):
            self.code = code

    client = MagicMock()
    client.models.generate_content.side_effect = [_FakeAPIError(429), MagicMock(text="recovered draft")]
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=client)

    draft, errors = WriterAgent().draft(_plan(), [])

    assert errors == []
    assert draft == "recovered draft"
    assert client.models.generate_content.call_count == 2
