"""
Planner Agent — turns a broad research question into a handful of focused
sub-questions, each with a web-search-style query and an academic-search-
style query. Downstream, Search Agent and Paper Retrieval Agent loop over
these sub-questions instead of taking a single query (see graph.py).

Uses structured output (schema=ResearchPlan) via the model router, so
parsing is just handed a validated `ResearchPlan` — no ad-hoc JSON coaxing
needed. If the call fails for any reason (no key, quota, malformed response
from every provider), falls back to a single trivial sub-question built from
the original query so the rest of the pipeline can still run. The failure is
reported, not hidden.

Routing (Phase 12): planning is a "heavy" reasoning stage, so it prefers
Gemini and transparently falls back to Groq if Gemini fails — see
model_router.py. Retry/backoff on each provider is handled inside the router
(retry.py); a bad key or malformed-prompt error on both providers falls
straight through to the existing single-question fallback, unchanged.
"""

from app.llm_clients import get_gemini_client
from app.model_router import Tier, generate_structured
from app.schemas import ResearchPlan, SubQuestion

PLANNER_PROMPT = """You are the planning stage of a multi-agent research system that produces publication-quality reports.

Break the research question below into {num_sub_questions} focused sub-questions that together give thorough, well-rounded coverage. Consider facets like background/definitions, current state of the art, key debates or open problems, notable recent developments, and practical applications — pick whichever actually fit this topic, don't force all of them.

For each sub-question, also write:
- web_query: phrased the way someone would type it into a search engine
- academic_query: phrased with the more formal/technical terminology an academic paper search needs

Research question: {query}
"""


class PlannerAgent:
    def run(self, query: str, num_sub_questions: int = 4) -> tuple[ResearchPlan, list[str]]:
        """Returns (plan, errors). Never raises — a failed LLM call degrades
        to a one-sub-question fallback plan instead of stopping the pipeline.
        `errors` may also carry a non-fatal note when the router had to fall
        back from the primary provider to the secondary."""
        warnings: list[str] = []
        try:
            plan = generate_structured(
                PLANNER_PROMPT.format(num_sub_questions=num_sub_questions, query=query),
                tier=Tier.HEAVY,
                schema=ResearchPlan,
                warnings=warnings,
                gemini_client_factory=get_gemini_client,
            )
            if not plan.sub_questions:
                raise ValueError("model returned a plan with no sub-questions")
            return plan, warnings
        except Exception as exc:
            return self._fallback_plan(query), [*warnings, f"Planner LLM call failed, used fallback plan: {exc}"]

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
