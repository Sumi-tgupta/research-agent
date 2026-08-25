"""
Planner Agent — turns a broad research question into a handful of focused
sub-questions, each with a web-search-style query and an academic-search-
style query. Downstream, Search Agent and Paper Retrieval Agent loop over
these sub-questions instead of taking a single query (see graph.py).

Uses Gemini's structured output (response_schema=ResearchPlan), so parsing
is just `ResearchPlan.model_validate_json(response.text)` — no ad-hoc JSON
coaxing needed. If the call fails for any reason (no key, quota, malformed
response), falls back to a single trivial sub-question built from the
original query so the rest of the pipeline can still run. The failure is
reported, not hidden.

Hardening (Phase 7): the Gemini call is wrapped in exponential backoff,
retrying only a 429 (rate limited) or 5xx (transient) response — see
retry.py. A bad key or a malformed-prompt-style error fails immediately
and falls straight through to the existing fallback, unchanged.
"""

from google.genai import types

from app.config import get_settings
from app.llm_clients import get_gemini_client
from app.retry import call_with_backoff, is_retryable_http_error
from app.schemas import ResearchPlan, SubQuestion

PLANNER_PROMPT = """You are the planning stage of a multi-agent research system that produces publication-quality reports.

Break the research question below into {num_sub_questions} focused sub-questions that together give thorough, well-rounded coverage. Consider facets like background/definitions, current state of the art, key debates or open problems, notable recent developments, and practical applications — pick whichever actually fit this topic, don't force all of them.

For each sub-question, also write:
- web_query: phrased the way someone would type it into a search engine
- academic_query: phrased with the more formal/technical terminology an academic paper search needs

Research question: {query}
"""


class PlannerAgent:
    def __init__(self):
        self.settings = get_settings()

    def run(self, query: str, num_sub_questions: int = 4) -> tuple[ResearchPlan, list[str]]:
        """Returns (plan, errors). Never raises — a failed LLM call degrades
        to a one-sub-question fallback plan instead of stopping the pipeline."""
        client = get_gemini_client()
        if client is None:
            return (
                self._fallback_plan(query),
                ["GEMINI_API_KEY not configured — used a single-question fallback plan"],
            )

        try:
            response = call_with_backoff(
                lambda: client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=PLANNER_PROMPT.format(num_sub_questions=num_sub_questions, query=query),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ResearchPlan,
                    ),
                ),
                is_retryable=is_retryable_http_error,
            )
            plan = ResearchPlan.model_validate_json(response.text)
            if not plan.sub_questions:
                raise ValueError("Gemini returned a plan with no sub-questions")
            return plan, []
        except Exception as exc:
            return self._fallback_plan(query), [f"Planner LLM call failed, used fallback plan: {exc}"]

    @staticmethod
    def _fallback_plan(query: str) -> ResearchPlan:
        return ResearchPlan(
            original_query=query,
            sub_questions=[SubQuestion(question=query, web_query=query, academic_query=query)],
        )


def planner_node(state: dict) -> dict:
    """LangGraph node: reads `query` (+ optional `num_sub_questions`) from
    state, writes `plan` and appends any planner errors."""
    agent = PlannerAgent()
    plan, errors = agent.run(state["query"], num_sub_questions=state.get("num_sub_questions", 4))
    return {"plan": plan, "errors": [*state.get("errors", []), *errors]}

    @staticmethod
    def _fallback_plan(query: str) -> ResearchPlan:
        return ResearchPlan(
            original_query=query,
            sub_questions=[SubQuestion(question=query, web_query=query, academic_query=query)],
        )


def planner_node(state: dict) -> dict:
    """LangGraph node: reads `query` (+ optional `num_sub_questions`) from
    state, writes `plan` and appends any planner errors."""
    agent = PlannerAgent()
    plan, errors = agent.run(state["query"], num_sub_questions=state.get("num_sub_questions", 4))
    return {"plan": plan, "errors": [*state.get("errors", []), *errors]}
