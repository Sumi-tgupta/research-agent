"""
Pipeline, wired end-to-end through Phase 5:

    planner -> search_all -> retrieve_all -> dedupe_and_rank -> fact_check
        -> writer -> reviewer -(revise, under the cap)-> writer
                            \\-(approved, or cap reached)-> add_citations -> generate_charts -> END

`search_all` / `retrieve_all` loop over the Planner's sub-questions
sequentially rather than fanning out in parallel. That's deliberate, not
just simple: ArXiv explicitly asks for a delay between requests (the
`arxiv` package already enforces this), and the web-search and Semantic
Scholar free tiers punish bursts more than they punish a few extra seconds
of wall-clock time. Sequential looping is naturally polite to all three.

The writer/reviewer loop is capped by `max_revisions` (default 2 total
review passes, i.e. at most one revision cycle) so a Reviewer that keeps
finding something to fix can't loop forever or run up free-tier API usage
unbounded. The Reviewer itself also defaults to APPROVE on failure, which
is a second, independent guard against getting stuck.

`add_citations` and `generate_charts` produce data (final_report text,
chart_specs), not files — actually rendering chart PNGs or a PDF is a
separate, on-demand step (see chart_render.py / pdf_export.py, called from
main.py) rather than something every /research call does whether or not a
file is wanted.

This does not replace Phase 1's endpoints or scripts/smoke_test_graph.py —
those still test Search Agent and Paper Retrieval Agent in isolation with
a single query. This is the real pipeline; that one's a focused smoke test.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.chart_agent import ChartAgent
from app.agents.crossref_agent import CrossrefAgent
from app.agents.fact_checker_agent import FactCheckerAgent
from app.agents.openalex_agent import OpenAlexAgent
from app.agents.paper_retrieval_agent import PaperRetrievalAgent
from app.agents.planner_agent import planner_node
from app.agents.pubmed_agent import PubMedAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.search_agent import SearchAgent
from app.agents.wikipedia_agent import WikipediaAgent
from app.agents.writer_agent import WriterAgent
from app.citations import append_references_section, build_source_index
from app.config import get_settings
from app.embedding_service import get_default_embedder
from app.retrieval_index import build_retrieval_index, retrieve_supplementary_excerpts
from app.schemas import ChartSpec, Document, ReviewDecision, ResearchPlan, VerifiedClaim
from app.vector_store import VectorStore

DEFAULT_MAX_REVISIONS = 2


class PipelineState(TypedDict, total=False):
    query: str
    num_sub_questions: int
    max_results_per_subquestion: int
    target_language: str
    max_revisions: int
    citation_style: str
    plan: ResearchPlan
    web_results: list[Document]
    paper_results: list[Document]
    final_documents: list[Document]
    verified_claims: list[VerifiedClaim]
    draft: str
    review_decision: str
    review_feedback: str
    revision_count: int
    final_report: str
    chart_specs: list[ChartSpec]
    errors: list[str]


def _web_agents(settings) -> list:
    """Web-tier retrievers, in query order. SearchAgent is the core web
    search (a free-tier provider chain — Exa → Serper → DuckDuckGo); Wikipedia
    adds encyclopedic grounding. Each is a plain object exposing
    `.run(query, max_results=...) -> AgentResult`, so the gather loop treats
    them uniformly. Toggle Wikipedia off via ENABLE_WIKIPEDIA without code
    changes."""
    agents = [SearchAgent()]
    if settings.enable_wikipedia:
        agents.append(WikipediaAgent())
    return agents


def _academic_agents(settings) -> list:
    """Paper-tier retrievers. PaperRetrievalAgent already covers arXiv +
    Semantic Scholar; OpenAlex, Europe PMC (PubMed), and Crossref are added
    when enabled. All keyless/free and independently toggleable."""
    agents = [PaperRetrievalAgent()]
    if settings.enable_openalex:
        agents.append(OpenAlexAgent())
    if settings.enable_pubmed:
        agents.append(PubMedAgent())
    if settings.enable_crossref:
        agents.append(CrossrefAgent())
    return agents


def _gather_over_subquestions(sub_questions, agents, query_of, max_results, label):
    """Runs every enabled retriever over every sub-question and merges the
    results, tagging each Document with the sub-question it came from.

    Concurrency mirrors the original single-source design: sub-questions run
    in parallel (one worker each), while the sources *within* a sub-question
    run sequentially in that worker. That keeps us polite to any one service
    (never more than `len(sub_questions)` concurrent hits to the same API,
    same as before) while still adding breadth across services. A failure in
    one source is captured in `errors`, never raised, so it can't sink the
    others."""
    documents: list[Document] = []
    errors: list[str] = []

    def worker(sub_q):
        query = query_of(sub_q)
        docs: list[Document] = []
        errs: list[str] = []
        for agent in agents:
            result = agent.run(query, max_results=max_results)
            for doc in result.documents:
                doc.sub_question = sub_q.question
            docs.extend(result.documents)
            errs.extend(result.errors)
        return docs, errs

    with ThreadPoolExecutor(max_workers=min(5, max(1, len(sub_questions)))) as executor:
        futures = [executor.submit(worker, sub_q) for sub_q in sub_questions]
        for future in as_completed(futures):
            try:
                docs, errs = future.result()
                documents.extend(docs)
                errors.extend(errs)
            except Exception as exc:
                errors.append(f"{label} sub-question worker failed: {exc}")

    return documents, errors


def search_all_subquestions_node(state: PipelineState) -> dict:
    plan = state["plan"]
    max_results = state.get("max_results_per_subquestion", 5)
    agents = _web_agents(get_settings())

    documents, errors = _gather_over_subquestions(
        plan.sub_questions,
        agents,
        query_of=lambda sub_q: sub_q.web_query,
        max_results=max_results,
        label="Web search",
    )
    return {"web_results": documents, "errors": [*state.get("errors", []), *errors]}


def retrieve_all_subquestions_node(state: PipelineState) -> dict:
    plan = state["plan"]
    max_results = state.get("max_results_per_subquestion", 5)
    agents = _academic_agents(get_settings())

    documents, errors = _gather_over_subquestions(
        plan.sub_questions,
        agents,
        query_of=lambda sub_q: sub_q.academic_query,
        max_results=max_results,
        label="Paper retrieval",
    )
    return {"paper_results": documents, "errors": [*state.get("errors", []), *errors]}


def dedupe_and_rank_node(state: PipelineState) -> dict:
    all_documents = [*state.get("web_results", []), *state.get("paper_results", [])]
    errors = list(state.get("errors", []))

    try:
        store = VectorStore(get_default_embedder())
        deduped = store.add_and_dedupe(all_documents)
        ranked = store.rank_by_relevance(state["query"], deduped)
        return {"final_documents": ranked, "errors": errors}
    except Exception as exc:
        # e.g. no internet access to download the embedding model on first
        # run. Degrade to unranked, undeduped results rather than failing
        # the whole pipeline.
        errors.append(f"Dedup/ranking unavailable, returning raw results: {exc}")
        return {"final_documents": all_documents, "errors": errors}


def fact_check_node(state: PipelineState) -> dict:
    plan = state["plan"]
    documents = state.get("final_documents", [])
    errors = list(state.get("errors", []))

    by_sub_question: dict[str, list[Document]] = {}
    for doc in documents:
        key = doc.sub_question or plan.original_query
        by_sub_question.setdefault(key, []).append(doc)

    try:
        embedder = get_default_embedder()
    except Exception:
        embedder = None

    agent = FactCheckerAgent(embedder=embedder)
    all_claims: list[VerifiedClaim] = []

    for sub_q in plan.sub_questions:
        sub_docs = by_sub_question.get(sub_q.question, [])
        claims, sub_errors = agent.run(sub_q.question, sub_docs)
        all_claims.extend(claims)
        errors.extend(sub_errors)

    return {"verified_claims": all_claims, "errors": errors}


def writer_node(state: PipelineState) -> dict:
    plan = state["plan"]
    verified_claims = state.get("verified_claims", [])
    errors = list(state.get("errors", []))

    # Supplementary retrieval is a nice-to-have on top of verified_claims —
    # a third LocalEmbedder-style load (see the note in fact_check_node);
    # if it fails, the Writer still runs on verified_claims alone.
    supplementary: dict[str, list[str]] = {}
    try:
        index = build_retrieval_index(state.get("final_documents", []))
        for sub_q in plan.sub_questions:
            supplementary[sub_q.question] = retrieve_supplementary_excerpts(index, sub_q.question)
    except Exception as exc:
        errors.append(f"Supplementary retrieval unavailable, writing from verified claims alone: {exc}")

    agent = WriterAgent()
    draft, writer_errors = agent.draft(
        plan=plan,
        verified_claims=verified_claims,
        supplementary_excerpts=supplementary,
        target_language=state.get("target_language", "English"),
        previous_draft=state.get("draft"),
        feedback=state.get("review_feedback"),
    )
    errors.extend(writer_errors)

    return {"draft": draft, "errors": errors}


def reviewer_node(state: PipelineState) -> dict:
    agent = ReviewerAgent()
    result, errors = agent.review(state["plan"], state["draft"], state.get("verified_claims", []))

    return {
        "review_decision": result.decision.value,
        "review_feedback": result.feedback,
        "revision_count": state.get("revision_count", 0) + 1,
        "errors": [*state.get("errors", []), *errors],
    }


def route_after_review(state: PipelineState) -> str:
    max_revisions = state.get("max_revisions", DEFAULT_MAX_REVISIONS)
    if state.get("review_decision") == ReviewDecision.REVISE.value and state.get("revision_count", 0) < max_revisions:
        return "revise"
    return "done"


def add_citations_node(state: PipelineState) -> dict:
    """Appends a References/Works Cited section listing only the sources
    the Writer actually cited (by [N] marker). Deterministic — no LLM call
    here, see citations.py's module docstring for why."""
    verified_claims = state.get("verified_claims", [])
    source_index = build_source_index(verified_claims)
    style = state.get("citation_style", "apa")
    final_report = append_references_section(state.get("draft", ""), source_index, style=style)
    return {"final_report": final_report}


def generate_charts_node(state: PipelineState) -> dict:
    agent = ChartAgent()
    chart_specs, errors = agent.extract(state.get("verified_claims", []))
    return {"chart_specs": chart_specs, "errors": [*state.get("errors", []), *errors]}


def build_research_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("planner", planner_node)
    graph.add_node("search_all", search_all_subquestions_node)
    graph.add_node("retrieve_all", retrieve_all_subquestions_node)
    graph.add_node("dedupe_and_rank", dedupe_and_rank_node)
    graph.add_node("fact_check", fact_check_node)
    graph.add_node("writer", writer_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("add_citations", add_citations_node)
    graph.add_node("generate_charts", generate_charts_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "search_all")
    graph.add_edge("search_all", "retrieve_all")
    graph.add_edge("retrieve_all", "dedupe_and_rank")
    graph.add_edge("dedupe_and_rank", "fact_check")
    graph.add_edge("fact_check", "writer")
    graph.add_edge("writer", "reviewer")
    graph.add_conditional_edges("reviewer", route_after_review, {"revise": "writer", "done": "add_citations"})
    graph.add_edge("add_citations", "generate_charts")
    graph.add_edge("generate_charts", END)

    return graph.compile()
