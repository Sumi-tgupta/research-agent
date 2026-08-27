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

CORS is restricted to the origins in ALLOWED_ORIGINS (default: the Next.js
dev server at http://localhost:3000). Set ALLOWED_ORIGINS="*" for wide-open
access during local experimentation, or list your real frontend origin(s)
before deploying anywhere public.

/agents/writer and /agents/reviewer take a plan + verified_claims directly
(e.g. copy-pasted from a prior /research response) rather than gathering
their own sources — useful for iterating on prompt/translation behavior
without re-running the whole (slower, rate-limited) pipeline each time.
"""

import logging
import os
import tempfile
from typing import Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

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
from app.auth import AuthUser, get_optional_user
from app.config import get_settings
from app.rate_limit import enforce_rate_limit

from app.db.session import init_db
from app import library_repository as _library_repo
from app import storage as _storage
from app.routers.library import router as library_router

def _init_sentry() -> None:
    """Optionally wire Sentry error monitoring (Phase 13).

    Fully env-driven and best-effort: a blank SENTRY_DSN is a no-op, a missing
    sentry-sdk just logs a hint, and any init failure is swallowed. Nothing here
    can break app startup — monitoring is a pure add-on. Runs at import time
    (before the app is created) so it can also catch import/startup errors.
    """
    settings = get_settings()
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
    except ModuleNotFoundError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk isn't installed; skipping error "
            "monitoring. Enable it with: pip install sentry-sdk"
        )
        return
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,  # never ship user PII to the monitor
        )
    except Exception:  # pragma: no cover - monitoring must never break boot
        logging.getLogger(__name__).warning(
            "Sentry init failed; continuing without error monitoring.",
            exc_info=True,
        )


_init_sentry()

app = FastAPI(title="Apex-Research Multi-Agent System", description="Phase 0-7 Enterprise Deep Research Platform")

@app.on_event("startup")
def on_startup():
    init_db()

# CORS: allow the configured frontend origins (Next.js dev server on :3000 by
# default). Set ALLOWED_ORIGINS in the environment to change this — "*" allows
# any origin, which is fine for local dev but should be tightened for a real
# deployment. See app/config.py.
_origins = get_settings().allowed_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Wildcard origins can't be combined with credentialed requests per the
    # CORS spec; the frontend doesn't send cookies to this API, so this is safe.
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Baseline security headers on every response (Phase 12). This is a pure JSON /
# SSE / PDF API that serves no HTML of its own, so a deny-everything CSP and
# frame policy cost nothing here while still hardening the responses. HSTS is
# added only in production, since forcing HTTPS on http://localhost during dev
# would be counterproductive. `setdefault` guarantees we never overwrite a
# header a response already set (e.g. content-type), so this is safe to run in
# front of the CORS middleware and the streaming/file responses alike.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-XSS-Protection": "0",  # modern browsers: disable the legacy, buggy auditor
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if get_settings().app_env == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
        )
    return response

# Saved-library endpoints (Phase 11). These require a signed-in user; anonymous
# research on the /research* endpoints below is unaffected.
app.include_router(library_router)


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
    """Public entry point for the whole pipeline, so its inputs are validated
    strictly (Phase 12): every field is bounded, the query can't be blank or
    unbounded, and citation_style is constrained to the two styles the writer
    actually supports. Bad input fails fast with a 422 here rather than wasting
    an LLM/search run — and the upper bounds cap how expensive any single call
    a caller can request is."""

    query: str = Field(min_length=3, max_length=2000)
    num_sub_questions: int = Field(default=4, ge=1, le=10)
    max_results_per_subquestion: int = Field(default=5, ge=1, le=20)
    target_language: str = Field(default="English", min_length=2, max_length=60)
    max_revisions: int = Field(default=DEFAULT_MAX_REVISIONS, ge=0, le=5)
    citation_style: Literal["apa", "mla"] = "apa"

    @field_validator("query", "target_language", mode="before")
    @classmethod
    def _strip_text(cls, v):
        """Trim surrounding whitespace before the length checks run, so a
        whitespace-only query collapses to "" and is rejected by min_length
        rather than sneaking past as 3+ spaces."""
        return v.strip() if isinstance(v, str) else v

    @field_validator("citation_style", mode="before")
    @classmethod
    def _normalize_citation_style(cls, v):
        """Accept "APA"/"Mla"/etc. by normalizing case before the Literal check;
        anything not apa/mla still fails validation with a clear 422."""
        return v.lower().strip() if isinstance(v, str) else v


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
    # Set when the request was authenticated and the result was auto-saved to
    # the caller's library (Phase 11); None for anonymous requests.
    saved_id: Optional[str] = None


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
def run_research_pipeline_stream(
    req: ResearchRequest,
    user: Optional[AuthUser] = Depends(get_optional_user),
    _rate=Depends(enforce_rate_limit),
) -> StreamingResponse:
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

        # Success path: send the result immediately, then (for signed-in
        # users) persist it. The DB save is fast and its id rides along on the
        # complete event; the optional file offload runs afterward so it can't
        # delay what the client sees.
        final = serialize(_response_dict(req, state))
        saved_id = _persist_for_user(req, user, final)
        if saved_id:
            final["saved_id"] = saved_id
        yield format_sse_event({"type": "complete", "result": final})
        if saved_id:
            _offload_storage_safe(saved_id, final)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/research", response_model=ResearchPipelineResponse)
def run_research_pipeline(
    req: ResearchRequest,
    background_tasks: BackgroundTasks,
    user: Optional[AuthUser] = Depends(get_optional_user),
    _rate=Depends(enforce_rate_limit),
) -> ResearchPipelineResponse:
    """Runs the full graph: planner -> search_all -> retrieve_all ->
    dedupe_and_rank -> fact_check -> writer <-> reviewer -> add_citations
    -> generate_charts. The real pipeline, not a single-agent test.

    For signed-in users the result is auto-saved to their library (best-effort;
    a save failure never fails the request) and `saved_id` is returned. Any
    durable file offload runs as a background task after the response is sent."""
    state = _invoke_pipeline(req)
    result = _response_dict(req, state)
    serialized = serialize(result)
    saved_id = _persist_for_user(req, user, serialized)
    if saved_id:
        background_tasks.add_task(_offload_storage_safe, saved_id, serialized)
    return ResearchPipelineResponse(**result, saved_id=saved_id)


@app.post("/research/pdf")
def run_research_pipeline_pdf(
    req: ResearchRequest,
    _rate=Depends(enforce_rate_limit),
) -> FileResponse:
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


# --------------------------------------------------------------------------- #
# Phase 11 — server-side auto-persist for signed-in users
#
# Research itself stays anonymous-first: these helpers only do anything when a
# verified user is present, and they are strictly best-effort — a persistence
# failure must never turn a successful research run into an error response, so
# every path swallows its exceptions and simply skips the save. `serialized`
# is the JSON-safe result dict (post-`serialize`), matching what the frontend
# receives and what library_repository expects.
# --------------------------------------------------------------------------- #

def _persist_for_user(
    req: ResearchRequest, user: Optional[AuthUser], serialized: dict
) -> Optional[str]:
    """Save a finished result to the user's library. Returns the new library
    id, or None (anonymous request, or a swallowed failure). Fast: writes only
    to the database — durable file offload happens separately, off the critical
    path (see _offload_storage_safe)."""
    if user is None:
        return None

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # A run that fell through to the pipeline's top-level failure handler
        # carries a "Pipeline failed unexpectedly: ..." error; record it as an
        # "error" job (with the reason) instead of a silent "complete". Partial
        # content, if any, is still saved so the run stays inspectable.
        errors = serialized.get("errors") or []
        fatal = next(
            (e for e in errors if isinstance(e, str) and e.startswith("Pipeline failed unexpectedly")),
            None,
        )
        session = _library_repo.save_result_for_user(
            db,
            user.id,
            serialized,
            citation_style=req.citation_style,
            target_language=req.target_language,
            num_sub_questions=req.num_sub_questions,
            max_results_per_subquestion=req.max_results_per_subquestion,
            status=("error" if fatal else "complete"),
            error_text=fatal,
        )
        return session.id
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _offload_storage_safe(session_id: str, serialized: dict) -> None:
    """Best-effort: render the report PDF and chart PNGs and push them to
    Supabase Storage, recording the signed URLs on the saved rows. No-op unless
    Storage is configured (SUPABASE_URL + SUPABASE_SERVICE_KEY); disabled by
    default, so the common path costs nothing. Runs after the response is sent
    (SSE: after the final yield; blocking: as a BackgroundTask), so the extra
    render latency never delays the result. Never raises."""
    try:
        if not _storage.storage_enabled():
            return

        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            chart_specs_json = serialized.get("chart_specs") or []
            chart_image_paths: list[str] = []
            if chart_specs_json:
                specs = [ChartSpec(**c) for c in chart_specs_json]
                chart_dir = tempfile.mkdtemp(prefix="research_charts_")
                chart_image_paths = render_charts(specs, chart_dir)
                urls_by_ordinal: dict[int, str] = {}
                for i, path in enumerate(chart_image_paths):
                    with open(path, "rb") as fh:
                        url = _storage.upload_chart_png(session_id, i, fh.read())
                    if url:
                        urls_by_ordinal[i] = url
                if urls_by_ordinal:
                    _library_repo.set_chart_png_urls(db, session_id, urls_by_ordinal)

            final_report = serialized.get("final_report") or ""
            if final_report:
                pdf_dir = tempfile.mkdtemp(prefix="research_report_")
                pdf_path = os.path.join(pdf_dir, "report.pdf")
                generate_pdf(
                    title=serialized.get("query") or "Research report",
                    report_text=final_report,
                    output_path=pdf_path,
                    chart_image_paths=chart_image_paths,
                )
                with open(pdf_path, "rb") as fh:
                    url = _storage.upload_report_pdf(session_id, fh.read())
                if url:
                    _library_repo.set_report_pdf_url(db, session_id, url)
        finally:
            db.close()
    except Exception:
        # Durable offload is a nice-to-have; the DB row already reconstructs the
        # full report and PDFs re-render on demand via /reports/pdf.
        return
