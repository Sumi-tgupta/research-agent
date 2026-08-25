"""
FastAPI app — Phase 0-6.

Each agent still gets its own endpoint for isolated testing. The pipeline
itself is exposed three ways:
  - /research         blocking call, full JSON result
  - /research/stream   Server-Sent Events, one event per pipeline stage —
                        what the React frontend (frontend/) uses for its
                        live status view
  - /research/pdf       blocking call, returns a downloadable PDF directly

Run with:

    uvicorn app.main:app --reload

Then try:
    curl -X POST http://localhost:8000/agents/search        -H "Content-Type: application/json" -d '{"query": "small modular reactors"}'
    curl -X POST http://localhost:8000/research               -H "Content-Type: application/json" -d '{"query": "impact of microplastics on marine food webs"}'
    curl -N -X POST http://localhost:8000/research/stream -H "Content-Type: application/json" -d '{"query": "impact of microplastics on marine food webs"}'
    curl -X POST http://localhost:8000/research/pdf -o report.pdf -H "Content-Type: application/json" -d '{"query": "impact of microplastics on marine food webs"}'

CORS is wide open (allow_origins=["*"]) since this is a local dev project,
not a deployed service — tighten this to your actual frontend origin
before putting it anywhere public.

/agents/writer and /agents/reviewer take a plan + verified_claims directly
(e.g. copy-pasted from a prior /research response) rather than gathering
their own sources — useful for iterating on prompt/translation behavior
without re-running the whole (slower, rate-limited) pipeline each time.
"""

import os
import tempfile

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.agents.fact_checker_agent import FactCheckerAgent
from app.agents.paper_retrieval_agent import PaperRetrievalAgent
from app.agents.planner_agent import PlannerAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.search_agent import SearchAgent
from app.agents.writer_agent import WriterAgent
from app.chart_render import render_charts
from app.graph import DEFAULT_MAX_REVISIONS, build_research_graph
from app.pdf_export import generate_pdf
from app.schemas import AgentResult, ChartSpec, Document, ResearchPlan, VerifiedClaim
from app.stream_events import STAGE_LABELS, format_sse_event, serialize, summarize_stage
from app.embedding_service import get_default_embedder

from app.db.session import init_db

app = FastAPI(title="Apex-Research Multi-Agent System", description="Phase 0-7 Enterprise Deep Research Platform")

@app.on_event("startup")
def on_startup():
    init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    max_results: int | None = None


class PlanRequest(BaseModel):
    query: str
    num_sub_questions: int = 4


class PlannerResponse(BaseModel):
    plan: ResearchPlan
    errors: list[str]


class FactCheckRequest(BaseModel):
    sub_question: str
    max_sources: int = 6


class FactCheckResponse(BaseModel):
    sub_question: str
    claims: list[VerifiedClaim]
    errors: list[str]


class WriterTestRequest(BaseModel):
    plan: ResearchPlan
    verified_claims: list[VerifiedClaim]
    target_language: str = "English"
    previous_draft: str | None = None
    feedback: str | None = None


class WriterTestResponse(BaseModel):
    draft: str
    errors: list[str]


class ReviewerTestRequest(BaseModel):
    plan: ResearchPlan
    draft: str
    verified_claims: list[VerifiedClaim]


class ReviewerTestResponse(BaseModel):
    decision: str
    feedback: str
    errors: list[str]


class ResearchRequest(BaseModel):
    query: str
    num_sub_questions: int = 4
    max_results_per_subquestion: int = 5
    target_language: str = "English"
    max_revisions: int = DEFAULT_MAX_REVISIONS
    citation_style: str = "apa"  # "apa" or "mla"


class ResearchPipelineResponse(BaseModel):
    query: str
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "phases_complete": [0, 1, 2, 3, 4, 5, 6]}


@app.post("/agents/search", response_model=AgentResult)
def run_search_agent(req: QueryRequest) -> AgentResult:
    return SearchAgent().run(req.query, max_results=req.max_results)


@app.post("/agents/papers", response_model=AgentResult)
def run_paper_agent(req: QueryRequest) -> AgentResult:
    return PaperRetrievalAgent().run(req.query, max_results=req.max_results)


@app.post("/agents/planner", response_model=PlannerResponse)
def run_planner_agent(req: PlanRequest) -> PlannerResponse:
    plan, errors = PlannerAgent().run(req.query, num_sub_questions=req.num_sub_questions)
    return PlannerResponse(plan=plan, errors=errors)


@app.post("/agents/fact_checker", response_model=FactCheckResponse)
def run_fact_checker_agent(req: FactCheckRequest) -> FactCheckResponse:
    """Self-contained for isolated testing: gathers its own sources via
    Search + Paper Retrieval for `sub_question`, then fact-checks them —
    mirroring how the full pipeline feeds it, without needing the Planner
    or a prior /research call first."""
    search_result = SearchAgent().run(req.sub_question, max_results=req.max_sources)
    paper_result = PaperRetrievalAgent().run(req.sub_question, max_results=req.max_sources)
    sources = [*search_result.documents, *paper_result.documents]

    try:
        embedder = get_default_embedder()
    except Exception:
        embedder = None

    claims, fact_check_errors = FactCheckerAgent(embedder=embedder).run(
        req.sub_question, sources, max_sources=req.max_sources
    )
    errors = [*search_result.errors, *paper_result.errors, *fact_check_errors]
    return FactCheckResponse(sub_question=req.sub_question, claims=claims, errors=errors)


@app.post("/agents/writer", response_model=WriterTestResponse)
def run_writer_agent(req: WriterTestRequest) -> WriterTestResponse:
    draft, errors = WriterAgent().draft(
        plan=req.plan,
        verified_claims=req.verified_claims,
        target_language=req.target_language,
        previous_draft=req.previous_draft,
        feedback=req.feedback,
    )
    return WriterTestResponse(draft=draft, errors=errors)


@app.post("/agents/reviewer", response_model=ReviewerTestResponse)
def run_reviewer_agent(req: ReviewerTestRequest) -> ReviewerTestResponse:
    result, errors = ReviewerAgent().review(req.plan, req.draft, req.verified_claims)
    return ReviewerTestResponse(decision=result.decision.value, feedback=result.feedback, errors=errors)


@app.post("/research/stream")
def run_research_pipeline_stream(req: ResearchRequest) -> StreamingResponse:
    """Same pipeline as /research, but streams one Server-Sent Event per
    pipeline stage as it completes (via graph.stream(), not .invoke()),
    ending with a final event carrying the complete result. This is what
    the frontend's live status view consumes.

    Every pass through the writer/reviewer revision loop streams as its
    own event too — if the Reviewer sends a draft back, the client sees
    "Writer" fire a second time, then "Reviewer" again."""

    def event_stream():
        graph = build_research_graph()
        state: dict = {}
        try:
            for update in graph.stream(_build_input_state(req), stream_mode="updates"):
                for node_name, node_update in update.items():
                    state.update(node_update)
                    yield format_sse_event(
                        {
                            "type": "stage",
                            "stage": node_name,
                            "label": STAGE_LABELS.get(node_name, node_name),
                            "summary": summarize_stage(node_name, node_update),
                            "errors": node_update.get("errors", []),
                        }
                    )
        except Exception as exc:
            # Every node has its own fallback logic already — reaching
            # here means something genuinely unanticipated broke mid-
            # stream. Still send a "complete" event with whatever partial
            # state was accumulated (plan guaranteed present) rather than
            # just stopping, so the frontend doesn't sit stuck on
            # "running" forever with nothing to show.
            state.setdefault("plan", ResearchPlan(original_query=req.query, sub_questions=[]))
            state["errors"] = [*state.get("errors", []), f"Pipeline failed unexpectedly: {exc}"]
            yield format_sse_event({"type": "error", "message": str(exc)})
            yield format_sse_event({"type": "complete", "result": serialize(_response_dict(req, state))})
            return

        yield format_sse_event({"type": "complete", "result": serialize(_response_dict(req, state))})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/research", response_model=ResearchPipelineResponse)
def run_research_pipeline(req: ResearchRequest) -> ResearchPipelineResponse:
    """Runs the full graph: planner -> search_all -> retrieve_all ->
    dedupe_and_rank -> fact_check -> writer <-> reviewer -> add_citations
    -> generate_charts. The real pipeline, not a single-agent test."""
    state = _invoke_pipeline(req)
    return ResearchPipelineResponse(**_response_dict(req, state))


@app.post("/research/pdf")
def run_research_pipeline_pdf(req: ResearchRequest) -> FileResponse:
    """Runs the full pipeline, then renders the result straight to a
    downloadable PDF. If you already have a result (e.g. from /research or
    /research/stream) and just want the PDF, use /reports/pdf instead —
    it skips re-running the whole pipeline."""
    state = _invoke_pipeline(req)
    return _render_pdf_response(
        title=state["plan"].original_query,
        final_report=state.get("final_report", ""),
        chart_specs=state.get("chart_specs", []),
    )


class ReportPdfRequest(BaseModel):
    title: str
    final_report: str
    chart_specs: list[ChartSpec] = []


@app.post("/reports/pdf")
def render_report_to_pdf(req: ReportPdfRequest) -> FileResponse:
    """Renders an already-computed report — e.g. copy-pasted from a prior
    /research or /research/stream result — to a PDF, without re-running
    the pipeline. This is what the frontend calls for its download button,
    since it already has everything from the stream's final event."""
    return _render_pdf_response(title=req.title, final_report=req.final_report, chart_specs=req.chart_specs)


def _render_pdf_response(title: str, final_report: str, chart_specs: list[ChartSpec]) -> FileResponse:
    chart_image_paths: list[str] = []
    if chart_specs:
        chart_dir = tempfile.mkdtemp(prefix="research_charts_")
        chart_image_paths = render_charts(chart_specs, chart_dir)

    pdf_dir = tempfile.mkdtemp(prefix="research_report_")
    pdf_path = os.path.join(pdf_dir, "report.pdf")
    generate_pdf(title=title, report_text=final_report, output_path=pdf_path, chart_image_paths=chart_image_paths)

    return FileResponse(pdf_path, media_type="application/pdf", filename="research_report.pdf")


def _build_input_state(req: ResearchRequest) -> dict:
    return {
        "query": req.query,
        "num_sub_questions": req.num_sub_questions,
        "max_results_per_subquestion": req.max_results_per_subquestion,
        "target_language": req.target_language,
        "max_revisions": req.max_revisions,
        "citation_style": req.citation_style,
    }


def _invoke_pipeline(req: ResearchRequest) -> dict:
    """Every node already has its own fallback logic (see each agent's
    module docstring) — reaching this except-block means something
    genuinely unanticipated broke deeper in the graph itself, not a
    documented failure mode. Rather than letting that reach the caller as
    a raw 500, this returns the minimum valid shape (_response_dict reads
    state["plan"] unconditionally) with the failure clearly surfaced."""
    graph = build_research_graph()
    try:
        return graph.invoke(_build_input_state(req))
    except Exception as exc:
        return {
            "plan": ResearchPlan(original_query=req.query, sub_questions=[]),
            "errors": [f"Pipeline failed unexpectedly: {exc}"],
        }


def _response_dict(req: ResearchRequest, state: dict) -> dict:
    return {
        "query": req.query,
        "plan": state["plan"],
        "web_results": state.get("web_results", []),
        "paper_results": state.get("paper_results", []),
        "final_documents": state.get("final_documents", []),
        "verified_claims": state.get("verified_claims", []),
        "draft": state.get("draft", ""),
        "review_decision": state.get("review_decision", ""),
        "review_feedback": state.get("review_feedback", ""),
        "revision_count": state.get("revision_count", 0),
        "final_report": state.get("final_report", ""),
        "chart_specs": state.get("chart_specs", []),
        "errors": state.get("errors", []),
    }
