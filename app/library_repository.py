"""
Saved-library repository (Phase 11).

Pure data-access functions over the normalized library tables (app/db/models).
Everything is scoped by `user_id` — the caller passes the id from the verified
Supabase JWT (see app/auth.py :: get_current_user), and every query filters on
it, so one user can never read or mutate another's rows. This is the in-app
half of the security story; supabase/schema.sql adds RLS as defense-in-depth.

Works on plain JSON-shaped dicts (the same serialized ResearchPipelineResponse
the frontend receives from the SSE "complete" event), so the endpoints can hand
a parsed request body straight in, and reconstruct that exact shape on read —
which is what lets a reopened report reproduce a fresh run byte-for-byte,
including the clickable [n] citations (their numbering is derived from the
verified claims' evidence, preserved here verbatim).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ChartModel,
    ClaimModel,
    FollowUpModel,
    FolderModel,
    ReportModel,
    ResearchSessionModel,
    SessionTagModel,
    SourceModel,
    TagModel,
)

# Which SourceType values are academic "papers" (vs. general "web/reference"),
# for the frontend's tabbed Web / Papers source panel.
_PAPER_SOURCES = {"arxiv", "semantic_scholar", "openalex", "pubmed", "crossref"}

# Job lifecycle states for a saved session (see ResearchSessionModel.status).
# "pending" → "running" are for a run tracked from the start; a result saved
# from a finished run lands directly on a terminal state ("complete"/"error").
VALID_STATUSES = ("pending", "running", "complete", "error")
_TERMINAL_STATUSES = ("complete", "error")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _kind_for_source(source_value: str) -> str:
    return "paper" if source_value in _PAPER_SOURCES else "web"


def _derive_title(result: dict) -> str:
    """The report's H1, else the query — mirrors the old client-side logic."""
    report = result.get("final_report") or ""
    match = re.search(r"^#\s+(.+)$", report, re.MULTILINE)
    title = (match.group(1).strip() if match else "") or (result.get("query") or "").strip()
    title = title or "Untitled research"
    return title if len(title) <= 160 else f"{title[:157]}…"


# --------------------------------------------------------------------------- #
# Document (source) <-> row mapping
# --------------------------------------------------------------------------- #

_DOC_FIELDS = (
    "title", "authors", "abstract", "snippet", "url", "source",
    "published_date", "citation_count", "relevance_score", "raw_id", "sub_question",
)


def _source_row_to_doc(row: SourceModel) -> dict:
    return {
        "title": row.title,
        "authors": row.authors or [],
        "abstract": row.abstract,
        "snippet": row.snippet,
        "url": row.url or "",
        "source": row.source,
        "published_date": row.published_date,
        "citation_count": row.citation_count,
        "relevance_score": row.relevance_score,
        "raw_id": row.raw_id,
        "sub_question": row.sub_question,
    }


def _doc_to_source_row(doc: dict, session_id: str, ordinal: int) -> SourceModel:
    source_value = doc.get("source") or "web"
    return SourceModel(
        session_id=session_id,
        ordinal=ordinal,
        title=doc.get("title") or "Untitled",
        url=doc.get("url") or "",
        authors=doc.get("authors") or [],
        abstract=doc.get("abstract"),
        snippet=doc.get("snippet"),
        source=source_value,
        kind=_kind_for_source(source_value),
        published_date=doc.get("published_date"),
        citation_count=doc.get("citation_count"),
        relevance_score=doc.get("relevance_score"),
        raw_id=doc.get("raw_id"),
        sub_question=doc.get("sub_question"),
    )


# --------------------------------------------------------------------------- #
# Save
# --------------------------------------------------------------------------- #

def save_result_for_user(
    db: Session,
    user_id: str,
    result: dict,
    *,
    citation_style: str = "apa",
    target_language: str = "English",
    num_sub_questions: Optional[int] = None,
    max_results_per_subquestion: int = 5,
    title: Optional[str] = None,
    status: str = "complete",
    error_text: Optional[str] = None,
) -> ResearchSessionModel:
    """Persist a finished research result as a new library entry. Returns the
    created session (with its generated id). Commits.

    ``status`` is the terminal state for the run — "complete" normally, or
    "error" when the pipeline hit an unrecoverable failure (``error_text`` then
    carries the reason). Either way the content that *was* produced is still
    saved, so a partially-failed run remains inspectable in the library."""
    plan = result.get("plan") or {}
    sub_questions = plan.get("sub_questions") or []

    session = ResearchSessionModel(
        user_id=user_id,
        query=result.get("query") or "",
        title=(title or _derive_title(result)),
        status=(status if status in VALID_STATUSES else "complete"),
        error_text=error_text,
        citation_style=citation_style,
        target_language=target_language,
        num_sub_questions=(num_sub_questions if num_sub_questions is not None else len(sub_questions)),
        max_results_per_subquestion=max_results_per_subquestion,
        revision_count=int(result.get("revision_count") or 0),
        review_decision=result.get("review_decision") or "",
        review_feedback=result.get("review_feedback") or "",
        plan_json=sub_questions,
        errors_json=result.get("errors") or [],
        starred=False,
        completed_at=_now(),
    )
    db.add(session)
    db.flush()  # assigns session.id

    db.add(
        ReportModel(
            session_id=session.id,
            final_report=result.get("final_report") or "",
            draft=result.get("draft") or "",
        )
    )

    for i, doc in enumerate(result.get("final_documents") or []):
        db.add(_doc_to_source_row(doc, session.id, i))

    for i, claim in enumerate(result.get("verified_claims") or []):
        db.add(
            ClaimModel(
                session_id=session.id,
                ordinal=i,
                text=claim.get("text") or "",
                sub_question=claim.get("sub_question") or "",
                verdict=claim.get("verdict") or "unverified",
                confidence=float(claim.get("confidence") or 0.0),
                note=claim.get("note"),
                supporting_sources=claim.get("supporting_sources") or [],
                contradicting_sources=claim.get("contradicting_sources") or [],
            )
        )

    for i, chart in enumerate(result.get("chart_specs") or []):
        db.add(
            ChartModel(
                session_id=session.id,
                ordinal=i,
                title=chart.get("title") or "",
                chart_type=chart.get("chart_type") or "bar",
                x_label=chart.get("x_label") or "",
                y_label=chart.get("y_label") or "",
                labels=chart.get("labels") or [],
                values=chart.get("values") or [],
            )
        )

    # Seed follow-up suggestions from the plan's sub-questions.
    for i, sub_q in enumerate(sub_questions):
        question = sub_q.get("question") if isinstance(sub_q, dict) else None
        if question:
            db.add(FollowUpModel(session_id=session.id, ordinal=i, question=question))

    db.commit()
    db.refresh(session)
    return session


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #

def _tag_names_by_session(db: Session, session_ids: list[str]) -> dict[str, list[str]]:
    if not session_ids:
        return {}
    rows = db.execute(
        select(SessionTagModel.session_id, TagModel.name)
        .join(TagModel, TagModel.id == SessionTagModel.tag_id)
        .where(SessionTagModel.session_id.in_(session_ids))
    ).all()
    out: dict[str, list[str]] = {}
    for session_id, name in rows:
        out.setdefault(session_id, []).append(name)
    return out


def list_sessions_for_user(
    db: Session,
    user_id: str,
    *,
    search: Optional[str] = None,
    folder_id: Optional[str] = None,
    starred: Optional[bool] = None,
    tag: Optional[str] = None,
) -> list[dict]:
    """Library list view — lightweight summaries, newest first."""
    stmt = select(ResearchSessionModel).where(ResearchSessionModel.user_id == user_id)

    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            ResearchSessionModel.title.ilike(like) | ResearchSessionModel.query.ilike(like)
        )
    if folder_id is not None:
        stmt = stmt.where(ResearchSessionModel.folder_id == folder_id)
    if starred is not None:
        stmt = stmt.where(ResearchSessionModel.starred == starred)
    if tag:
        stmt = (
            stmt.join(SessionTagModel, SessionTagModel.session_id == ResearchSessionModel.id)
            .join(TagModel, TagModel.id == SessionTagModel.tag_id)
            .where(TagModel.user_id == user_id, TagModel.name == tag)
        )

    stmt = stmt.order_by(ResearchSessionModel.created_at.desc())
    sessions = list(db.execute(stmt).scalars().all())

    tags_map = _tag_names_by_session(db, [s.id for s in sessions])
    return [_summary(s, tags_map.get(s.id, [])) for s in sessions]


def _summary(s: ResearchSessionModel, tags: list[str]) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "query": s.query,
        "status": s.status,
        "starred": s.starred,
        "folder_id": s.folder_id,
        "tags": tags,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _load_session(db: Session, user_id: str, session_id: str) -> Optional[ResearchSessionModel]:
    stmt = (
        select(ResearchSessionModel)
        .where(ResearchSessionModel.id == session_id, ResearchSessionModel.user_id == user_id)
        .options(
            selectinload(ResearchSessionModel.report),
            selectinload(ResearchSessionModel.sources),
            selectinload(ResearchSessionModel.claims),
            selectinload(ResearchSessionModel.charts),
            selectinload(ResearchSessionModel.follow_ups),
        )
    )
    return db.execute(stmt).scalars().first()


def get_session_result(db: Session, user_id: str, session_id: str) -> Optional[dict]:
    """Full library entry: metadata + a ResearchResult-shaped `result` that
    renders identically to a fresh run. None if it doesn't exist / isn't the
    caller's."""
    s = _load_session(db, user_id, session_id)
    if s is None:
        return None

    docs = [_source_row_to_doc(row) for row in s.sources]
    web_results = [d for d, row in zip(docs, s.sources) if row.kind == "web"]
    paper_results = [d for d, row in zip(docs, s.sources) if row.kind == "paper"]

    verified_claims = [
        {
            "text": c.text,
            "sub_question": c.sub_question,
            "supporting_sources": c.supporting_sources or [],
            "contradicting_sources": c.contradicting_sources or [],
            "verdict": c.verdict,
            "confidence": c.confidence,
            "note": c.note,
        }
        for c in s.claims
    ]

    chart_specs = [
        {
            "title": ch.title,
            "chart_type": ch.chart_type,
            "x_label": ch.x_label,
            "y_label": ch.y_label,
            "labels": ch.labels or [],
            "values": ch.values or [],
        }
        for ch in s.charts
    ]

    result = {
        "query": s.query,
        "plan": {"original_query": s.query, "sub_questions": s.plan_json or []},
        "web_results": web_results,
        "paper_results": paper_results,
        "final_documents": docs,
        "verified_claims": verified_claims,
        "draft": s.report.draft if s.report else "",
        "review_decision": s.review_decision,
        "review_feedback": s.review_feedback,
        "revision_count": s.revision_count,
        "final_report": s.report.final_report if s.report else "",
        "chart_specs": chart_specs,
        "errors": s.errors_json or [],
    }

    tags = _tag_names_by_session(db, [s.id]).get(s.id, [])
    return {
        **_summary(s, tags),
        "citation_style": s.citation_style,
        "pdf_url": s.report.pdf_url if s.report else None,
        "follow_ups": [f.question for f in s.follow_ups],
        "result": result,
    }


# --------------------------------------------------------------------------- #
# Mutate (all user-scoped; return True when a row was affected)
# --------------------------------------------------------------------------- #

def _owned_session(db: Session, user_id: str, session_id: str) -> Optional[ResearchSessionModel]:
    return db.execute(
        select(ResearchSessionModel).where(
            ResearchSessionModel.id == session_id,
            ResearchSessionModel.user_id == user_id,
        )
    ).scalars().first()


def rename_session(db: Session, user_id: str, session_id: str, title: str) -> bool:
    s = _owned_session(db, user_id, session_id)
    if s is None:
        return False
    s.title = (title or "").strip() or s.title
    db.commit()
    return True


def set_starred(db: Session, user_id: str, session_id: str, starred: bool) -> bool:
    s = _owned_session(db, user_id, session_id)
    if s is None:
        return False
    s.starred = bool(starred)
    db.commit()
    return True


def move_to_folder(db: Session, user_id: str, session_id: str, folder_id: Optional[str]) -> bool:
    s = _owned_session(db, user_id, session_id)
    if s is None:
        return False
    if folder_id is not None:
        # Only allow moving into a folder the caller owns.
        folder = db.execute(
            select(FolderModel).where(FolderModel.id == folder_id, FolderModel.user_id == user_id)
        ).scalars().first()
        if folder is None:
            return False
    s.folder_id = folder_id
    db.commit()
    return True


def delete_session(db: Session, user_id: str, session_id: str) -> bool:
    s = _owned_session(db, user_id, session_id)
    if s is None:
        return False
    db.delete(s)  # cascades to report/sources/claims/charts/follow_ups/session_tags
    db.commit()
    return True


# --------------------------------------------------------------------------- #
# Job status (Phase 12) — DB-backed lifecycle transitions
#
# The status column starts "complete" for a run saved from a finished result
# (the common path). These helpers let a caller track a run explicitly —
# "running" while it executes, then "complete"/"error" — and poll it. All
# user-scoped, like the other mutators.
# --------------------------------------------------------------------------- #

def set_session_status(
    db: Session, user_id: str, session_id: str, status: str, *, error_text: Optional[str] = None
) -> bool:
    """Transition a saved run's job status. A terminal status
    ("complete"/"error") stamps ``completed_at``; a non-terminal one clears it.
    ``error_text`` is stored as given (pass None to clear a prior error).
    Returns False if the session isn't the caller's; raises ValueError on an
    unknown status."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Unknown status {status!r}; expected one of {VALID_STATUSES}.")
    s = _owned_session(db, user_id, session_id)
    if s is None:
        return False
    s.status = status
    s.error_text = error_text
    s.completed_at = _now() if status in _TERMINAL_STATUSES else None
    db.commit()
    return True


def get_session_status(db: Session, user_id: str, session_id: str) -> Optional[dict]:
    """Lightweight status view for polling — no report/sources/claims loaded.
    None if the session isn't the caller's."""
    s = _owned_session(db, user_id, session_id)
    if s is None:
        return None
    return {
        "id": s.id,
        "status": s.status,
        "error_text": s.error_text,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }


def set_report_pdf_url(db: Session, session_id: str, pdf_url: str) -> None:
    report = db.execute(
        select(ReportModel).where(ReportModel.session_id == session_id)
    ).scalars().first()
    if report is not None:
        report.pdf_url = pdf_url
        db.commit()


def set_chart_png_urls(db: Session, session_id: str, urls_by_ordinal: dict[int, str]) -> None:
    """Attach signed PNG URLs to a session's charts, keyed by ordinal."""
    if not urls_by_ordinal:
        return
    charts = db.execute(
        select(ChartModel).where(ChartModel.session_id == session_id)
    ).scalars().all()
    for chart in charts:
        url = urls_by_ordinal.get(chart.ordinal)
        if url:
            chart.png_url = url
    db.commit()


# --------------------------------------------------------------------------- #
# Folders
# --------------------------------------------------------------------------- #

def list_folders(db: Session, user_id: str) -> list[dict]:
    rows = db.execute(
        select(FolderModel).where(FolderModel.user_id == user_id).order_by(FolderModel.name)
    ).scalars().all()
    return [{"id": f.id, "name": f.name} for f in rows]


def create_folder(db: Session, user_id: str, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Folder name is required.")
    existing = db.execute(
        select(FolderModel).where(FolderModel.user_id == user_id, FolderModel.name == name)
    ).scalars().first()
    if existing:
        return {"id": existing.id, "name": existing.name}
    folder = FolderModel(user_id=user_id, name=name)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name}


def delete_folder(db: Session, user_id: str, folder_id: str) -> bool:
    folder = db.execute(
        select(FolderModel).where(FolderModel.id == folder_id, FolderModel.user_id == user_id)
    ).scalars().first()
    if folder is None:
        return False
    db.delete(folder)  # sessions' folder_id is set NULL by the FK rule
    db.commit()
    return True


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #

def list_tags(db: Session, user_id: str) -> list[dict]:
    rows = db.execute(
        select(TagModel).where(TagModel.user_id == user_id).order_by(TagModel.name)
    ).scalars().all()
    return [{"id": t.id, "name": t.name} for t in rows]


def _get_or_create_tag(db: Session, user_id: str, name: str) -> TagModel:
    name = name.strip()
    tag = db.execute(
        select(TagModel).where(TagModel.user_id == user_id, TagModel.name == name)
    ).scalars().first()
    if tag is None:
        tag = TagModel(user_id=user_id, name=name)
        db.add(tag)
        db.flush()
    return tag


def set_session_tags(db: Session, user_id: str, session_id: str, tag_names: Iterable[str]) -> Optional[list[str]]:
    """Replace a session's tags with `tag_names` (created if new). Returns the
    resulting tag names, or None if the session isn't the caller's."""
    s = _owned_session(db, user_id, session_id)
    if s is None:
        return None

    clean = []
    seen = set()
    for raw in tag_names:
        name = (raw or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            clean.append(name)

    # Clear existing links, then relink.
    db.query(SessionTagModel).filter(SessionTagModel.session_id == session_id).delete()
    for name in clean:
        tag = _get_or_create_tag(db, user_id, name)
        db.add(SessionTagModel(session_id=session_id, tag_id=tag.id))
    db.commit()
    return clean
