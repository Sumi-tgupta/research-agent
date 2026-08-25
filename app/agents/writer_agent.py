"""
Writer Agent — drafts the report from Phase 3's verified claims, not raw
documents, so each claim's verification status carries through into how
it's phrased (stated directly, hedged, or flagged as disputed). Optionally
takes supplementary excerpts (see retrieval_index.py) for background color
that didn't rise to the level of a standalone claim — those are explicitly
framed to the model as unverified context, not fact, and off-limits to cite.

Citations: claims are presented with bracketed reference numbers (e.g.
"cite as: [1], [2]") drawn from the same stable, deduplicated source index
citations.py uses to build the final bibliography. The Writer's only job
is to place "[N]" markers where it states something from that source — it
never formats a citation itself. That stays entirely in citations.py,
deterministic and LLM-free (see graph.py's add_citations_node).

Supports two modes:
  - First draft: plan + verified_claims (+ optional excerpts) -> draft text.
  - Revision: also pass `previous_draft` + `feedback` from the Reviewer.

Multi-language support is a prompt instruction ("write in {target_language}"),
not a separate translation pass — one Gemini call either way.

If Gemini is unavailable, this falls back to a plain, mechanical summary of
the claims (headings + bullet points, verdict/confidence/source titles
shown directly, no [N] markers) rather than fabricating polished prose it
can't actually generate without a model. It's clearly labeled as a
fallback, not presented as a finished report.
"""

from app.citations import build_source_index
from app.config import get_settings
from app.llm_clients import get_gemini_client
from app.retry import call_with_backoff, is_retryable_http_error
from app.schemas import Document, ResearchPlan, VerifiedClaim

WRITER_PROMPT = """You are the writing stage of a multi-agent research system that produces publication-quality reports. Write the report in {target_language}.

Write a well-organized research report answering: {original_query}

Structure: a brief introduction framing the question, one section per sub-question below (use its theme as a natural heading — no need to quote it verbatim), and a short conclusion synthesizing across sections. Use markdown headings.

Ground every claim in the material below — do not introduce outside facts. Reflect each claim's verification status in how you phrase it:
- "corroborated" claims (2+ independent sources agree): state directly
- "single_source" claims: hedge appropriately ("one source indicates...", "according to X...")
- "contradicted" claims: explicitly surface the disagreement rather than silently picking a side
- Skip "unverified" claims unless nothing better-supported exists for that sub-question
- Background excerpts (marked below) are context only — don't present them as established facts, and don't cite them

Cite claims using the bracketed reference numbers given for each one, e.g. "Fish accumulate microplastics [1][2]." Use ONLY the numbers provided below — never invent a citation number, and never attach one to a background excerpt.

Material, organized by sub-question:
{material}
{revision_block}
"""

REVISION_BLOCK_TEMPLATE = """
This is a revision. Your previous draft:
---
{previous_draft}
---

Reviewer feedback to address:
{feedback}

Revise the draft to address this feedback while keeping what already works well.
"""


def _format_material(
    plan: ResearchPlan,
    verified_claims: list[VerifiedClaim],
    supplementary_excerpts: dict[str, list[str]] | None,
) -> str:
    supplementary_excerpts = supplementary_excerpts or {}
    source_index = build_source_index(verified_claims)
    numbers_by_key = {(doc.url or doc.title): i for i, doc in enumerate(source_index, start=1)}

    def _cite_numbers(docs: list[Document]) -> str:
        numbers = [numbers_by_key[doc.url or doc.title] for doc in docs if (doc.url or doc.title) in numbers_by_key]
        return ", ".join(f"[{n}]" for n in numbers) if numbers else "none"

    claims_by_sub_q: dict[str, list[VerifiedClaim]] = {}
    for claim in verified_claims:
        claims_by_sub_q.setdefault(claim.sub_question, []).append(claim)

    sections = []
    for sub_q in plan.sub_questions:
        lines = [f"### {sub_q.question}"]
        claims = claims_by_sub_q.get(sub_q.question, [])
        if claims:
            lines.append("Verified claims:")
            for claim in claims:
                line = (
                    f"- [{claim.verdict.value}, confidence {claim.confidence:.1f}] "
                    f"{claim.text} (cite as: {_cite_numbers(claim.supporting_sources)}"
                )
                if claim.contradicting_sources:
                    line += f"; disagreed with by: {_cite_numbers(claim.contradicting_sources)}"
                line += ")"
                lines.append(line)
        else:
            lines.append("No verified claims are available for this sub-question.")

        excerpts = supplementary_excerpts.get(sub_q.question, [])
        if excerpts:
            lines.append("Background excerpts (unverified context only, do not cite these):")
            lines.extend(f"- {excerpt[:400]}" for excerpt in excerpts)

        sections.append("\n".join(lines))

    if source_index:
        source_list = "\n".join(f"[{i}] {doc.title}" for i, doc in enumerate(source_index, start=1))
        header = f"Numbered sources (cite using these bracketed numbers):\n{source_list}\n\n"
    else:
        header = ""

    return header + "\n\n".join(sections)


def _fallback_draft(plan: ResearchPlan, verified_claims: list[VerifiedClaim]) -> str:
    claims_by_sub_q: dict[str, list[VerifiedClaim]] = {}
    for claim in verified_claims:
        claims_by_sub_q.setdefault(claim.sub_question, []).append(claim)

    lines = [
        f"# {plan.original_query}",
        "",
        "_Gemini was unavailable, so this is an unformatted summary of verified claims, not a written report._",
        "",
    ]
    for sub_q in plan.sub_questions:
        lines.append(f"## {sub_q.question}")
        claims = claims_by_sub_q.get(sub_q.question, [])
        if not claims:
            lines.append("_No verified claims available._")
        for claim in claims:
            supporting = ", ".join(s.title for s in claim.supporting_sources) or "no attributed source"
            lines.append(f"- [{claim.verdict.value}, confidence {claim.confidence:.1f}] {claim.text} (Source: {supporting})")
        lines.append("")
    return "\n".join(lines)


class WriterAgent:
    def __init__(self):
        self.settings = get_settings()

    def draft(
        self,
        plan: ResearchPlan,
        verified_claims: list[VerifiedClaim],
        supplementary_excerpts: dict[str, list[str]] | None = None,
        target_language: str = "English",
        previous_draft: str | None = None,
        feedback: str | None = None,
    ) -> tuple[str, list[str]]:
        """Returns (draft_text, errors). Always returns usable text — a
        failed LLM call degrades to a mechanical claims summary rather
        than an empty string, so the pipeline always produces something."""
        client = get_gemini_client()
        if client is None:
            return (
                _fallback_draft(plan, verified_claims),
                ["GEMINI_API_KEY not configured — used an unformatted claims summary instead of a written draft"],
            )

        revision_block = ""
        if previous_draft and feedback:
            revision_block = REVISION_BLOCK_TEMPLATE.format(previous_draft=previous_draft, feedback=feedback)

        prompt = WRITER_PROMPT.format(
            target_language=target_language,
            original_query=plan.original_query,
            material=_format_material(plan, verified_claims, supplementary_excerpts),
            revision_block=revision_block,
        )

        try:
            response = call_with_backoff(
                lambda: client.models.generate_content(model=self.settings.gemini_model, contents=prompt),
                is_retryable=is_retryable_http_error,
            )
            if not response.text or not response.text.strip():
                raise ValueError("Gemini returned an empty draft")
            return response.text, []
        except Exception as exc:
            return (
                _fallback_draft(plan, verified_claims),
                [f"Writer LLM call failed, used unformatted claims summary instead: {exc}"],
            )
