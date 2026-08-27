"""
Optional Supabase auth.

The API is anonymous-first: research works with no account at all. When a
Supabase JWT secret is configured (SUPABASE_JWT_SECRET), we *recognize* a
signed-in user from the `Authorization: Bearer <token>` header, but we never
*require* one. Missing or invalid tokens simply resolve to `None` — the
request proceeds as anonymous.

This gives per-user features (e.g. server-side saves) a hook without ever
locking anonymous visitors out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app.config import get_settings

try:  # PyJWT is only needed when auth is configured.
    import jwt
except Exception:  # pragma: no cover - import guard
    jwt = None  # type: ignore[assignment]


@dataclass
class AuthUser:
    id: str
    email: Optional[str] = None


def _decode(token: str) -> Optional[AuthUser]:
    settings = get_settings()
    if not settings.supabase_auth_enabled or jwt is None:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": False},  # tolerate aud variations
        )
    except Exception:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None
    return AuthUser(id=user_id, email=payload.get("email"))


def get_optional_user(request: Request) -> Optional[AuthUser]:
    """FastAPI dependency: the signed-in user, or None for anonymous.

    Never raises — an absent, malformed, or unverifiable token all resolve to
    anonymous so the endpoint keeps working for everyone.
    """
    header = request.headers.get("authorization") or request.headers.get(
        "Authorization"
    )
    if not header or not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    return _decode(token)


def get_current_user(request: Request) -> AuthUser:
    """FastAPI dependency for endpoints that DO require a signed-in user (the
    saved library). Raises 401 when auth isn't configured or the token is
    absent/invalid — unlike get_optional_user, which never raises.

    The distinction keeps research anonymous-first (get_optional_user) while
    letting per-user features gate cleanly (get_current_user)."""
    settings = get_settings()
    if not settings.supabase_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign-in isn't configured on this server.",
        )
    user = get_optional_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use the saved library.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# Convenience alias for endpoint signatures.
OptionalUser = Depends(get_optional_user)
CurrentUser = Depends(get_current_user)
