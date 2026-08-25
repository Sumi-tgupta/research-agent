"""
Tests for stream_events.py. All real — pure formatting/serialization
logic with no LLM or network involved.
"""

import json

from app.schemas import ChartSpec, ClaimVerdict, Document, ResearchPlan, SourceType, SubQuestion, VerifiedClaim
from app.stream_events import format_sse_event, serialize, summarize_stage


def _plan(n_sub_questions: int = 2) -> ResearchPlan:
    return ResearchPlan(
        original_query="test query",
        sub_questions=[SubQuestion(question=f"q{i}", web_query="w", academic_query="a") for i in range(n_sub_questions)],
    )


def _claim(verdict: ClaimVerdict) -> VerifiedClaim:
    return VerifiedClaim(text="A claim", sub_question="q1", verdict=verdict, confidence=0.5)


# --------------------------------------------------------------- summarize_stage

def test_planner_summary_counts_subquestions():
    assert summarize_stage("planner", {"plan": _plan(3)}) == "3 sub-questions drafted"


def test_planner_summary_singular_for_one():
    assert summarize_stage("planner", {"plan": _plan(1)}) == "1 sub-question drafted"


def test_search_all_summary():
    docs = [Document(title="A", source=SourceType.WEB, url="https://a.com")]
    assert summarize_stage("search_all", {"web_results": docs}) == "1 web result found"


def test_fact_check_summary_flags_contradictions():
    claims = [_claim(ClaimVerdict.CORROBORATED), _claim(ClaimVerdict.CONTRADICTED)]
    summary = summarize_stage("fact_check", {"verified_claims": claims})
    assert "2 claims checked" in summary
    assert "1 contradiction found" in summary


def test_fact_check_summary_omits_contradiction_note_when_none():
    claims = [_claim(ClaimVerdict.CORROBORATED)]
    summary = summarize_stage("fact_check", {"verified_claims": claims})
    assert "contradiction" not in summary


def test_reviewer_summary_includes_decision():
    assert summarize_stage("reviewer", {"review_decision": "revise"}) == "Reviewed — revise"


def test_generate_charts_summary_zero_case():
    assert summarize_stage("generate_charts", {"chart_specs": []}) == "No chartable data found"


def test_generate_charts_summary_nonzero_case():
    charts = [ChartSpec(title="T", labels=["a"], values=[1.0])]
    assert summarize_stage("generate_charts", {"chart_specs": charts}) == "1 chart extracted"


def test_unknown_stage_returns_empty_string():
    assert summarize_stage("some_future_stage", {}) == ""


# --------------------------------------------------------------- serialize

def test_serialize_converts_nested_pydantic_models_and_enums():
    claim = _claim(ClaimVerdict.CONTRADICTED)
    result = serialize({"claims": [claim]})

    assert result["claims"][0]["verdict"] == "contradicted"
    assert result["claims"][0]["text"] == "A claim"
    # must be genuinely JSON-serializable, not just dict-shaped
    json.dumps(result)


def test_serialize_passes_through_plain_values_unchanged():
    assert serialize({"count": 3, "name": "x", "items": [1, 2, 3]}) == {"count": 3, "name": "x", "items": [1, 2, 3]}


# --------------------------------------------------------------- format_sse_event

def test_format_sse_event_produces_valid_sse_and_json():
    event = format_sse_event({"type": "stage", "stage": "planner"})

    assert event.startswith("data: ")
    assert event.endswith("\n\n")
    payload = json.loads(event[len("data: "):].strip())
    assert payload == {"type": "stage", "stage": "planner"}
