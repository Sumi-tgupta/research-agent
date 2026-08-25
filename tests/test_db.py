"""Unit tests for Apex-Research database models and persistence layer."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, ResearchJobModel, VerifiedClaimModel, DocumentSourceModel


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_create_research_job_and_claims(in_memory_db):
    job = ResearchJobModel(query="What is caffeine half-life?", depth_level="deep", status="COMPLETED")
    in_memory_db.add(job)
    in_memory_db.commit()
    in_memory_db.refresh(job)

    assert job.id is not None
    assert job.status == "COMPLETED"

    claim = VerifiedClaimModel(
        job_id=job.id,
        sub_question="Half-life in healthy adults",
        claim_text="Caffeine half-life is 3 to 7 hours in healthy adults.",
        verdict="corroborated",
        confidence_score=0.92,
    )
    in_memory_db.add(claim)
    in_memory_db.commit()

    saved_claims = in_memory_db.query(VerifiedClaimModel).filter_by(job_id=job.id).all()
    assert len(saved_claims) == 1
    assert saved_claims[0].verdict == "corroborated"
