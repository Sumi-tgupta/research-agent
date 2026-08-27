"""
Tests for the Phase-12 DB-backed job-status transitions in
app/library_repository.py:

  - the new ``status`` / ``error_text`` params on ``save_result_for_user`` (a
    finished run lands on a terminal state, "complete" or "error"),
  - ``set_session_status`` (user-scoped transitions; terminal states stamp
    ``completed_at``, non-terminal ones clear it), and
  - ``get_session_status`` (the lightweight poll view).

Uses an in-memory SQLite behind a StaticPool so the schema/rows persist across
whatever sessions the helpers touch — the same pattern as test_rate_limit.py.
All helpers here share the one session the fixture yields.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import library_repository as repo
from app.db.models import Base

USER = "user-1"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Local()
    try:
        yield session
    finally:
        session.close()


def _save(db, user_id: str = USER, **kwargs):
    result = {"query": "q", "final_report": "# Title\n\nbody", "plan": {"sub_questions": []}}
    return repo.save_result_for_user(db, user_id, result, **kwargs)


# --------------------------------------------------------------------------- #
# save_result_for_user — terminal status on a finished run
# --------------------------------------------------------------------------- #

def test_save_defaults_to_complete(db):
    s = _save(db)
    assert s.status == "complete"
    assert s.error_text is None
    assert s.completed_at is not None


def test_save_can_record_an_error_run(db):
    s = _save(db, status="error", error_text="Pipeline failed unexpectedly: boom")
    assert s.status == "error"
    assert s.error_text == "Pipeline failed unexpectedly: boom"
    # An errored run still finished, so it's stamped complete-time.
    assert s.completed_at is not None


def test_save_coerces_unknown_status_to_complete(db):
    # A bogus status must never persist — it defensively falls back to complete.
    assert _save(db, status="banana").status == "complete"


# --------------------------------------------------------------------------- #
# set_session_status — transitions + ownership
# --------------------------------------------------------------------------- #

def test_transition_clears_and_restamps_completed_at(db):
    s = _save(db)  # complete, completed_at set

    # A different user cannot transition someone else's run.
    assert repo.set_session_status(db, "intruder", s.id, "running") is False

    # complete -> running clears completed_at.
    assert repo.set_session_status(db, USER, s.id, "running") is True
    st = repo.get_session_status(db, USER, s.id)
    assert st["status"] == "running" and st["completed_at"] is None

    # running -> complete stamps it again and leaves no error.
    assert repo.set_session_status(db, USER, s.id, "complete") is True
    st = repo.get_session_status(db, USER, s.id)
    assert st["status"] == "complete"
    assert st["completed_at"] is not None
    assert st["error_text"] is None


def test_error_status_carries_text_then_clears_on_reopen(db):
    s = _save(db)

    assert repo.set_session_status(db, USER, s.id, "error", error_text="nope") is True
    assert repo.get_session_status(db, USER, s.id)["error_text"] == "nope"

    # Moving back to a non-terminal state clears both completed_at and error.
    assert repo.set_session_status(db, USER, s.id, "running") is True
    st = repo.get_session_status(db, USER, s.id)
    assert st["completed_at"] is None and st["error_text"] is None


def test_set_session_status_rejects_unknown_status(db):
    s = _save(db)
    with pytest.raises(ValueError):
        repo.set_session_status(db, USER, s.id, "bogus")


def test_set_session_status_false_for_missing_or_other_users(db):
    s = _save(db)
    assert repo.set_session_status(db, "intruder", s.id, "complete") is False
    assert repo.set_session_status(db, USER, "no-such-id", "complete") is False


# --------------------------------------------------------------------------- #
# get_session_status — shape + scoping
# --------------------------------------------------------------------------- #

def test_get_session_status_shape(db):
    s = _save(db)
    st = repo.get_session_status(db, USER, s.id)
    assert set(st) == {"id", "status", "error_text", "created_at", "updated_at", "completed_at"}
    assert st["id"] == s.id


def test_get_session_status_none_for_other_users(db):
    s = _save(db)
    assert repo.get_session_status(db, "intruder", s.id) is None
