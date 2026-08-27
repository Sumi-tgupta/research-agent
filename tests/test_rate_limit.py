"""
Tests for the Phase-12 request quota / rate limiter (app/rate_limit.py).

Two layers:
  - ``check_and_consume`` is exercised directly against an in-memory session —
    it's deliberately free of FastAPI concerns, so the quota math (allow/block,
    remaining, per-subject isolation, implicit daily reset) is unit-testable
    without HTTP.
  - ``enforce_rate_limit`` is exercised through a throwaway FastAPI app with a
    trivial endpoint, so we verify the 429 + headers behavior without ever
    running the real (slow, network-bound) research pipeline. Its DB access is
    pointed at a shared in-memory SQLite via a StaticPool so counts persist
    across the separate sessions the dependency opens per request.
"""

from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.auth import AuthUser, get_optional_user
from app.config import Settings
from app.db.models import Base, UsageCounterModel
from app.rate_limit import (
    _next_utc_midnight_epoch,
    check_and_consume,
    client_ip,
    enforce_rate_limit,
)


# --------------------------------------------------------------------------- #
# In-memory DB helpers
# --------------------------------------------------------------------------- #

def _shared_memory_sessionmaker():
    """A sessionmaker over a single shared in-memory SQLite connection. The
    StaticPool is what makes the table survive across the multiple sessions the
    dependency opens (a plain ``:memory:`` gives each connection its own empty
    database)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Local = _shared_memory_sessionmaker()
    session = Local()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# check_and_consume — the core quota logic
# --------------------------------------------------------------------------- #

def test_allows_up_to_the_limit_then_blocks(db_session):
    key, limit = "ip:1.2.3.4", 3

    d1 = check_and_consume(db_session, key, limit)
    d2 = check_and_consume(db_session, key, limit)
    d3 = check_and_consume(db_session, key, limit)
    d4 = check_and_consume(db_session, key, limit)

    assert [d1.allowed, d2.allowed, d3.allowed, d4.allowed] == [True, True, True, False]
    # remaining counts down and never goes negative
    assert [d1.remaining, d2.remaining, d3.remaining, d4.remaining] == [2, 1, 0, 0]


def test_a_blocked_request_does_not_consume_quota(db_session):
    key, limit = "ip:5.5.5.5", 1
    check_and_consume(db_session, key, limit)  # uses the one slot

    # Hitting the wall repeatedly must not push the stored count past the limit,
    # otherwise the reset math and "remaining" would drift.
    check_and_consume(db_session, key, limit)
    check_and_consume(db_session, key, limit)

    row = (
        db_session.query(UsageCounterModel)
        .filter(UsageCounterModel.subject_key == key)
        .one()
    )
    assert row.count == 1


def test_separate_subjects_have_independent_buckets(db_session):
    limit = 1
    a = check_and_consume(db_session, "ip:1.1.1.1", limit)
    b = check_and_consume(db_session, "ip:2.2.2.2", limit)
    # user vs ip are different namespaces too
    c = check_and_consume(db_session, "user:abc", limit)

    assert a.allowed and b.allowed and c.allowed


def test_counter_resets_on_a_new_utc_day(db_session):
    key, limit = "ip:9.9.9.9", 2
    day1 = datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)
    day2 = datetime(2026, 1, 2, 0, 5, tzinfo=timezone.utc)

    assert check_and_consume(db_session, key, limit, now=day1).allowed
    assert check_and_consume(db_session, key, limit, now=day1).allowed
    assert not check_and_consume(db_session, key, limit, now=day1).allowed  # limit hit

    # New UTC day → fresh window, allowed again.
    fresh = check_and_consume(db_session, key, limit, now=day2)
    assert fresh.allowed
    assert fresh.remaining == 1


def test_non_positive_limit_means_unlimited_and_writes_no_rows(db_session):
    key = "ip:0.0.0.0"
    for _ in range(5):
        assert check_and_consume(db_session, key, 0).allowed

    assert db_session.query(UsageCounterModel).count() == 0


def test_reset_epoch_is_next_utc_midnight():
    now = datetime(2026, 3, 4, 15, 45, tzinfo=timezone.utc)
    expected = datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc)
    assert _next_utc_midnight_epoch(now) == int(expected.timestamp())


# --------------------------------------------------------------------------- #
# client_ip
# --------------------------------------------------------------------------- #

def _make_request(headers: dict | None = None, client=("203.0.113.9", 5000)) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client,
    }
    return Request(scope)


def test_client_ip_prefers_first_forwarded_hop():
    req = _make_request({"x-forwarded-for": "9.9.9.9, 8.8.8.8, 7.7.7.7"})
    assert client_ip(req) == "9.9.9.9"


def test_client_ip_falls_back_to_direct_peer_then_unknown():
    assert client_ip(_make_request()) == "203.0.113.9"
    assert client_ip(_make_request(client=None)) == "unknown"


# --------------------------------------------------------------------------- #
# enforce_rate_limit — the FastAPI dependency (via a throwaway app)
# --------------------------------------------------------------------------- #

def _mini_app() -> FastAPI:
    app = FastAPI()

    @app.get("/x", dependencies=[Depends(enforce_rate_limit)])
    def _endpoint():
        return {"ok": True}

    return app


def _settings(**overrides) -> Settings:
    base = dict(rate_limit_enabled=True, rate_limit_per_day=50, rate_limit_anon_per_day=2)
    base.update(overrides)
    return Settings.model_construct(**base)


def test_dependency_returns_429_after_anon_limit_with_headers(mocker):
    mocker.patch("app.rate_limit.get_settings", return_value=_settings(rate_limit_anon_per_day=2))
    mocker.patch("app.rate_limit.SessionLocal", _shared_memory_sessionmaker())

    client = TestClient(_mini_app())

    r1 = client.get("/x")
    r2 = client.get("/x")
    r3 = client.get("/x")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.headers["X-RateLimit-Limit"] == "2"
    assert r1.headers["X-RateLimit-Remaining"] == "1"
    assert r2.headers["X-RateLimit-Remaining"] == "0"

    assert r3.status_code == 429
    assert r3.headers["X-RateLimit-Remaining"] == "0"
    assert int(r3.headers["Retry-After"]) >= 1


def test_dependency_is_a_noop_when_disabled(mocker):
    mocker.patch("app.rate_limit.get_settings", return_value=_settings(rate_limit_enabled=False))
    # If it were enabled this would 429 on the 3rd call; disabled, it never does
    # and never even touches the DB.
    spy = mocker.patch("app.rate_limit.SessionLocal")
    client = TestClient(_mini_app())

    for _ in range(5):
        assert client.get("/x").status_code == 200
    spy.assert_not_called()


def test_dependency_fails_open_if_the_counter_store_errors(mocker):
    mocker.patch("app.rate_limit.get_settings", return_value=_settings())
    mocker.patch("app.rate_limit.SessionLocal", side_effect=RuntimeError("db down"))

    client = TestClient(_mini_app())
    # A limiter/DB hiccup must not turn an allowed request into an error.
    assert client.get("/x").status_code == 200


def test_signed_in_user_uses_the_higher_per_user_limit_and_own_bucket(mocker):
    mocker.patch(
        "app.rate_limit.get_settings",
        return_value=_settings(rate_limit_per_day=1, rate_limit_anon_per_day=1),
    )
    mocker.patch("app.rate_limit.SessionLocal", _shared_memory_sessionmaker())

    app = _mini_app()
    # Force a recognized user, so the limiter keys on user:<id>, not IP.
    app.dependency_overrides[get_optional_user] = lambda: AuthUser(id="user-123", email=None)
    client = TestClient(app)

    r1 = client.get("/x")
    r2 = client.get("/x")

    assert r1.status_code == 200
    assert r2.status_code == 429  # per-user limit of 1 reached

    # The consumed row is the user's bucket, not an IP bucket.
    assert r1.headers["X-RateLimit-Limit"] == "1"
