"""
Turns LangGraph's raw `stream(..., stream_mode="updates")` output — which
yields `{node_name: partial_state_update}` after every node, including
every pass through the writer/reviewer revision loop — into something a
UI can show a person: a friendly stage label, a one-line human-readable
summary of what that stage actually produced, and Server-Sent-Events
formatting.

Kept separate from main.py's routing so the "how do I describe what the
Fact Checker just did" logic doesn't get lost inside an endpoint function.
"""

import json
from typing import Any

STAGE_LABELS = {
    "planner": "Planner",
    "search_all": "Web Search",
    "retrieve_all": "Paper Retrieval",
    "dedupe_and_rank": "Deduplication & Ranking",
    "fact_check": "Fact Checking",
    "writer": "Writer",
    "reviewer": "Reviewer",
    "add_citations": "Citation Generator",
    "generate_charts": "Chart Generator",
}


def summarize_stage(node_name: str, update: dict) -> str:
    """A short, human-readable line describing what this node's update
    contains — shown next to the stage in the live status feed."""
    if node_name == "planner":
        plan = update.get("plan")
        n = len(plan.sub_questions) if plan else 0
        return f"{n} sub-question{'s' if n != 1 else ''} drafted"

    if node_name == "search_all":
        n = len(update.get("web_results", []))
        return f"{n} web result{'s' if n != 1 else ''} found"

    if node_name == "retrieve_all":
        n = len(update.get("paper_results", []))
        return f"{n} paper{'s' if n != 1 else ''} found"

    if node_name == "dedupe_and_rank":
        n = len(update.get("final_documents", []))
        return f"{n} unique source{'s' if n != 1 else ''} after deduplication"

    if node_name == "fact_check":
        claims = update.get("verified_claims", [])
        contradicted = sum(1 for c in claims if getattr(c.verdict, "value", c.verdict) == "contradicted")
        summary = f"{len(claims)} claim{'s' if len(claims) != 1 else ''} checked"
        if contradicted:
            summary += f" — {contradicted} contradiction{'s' if contradicted != 1 else ''} found"
        return summary

    if node_name == "writer":
        return "Draft written"

    if node_name == "reviewer":
        decision = update.get("review_decision", "")
        return f"Reviewed — {decision}" if decision else "Reviewed"

    if node_name == "add_citations":
        return "Bibliography compiled"

    if node_name == "generate_charts":
        n = len(update.get("chart_specs", []))
        return f"{n} chart{'s' if n != 1 else ''} extracted" if n else "No chartable data found"

    return ""


def serialize(obj: Any) -> Any:
    """Recursively converts Pydantic models (and lists/dicts containing
    them) into plain JSON-safe values, so the raw state-update dicts from
    LangGraph — which hold Document/VerifiedClaim/ResearchPlan objects
    directly — can go straight into an SSE payload without hand-written
    per-field conversion."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {key: serialize(value) for key, value in obj.items()}
    return obj


def format_sse_event(payload: dict) -> str:
    return f"data: {json.dumps(serialize(payload))}\n\n"
