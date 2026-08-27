"""
PostgreSQL 17 & SQLite Compatible Data Models for Apex-Research.

Implements persistent storage for users, research jobs, claims, citations,
and audit logs as specified in the enterprise architecture blueprint.
"""

from datetime import datetime, timezone
import uuid
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Numeric,
    ForeignKey,
    JSON,
    Float,
    Boolean,
    Integer,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="researcher", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    jobs = relationship("ResearchJobModel", back_populates="user", cascade="all, delete-orphan")


class ResearchJobModel(Base):
    __tablename__ = "research_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    query = Column(Text, nullable=False)
    depth_level = Column(String(50), default="deep", nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cost_usd = Column(Numeric(10, 4), default=0.0000)
    final_report = Column(Text, nullable=True)

    user = relationship("UserModel", back_populates="jobs")
    verified_claims = relationship("VerifiedClaimModel", back_populates="job", cascade="all, delete-orphan")
    document_sources = relationship("DocumentSourceModel", back_populates="job", cascade="all, delete-orphan")


class VerifiedClaimModel(Base):
    __tablename__ = "verified_claims"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sub_question = Column(Text, nullable=False)
    claim_text = Column(Text, nullable=False)
    verdict = Column(String(50), nullable=False)
    confidence_score = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    job = relationship("ResearchJobModel", back_populates="verified_claims")


class DocumentSourceModel(Base):
    __tablename__ = "document_sources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    authors = Column(JSON, nullable=True)  # List[str]
    publisher = Column(String(255), nullable=True)
    published_date = Column(String(100), nullable=True)
    snippet = Column(Text, nullable=True)
    source_type = Column(String(50), nullable=False)

    job = relationship("ResearchJobModel", back_populates="document_sources")


# ---------------------------------------------------------------------------
# Phase 11 — Saved library (normalized, user-scoped)
#
# These tables are the canonical store for the frontend's saved library. They
# are deliberately separate from the Phase 0-7 enterprise blueprint tables
# above (users / research_jobs / verified_claims / document_sources), which
# keep their own shape and tests. Everything here is scoped by `user_id` — the
# Supabase auth user id (a UUID kept as a string so the same models work on
# SQLite locally and Postgres in production).
#
# `user_id` is stored, not a ForeignKey to a local users table: with Supabase,
# identities live in Supabase's own `auth.users`, and the backend trusts the
# verified JWT's `sub`. Row scoping is enforced in the repository (and, for
# defense-in-depth on Postgres, by the RLS policies in supabase/schema.sql).
# ---------------------------------------------------------------------------


def new_uuid() -> str:
    return str(uuid.uuid4())


class FolderModel(Base):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_folder_user_name"),
    )

    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class TagModel(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tag_user_name"),
    )

    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


# Many-to-many between sessions and tags.
class SessionTagModel(Base):
    __tablename__ = "session_tags"
    __table_args__ = (
        UniqueConstraint("session_id", "tag_id", name="uq_session_tag"),
    )

    id = Column(String(36), primary_key=True, default=new_uuid)
    session_id = Column(
        String(36), ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id = Column(String(36), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True)


class ResearchSessionModel(Base):
    """One saved research run — the row a library entry points at."""

    __tablename__ = "research_sessions"
    __table_args__ = (
        Index("ix_session_user_created", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(String(36), nullable=False, index=True)

    query = Column(Text, nullable=False)
    title = Column(Text, nullable=False)

    # Job lifecycle (Phase 12 concurrency/status): pending → running →
    # complete | error. Saved-from-a-finished-result rows start "complete".
    status = Column(String(20), default="complete", nullable=False, index=True)
    error_text = Column(Text, nullable=True)

    # Run parameters + summary metadata, enough to reconstruct the result.
    citation_style = Column(String(10), default="apa", nullable=False)
    target_language = Column(String(60), default="English", nullable=False)
    num_sub_questions = Column(Integer, default=0, nullable=False)
    max_results_per_subquestion = Column(Integer, default=5, nullable=False)
    revision_count = Column(Integer, default=0, nullable=False)
    review_decision = Column(String(20), default="", nullable=False)
    review_feedback = Column(Text, default="", nullable=False)

    # The plan's sub-questions and the run's error list, stored verbatim so the
    # reopened result matches a fresh run byte-for-byte.
    plan_json = Column(JSON, nullable=True)      # list[{question, web_query, academic_query}]
    errors_json = Column(JSON, nullable=True)    # list[str]

    # Library organization.
    folder_id = Column(
        String(36), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    starred = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    report = relationship(
        "ReportModel", back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    sources = relationship(
        "SourceModel", back_populates="session", cascade="all, delete-orphan",
        order_by="SourceModel.ordinal",
    )
    claims = relationship(
        "ClaimModel", back_populates="session", cascade="all, delete-orphan",
        order_by="ClaimModel.ordinal",
    )
    charts = relationship(
        "ChartModel", back_populates="session", cascade="all, delete-orphan",
        order_by="ChartModel.ordinal",
    )
    follow_ups = relationship(
        "FollowUpModel", back_populates="session", cascade="all, delete-orphan",
        order_by="FollowUpModel.ordinal",
    )


class ReportModel(Base):
    """The written output for a session (1:1). Kept in its own table because
    the report text is large and rarely needed in list views."""

    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=new_uuid)
    session_id = Column(
        String(36), ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    final_report = Column(Text, default="", nullable=False)  # markdown, with [n] citations + references
    draft = Column(Text, default="", nullable=False)
    pdf_url = Column(Text, nullable=True)   # signed Supabase Storage URL, when Storage is enabled
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    session = relationship("ResearchSessionModel", back_populates="report")


class SourceModel(Base):
    """A retrieved+ranked document (mirrors app.schemas.Document)."""

    __tablename__ = "sources"

    id = Column(String(36), primary_key=True, default=new_uuid)
    session_id = Column(
        String(36), ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ordinal = Column(Integer, default=0, nullable=False)  # preserves final_documents order

    title = Column(Text, nullable=False)
    url = Column(Text, default="", nullable=False)
    authors = Column(JSON, nullable=True)          # list[str]
    abstract = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    source = Column(String(30), nullable=False)    # SourceType value: web/arxiv/openalex/...
    kind = Column(String(10), default="web", nullable=False)  # "web" | "paper" (for the tabbed panel)
    published_date = Column(String(60), nullable=True)
    citation_count = Column(Integer, nullable=True)
    relevance_score = Column(Float, nullable=True)
    raw_id = Column(String(120), nullable=True)
    sub_question = Column(Text, nullable=True)

    session = relationship("ResearchSessionModel", back_populates="sources")


class ClaimModel(Base):
    """A verified claim (mirrors app.schemas.VerifiedClaim). The supporting /
    contradicting evidence is stored as JSON of full Document dicts so the
    frontend's citation index (which numbers sources by walking claims in
    order) reproduces exactly on reopen."""

    __tablename__ = "claims"

    id = Column(String(36), primary_key=True, default=new_uuid)
    session_id = Column(
        String(36), ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ordinal = Column(Integer, default=0, nullable=False)

    text = Column(Text, nullable=False)
    sub_question = Column(Text, default="", nullable=False)
    verdict = Column(String(20), nullable=False)   # ClaimVerdict value
    confidence = Column(Float, default=0.0, nullable=False)
    note = Column(Text, nullable=True)
    supporting_sources = Column(JSON, nullable=True)     # list[Document dict]
    contradicting_sources = Column(JSON, nullable=True)  # list[Document dict]

    session = relationship("ResearchSessionModel", back_populates="claims")


class ChartModel(Base):
    """A chartable comparison (mirrors app.schemas.ChartSpec)."""

    __tablename__ = "charts"

    id = Column(String(36), primary_key=True, default=new_uuid)
    session_id = Column(
        String(36), ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ordinal = Column(Integer, default=0, nullable=False)

    title = Column(Text, nullable=False)
    chart_type = Column(String(10), default="bar", nullable=False)
    x_label = Column(String(200), default="", nullable=False)
    y_label = Column(String(200), default="", nullable=False)
    labels = Column(JSON, nullable=True)   # list[str]
    values = Column(JSON, nullable=True)   # list[float]
    png_url = Column(Text, nullable=True)  # signed Supabase Storage URL, when Storage is enabled

    session = relationship("ResearchSessionModel", back_populates="charts")


class FollowUpModel(Base):
    """A suggested follow-up question seeded from the plan's sub-questions."""

    __tablename__ = "follow_ups"

    id = Column(String(36), primary_key=True, default=new_uuid)
    session_id = Column(
        String(36), ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ordinal = Column(Integer, default=0, nullable=False)
    question = Column(Text, nullable=False)

    session = relationship("ResearchSessionModel", back_populates="follow_ups")


# ---------------------------------------------------------------------------
# Phase 12 — request quotas (daily rate limiting)
#
# One row per (subject, UTC day). `subject_key` is "user:<uuid>" for a signed-in
# caller or "ip:<addr>" for an anonymous one; `day` is an ISO date string in
# UTC. The daily reset is implicit and needs no cron: a new day simply has no
# row yet, so the count starts from zero. The (subject_key, day) unique
# constraint both prevents duplicates and lets two concurrent first-hits race
# safely — the loser catches the IntegrityError and increments the winner's row
# (see app/rate_limit.py). Kept intentionally separate from the saved-library
# tables: it's operational metering, not user content.
# ---------------------------------------------------------------------------


class UsageCounterModel(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("subject_key", "day", name="uq_usage_subject_day"),
        Index("ix_usage_subject_day", "subject_key", "day"),
    )

    id = Column(String(36), primary_key=True, default=new_uuid)
    subject_key = Column(String(80), nullable=False)  # "user:<uuid>" | "ip:<addr>"
    day = Column(String(10), nullable=False)          # "YYYY-MM-DD" (UTC)
    count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
