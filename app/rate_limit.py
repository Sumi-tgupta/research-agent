"""
Request quotas — daily, DB-backed rate limiting (Phase 12).

Off by default (``settings.rate_limit_enabled``), so local dev and the test
suite are unaffected. Turn it on for a shared/public deployment to cap how
many full research runs a single caller can start per day.

Design
------
- **Keyed by identity, then IP.** A signed-in caller is limited by user id
  (``user:<uuid>``) with ``rate_limit_per_day``; an anonymous caller is limited
  by client IP (``ip:<addr>``) with ``rate_limit_anon_per_day``.
- **Daily reset is implicit (UTC).** The counter row is keyed by
  ``(subject_key, day)`` where ``day`` is the UTC date. A new day has no row, so
  the count starts fresh — no scheduled job to reset anything.
- **Count before you spend.** The check reads the current count and only
  increments when the request is *allowed*. A rejected request does not consume
  quota, so a client hammering a 429 can't push its own reset further away.
- **Fail open.** Rate limiting is a guardrail, not the product. If the counter
  store itself errors (e.g. the DB is briefly unavailable), the request is
  allowed rather than 500'd — the only hard failure surfaced to the caller is
  the intended 429 when they're genuinely over the limit.

Only the pipeline endpoints that actually spend LLM/search quota are metered
(``/research``, ``/research/stream``, ``/research/pdf`` in app/main.py); the
lightweight single-agent test endpoints and PDF re-rendering are not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthUser, get_optional_user
from app.config import get_settings
from app.db.models import UsageCounterModel
from app.db.session import SessionLocal


@dataclass
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_epoch: int  # UTC seconds at the next daily reset (next UTC midnight)


def _utc_day(now: datetime) -> str:
    return now.astimezone(timezone.utc).date().isoformat()


def _next_utc_midnight_epoch(now: datetime) -> int:
    """Seconds since the epoch at the next UTC midnight — when the daily
    window rolls over and the caller's count effectively resets to zero."""
    now_utc = now.astimezone(timezone.utc)
    tomorrow = now_utc.date().toordinal() + 1
    reset = datetime.fromordinal(tomorrow).replace(tzinfo=timezone.utc)
    return int(reset.timestamp())


def client_ip(request: Request) -> str:
    """Best-effort caller IP. Behind a proxy/CDN (Render, HF Spaces, Fly) the
    real client is the first hop in ``X-Forwarded-For``; fall back to the direct
    peer, then to a constant so a missing IP still shares one bucket rather than
    silently bypassing the limit."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def check_and_consume(
    db: Session, subject_key: str, limit: int, *, now: datetime | None = None
) -> RateLimitDecision:
    """Core quota logic, deliberately free of any FastAPI/HTTP concerns so it
    can be unit-tested against a plain session.

    Reads today's count for ``subject_key`` and, only if it's under ``limit``,
    increments it and reports the request allowed. A non-positive ``limit`` is
    treated as "unlimited" (guards against a misconfiguration locking everyone
    out). Returns a decision carrying the numbers needed for the standard
    ``X-RateLimit-*`` response headers.
    """
    now = now or datetime.now(timezone.utc)
    reset_epoch = _next_utc_midnight_epoch(now)

    if limit <= 0:  # unlimited / disabled sentinel
        return RateLimitDecision(allowed=True, limit=limit, remaining=limit, reset_epoch=reset_epoch)

    day = _utc_day(now)
    row = (
        db.query(UsageCounterModel)
        .filter(UsageCounterModel.subject_key == subject_key, UsageCounterModel.day == day)
        .one_or_none()
    )
    current = row.count if row else 0

    if current >= limit:
        return RateLimitDecision(allowed=False, limit=limit, remaining=0, reset_epoch=reset_epoch)

    if row is None:
        db.add(UsageCounterModel(subject_key=subject_key, day=day, count=1))
        try:
            db.commit()
        except IntegrityError:
            # A concurrent first-hit for the same (subject, day) won the unique
            # constraint race. Re-read its row and increment that instead.
            db.rollback()
            row = (
                db.query(UsageCounterModel)
                .filter(UsageCounterModel.subject_key == subject_key, UsageCounterModel.day == day)
                .one()
            )
            current = row.count
            if current >= limit:
                return RateLimitDecision(allowed=False, limit=limit, remaining=0, reset_epoch=reset_epoch)
            row.count = current + 1
            db.commit()
    else:
        row.count = current + 1
        db.commit()

    return RateLimitDecision(
        allowed=True, limit=limit, remaining=max(0, limit - (current + 1)), reset_epoch=reset_epoch
    )


def _subject_and_limit(request: Request, user: AuthUser | None) -> tuple[str, int]:
    settings = get_settings()
    if user is not None:
        return f"user:{user.id}", settings.rate_limit_per_day
    return f"ip:{client_ip(request)}", settings.rate_limit_anon_per_day


def _apply_headers(response: Response, decision: RateLimitDecision) -> None:
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Reset"] = str(decision.reset_epoch)


def enforce_rate_limit(
    request: Request,
    response: Response,
    user: AuthUser | None = Depends(get_optional_user),
) -> None:
    """FastAPI dependency for the metered pipeline endpoints.

    No-op unless ``rate_limit_enabled``. Shares the already-resolved
    ``get_optional_user`` result (FastAPI caches it within the request), so the
    JWT is decoded once even though both the endpoint and this guard want it.

    On success it annotates the response with ``X-RateLimit-*`` headers (they
    land on JSON responses; streaming/file responses return their own Response
    object, so those headers are best-effort there). Over the limit, it raises
    429 with ``Retry-After`` and the same headers. Any *unexpected* failure in
    the counter store is swallowed and the request allowed — see module docs.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    subject_key, limit = _subject_and_limit(request, user)

    try:
        db = SessionLocal()
        try:
            decision = check_and_consume(db, subject_key, limit)
        finally:
            db.close()
    except Exception:
        # Fail open: a limiter/store hiccup must not take down a request the
        # user is entitled to make.
        return

    _apply_headers(response, decision)
    if not decision.allowed:
        retry_after = max(1, decision.reset_epoch - int(datetime.now(timezone.utc).timestamp()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Daily request limit reached. This is a free, shared deployment — "
                "your quota resets at 00:00 UTC. Add your own free API keys and run "
                "it locally for unlimited use."
            ),
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(decision.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(decision.reset_epoch),
            },
        )


# Convenience alias for endpoint signatures.
RateLimit = Depends(enforce_rate_limit)
