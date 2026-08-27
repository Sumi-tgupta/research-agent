"""
Optional Supabase Storage offload (Phase 11).

Rendered PDFs and chart PNGs can be pushed to a private Supabase Storage bucket
so the frontend can link them directly. This is a pure add-on: with Storage
disabled (the default), saved reports still reconstruct fully from the database
and PDFs re-render on demand via /reports/pdf — so nothing here is on the
critical path, and every function degrades to returning None instead of raising.

Talks to Storage over its REST API with `requests` (already a dependency) to
avoid pulling in the heavier `supabase` SDK. Enabled only when both SUPABASE_URL
and SUPABASE_SERVICE_KEY are set (see Settings.supabase_storage_enabled). The
service-role key is a secret and lives in the backend env only.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)


def storage_enabled() -> bool:
    return get_settings().supabase_storage_enabled


def _headers(content_type: Optional[str] = None, *, upsert: bool = False) -> dict:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    if upsert:
        headers["x-upsert"] = "true"
    return headers


def ensure_bucket() -> bool:
    """Best-effort: create the (private) bucket if it doesn't exist. Safe to
    call repeatedly. Returns True if the bucket exists or was created."""
    if not storage_enabled():
        return False
    settings = get_settings()
    base = settings.supabase_url.rstrip("/")
    bucket = settings.supabase_storage_bucket
    try:
        # Creating an existing bucket returns a 400/409 — treat that as success.
        resp = requests.post(
            f"{base}/storage/v1/bucket",
            headers=_headers("application/json"),
            json={"id": bucket, "name": bucket, "public": False},
            timeout=settings.request_timeout_seconds,
        )
        if resp.status_code in (200, 201):
            return True
        if resp.status_code in (400, 409):
            return True  # already exists
        logger.warning("Supabase bucket ensure failed (%s): %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:  # network/other — non-fatal
        logger.warning("Supabase bucket ensure error: %s", exc)
        return False


def upload_and_sign(path: str, data: bytes, content_type: str) -> Optional[str]:
    """Upload bytes to `bucket/path` (overwriting) and return a time-limited
    signed URL, or None if Storage is disabled or anything fails."""
    if not storage_enabled():
        return None

    settings = get_settings()
    base = settings.supabase_url.rstrip("/")
    bucket = settings.supabase_storage_bucket
    ttl = settings.supabase_signed_url_ttl_seconds
    path = path.lstrip("/")

    try:
        up = requests.post(
            f"{base}/storage/v1/object/{bucket}/{path}",
            headers=_headers(content_type, upsert=True),
            data=data,
            timeout=settings.request_timeout_seconds,
        )
        if up.status_code not in (200, 201):
            logger.warning("Supabase upload failed (%s): %s", up.status_code, up.text[:200])
            return None

        signed = requests.post(
            f"{base}/storage/v1/object/sign/{bucket}/{path}",
            headers=_headers("application/json"),
            json={"expiresIn": ttl},
            timeout=settings.request_timeout_seconds,
        )
        if signed.status_code != 200:
            logger.warning("Supabase sign failed (%s): %s", signed.status_code, signed.text[:200])
            return None

        rel = signed.json().get("signedURL") or signed.json().get("signedUrl")
        if not rel:
            return None
        # The API returns a path relative to /storage/v1.
        return f"{base}/storage/v1{rel}" if rel.startswith("/") else f"{base}/storage/v1/{rel}"
    except Exception as exc:
        logger.warning("Supabase storage error for %s: %s", path, exc)
        return None


def upload_report_pdf(session_id: str, pdf_bytes: bytes) -> Optional[str]:
    return upload_and_sign(f"{session_id}/report.pdf", pdf_bytes, "application/pdf")


def upload_chart_png(session_id: str, index: int, png_bytes: bytes) -> Optional[str]:
    return upload_and_sign(f"{session_id}/chart_{index}.png", png_bytes, "image/png")
