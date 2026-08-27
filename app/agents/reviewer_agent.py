"""
Reviewer Agent — critiques the Writer's draft against the verified claims
and the plan, checking specifically for the failure modes this pipeline is
prone to: overstating a single-source or contradicted claim as settled
fact, or leaving a sub-question's disagreement unmentioned. Returns an
approve/revise decision plus actionable feedback — it never edits the
draft itself, that's still the Writer's job (see graph.py for the loop).

If review fails outright (no key, bad response), it defaults to APPROVE
rather than REVISE: a pipeline that can't judge a draft shouldn't loop
forever trying to fix it, or block the report from being produced because
the reviewer itself is broken. The failure is still surfaced as an error.
"""

from app.llm_clients import get_gemini_client
from app.model_router import Tier, generate_structured
from app.schemas import ReviewDecision, ReviewResult, ResearchPlan, VerifiedClaim

REVIEWER_PROMPT = """You are the review stage of a multi-agent research system that produces publication-quality reports. Check the draft below against the verified claims it should be based on.

Look specifically for:
1. Any claim marked "single_source" or "unverified" presented as settled, uncontested fact.
2. Any "contradicted" claim where the disagreement between sources isn't actually mentioned in the draft.
3. Any sub-question from the plan that the draft doesn't meaningfully address.
4. Any claim in the draft that doesn't seem to trace back to the material it was given (possible fabrication).

If none of these problems are present, approve. If any are present, request a revision with SPECIFIC, actionable feedback (what to fix and where) — don't rewrite the draft yourself.

Research question: {original_query}

Sub-questions the report should cover:
{sub_questions}

Verified claims the draft should be grounded in:
{claims_summary}

Draft to review:
---
{draft}
---
"""


def _format_claims_summary(verified_claims: list[VerifiedClaim]) -> str:
    if not verified_claims:
        return "(no verified claims were available)"
    return "\n".join(f"- [{claim.sub_question}] [{claim.verdict.value}] {claim.text}" for claim in verified_claims)


class ReviewerAgent:
    def review(
        self,
        plan: ResearchPlan,
        draft: str,
        verified_claims: list[VerifiedClaim],
    ) -> tuple[ReviewResult, list[str]]:
        """Returns (result, errors). Defaults to APPROVE on any failure —
        see module docstring for why that's the safe default here. Review is
        a "heavy" reasoning stage: it prefers Gemini and falls back to Groq
        via the model router; a fallback is noted in `errors`."""
        prompt = REVIEWER_PROMPT.format(
            original_query=plan.original_query,
            sub_questions="\n".join(f"- {sq.question}" for sq in plan.sub_questions),
            claims_summary=_format_claims_summary(verified_claims),
            draft=draft,
        )

        warnings: list[str] = []
        try:
            result = generate_structured(
                prompt,
                tier=Tier.HEAVY,
                schema=ReviewResult,
                warnings=warnings,
                gemini_client_factory=get_gemini_client,
            )
            return result, warnings
        except Exception as exc:
            return (
                ReviewResult(decision=ReviewDecision.APPROVE, feedback=""),
                [*warnings, f"Review failed — skipped review, draft approved by default: {exc}"],
            )
