"""
Tests for the Reviewer. The key behavior to verify: when review fails
outright, it defaults to APPROVE, not REVISE — a broken reviewer should
never be able to trap the pipeline in an endless revision loop.
"""

from unittest.mock import MagicMock

from app.agents.reviewer_agent import ReviewerAgent
from app.schemas import ClaimVerdict, Document, ReviewDecision, ResearchPlan, SourceType, SubQuestion, VerifiedClaim


def _plan() -> ResearchPlan:
    return ResearchPlan(
        original_query="impact of microplastics on marine food webs",
        sub_questions=[SubQuestion(question="Do microplastics accumulate in fish tissue?", web_query="x", academic_query="y")],
    )


def _claims() -> list[VerifiedClaim]:
    source = Document(title="Some Source", source=SourceType.WEB, url="https://a.com")
    return [
        VerifiedClaim(
            text="Fish accumulate microplastics.",
            sub_question="Do microplastics accumulate in fish tissue?",
            supporting_sources=[source],
            verdict=ClaimVerdict.CORROBORATED,
            confidence=0.7,
        )
    ]


def _fake_gemini_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


def test_reviewer_approves_a_good_draft(mocker):
    mocker.patch(
        "app.agents.reviewer_agent.get_gemini_client",
        return_value=_fake_gemini_client('{"decision": "approve", "feedback": ""}'),
    )

    result, errors = ReviewerAgent().review(_plan(), "A well-written draft.", _claims())

    assert errors == []
    assert result.decision == ReviewDecision.APPROVE


def test_reviewer_requests_revision_with_feedback(mocker):
    mocker.patch(
        "app.agents.reviewer_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"decision": "revise", "feedback": "The single-source claim about fish accumulation is presented as settled fact — hedge it."}'
        ),
    )

    result, errors = ReviewerAgent().review(_plan(), "Fish definitely accumulate microplastics.", _claims())

    assert errors == []
    assert result.decision == ReviewDecision.REVISE
    assert "hedge" in result.feedback


def test_reviewer_defaults_to_approve_when_no_key(mocker):
    mocker.patch("app.agents.reviewer_agent.get_gemini_client", return_value=None)

    result, errors = ReviewerAgent().review(_plan(), "A draft.", _claims())

    assert result.decision == ReviewDecision.APPROVE
    assert any("GEMINI_API_KEY" in e for e in errors)


def test_reviewer_defaults_to_approve_on_malformed_response(mocker):
    mocker.patch(
        "app.agents.reviewer_agent.get_gemini_client",
        return_value=_fake_gemini_client("not valid json"),
    )

    result, errors = ReviewerAgent().review(_plan(), "A draft.", _claims())

    assert result.decision == ReviewDecision.APPROVE
    assert any("Review failed" in e for e in errors)


def test_reviewer_defaults_to_approve_when_gemini_raises(mocker):
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("quota exceeded")
    mocker.patch("app.agents.reviewer_agent.get_gemini_client", return_value=client)

    result, errors = ReviewerAgent().review(_plan(), "A draft.", _claims())

    assert result.decision == ReviewDecision.APPROVE
    assert any("Review failed" in e for e in errors)


def test_reviewer_retries_a_transient_server_error_then_succeeds(mocker):
    mocker.patch("app.retry.time.sleep")  # skip real backoff delays

    class _FakeAPIError(Exception):
        def __init__(self, code):
            self.code = code

    client = MagicMock()
    client.models.generate_content.side_effect = [
        _FakeAPIError(500),
        MagicMock(text='{"decision": "approve", "feedback": ""}'),
    ]
    mocker.patch("app.agents.reviewer_agent.get_gemini_client", return_value=client)

    result, errors = ReviewerAgent().review(_plan(), "A draft.", _claims())

    assert errors == []
    assert result.decision == ReviewDecision.APPROVE
    assert client.models.generate_content.call_count == 2
