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
