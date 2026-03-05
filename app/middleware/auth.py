"""
JWT + cookie auth middleware.

Storage strategy:
  - access_token  → HttpOnly cookie (prevents XSS)
  - refresh_token → HttpOnly cookie
  - user_role     → readable JS cookie (frontend UI gating only)
  - Bearer header also accepted for API/mobile clients

Cookie SameSite strategy (auto-detected):
  - Development  → SameSite=Lax,  Secure=False  (localhost, same-origin)
  - Production   → SameSite=None, Secure=True   (cross-origin, different subdomains)

Set APP_ENV=production in your Vercel backend environment variables.
"""
import os
import jwt
import functools
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from app.utils.responses import unauthorized, forbidden

SECRET         = os.getenv("JWT_SECRET", "dev-secret")
ACCESS_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRY_MINUTES", 60))
REFRESH_DAYS   = int(os.getenv("JWT_REFRESH_EXPIRY_DAYS", 7))
COOKIE_ACCESS  = "access_token"
COOKIE_REFRESH = "refresh_token"


# ── Environment detection ─────────────────────────────────────────────────────

def _is_prod() -> bool:
    """
    Returns True when running in production (Vercel or any deployed env).
    Checks APP_ENV first, then falls back to FLASK_ENV.

    To enable production mode, set in your Vercel environment variables:
        APP_ENV=production
    """
    env = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "")).strip().lower()
    return env == "production"


def _cookie_params() -> dict:
    """
    Returns the correct cookie security parameters based on the environment.

    Development  → SameSite=Lax,  Secure=False
      Works for localhost where frontend and backend share the same origin.

    Production   → SameSite=None, Secure=True
      Required when frontend and backend are on different subdomains
      (e.g. frontend.vercel.app vs backend.vercel.app).
      Browsers will reject SameSite=None without Secure=True.
    """
    prod = _is_prod()
    return {
        "secure":   prod,
        "samesite": "none" if prod else "lax",
    }


# ── Token helpers ─────────────────────────────────────────────────────────────

def make_access_token(user_id: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MINUTES)
    return jwt.encode({"sub": user_id, "role": role, "exp": exp}, SECRET, algorithm="HS256")


def make_refresh_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS)
    return jwt.encode({"sub": user_id, "exp": exp}, SECRET, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ── Cookie management ─────────────────────────────────────────────────────────

def set_auth_cookies(response: Response, user_id: str, role: str):
    """
    Sets HttpOnly access + refresh cookies and a readable user_role cookie.
    Cookie attributes auto-adjust based on APP_ENV:
      - production  → Secure=True,  SameSite=None  (cross-origin safe)
      - development → Secure=False, SameSite=Lax   (localhost safe)
    """
    params = _cookie_params()
    access  = make_access_token(user_id, role)
    refresh = make_refresh_token(user_id)

    response.set_cookie(
        COOKIE_ACCESS, access,
        httponly=True,
        max_age=ACCESS_MINUTES * 60,
        **params,
    )
    response.set_cookie(
        COOKIE_REFRESH, refresh,
        httponly=True,
        max_age=REFRESH_DAYS * 86400,
        **params,
    )
    # user_role is intentionally NOT httponly so the frontend JS can read it
    response.set_cookie(
        "user_role", role,
        httponly=False,
        max_age=ACCESS_MINUTES * 60,
        **params,
    )
    return response


def clear_auth_cookies(response: Response):
    """Clears all auth cookies. Uses matching params so browsers accept the deletion."""
    params = _cookie_params()
    for name in (COOKIE_ACCESS, COOKIE_REFRESH, "user_role"):
        response.delete_cookie(name, **params)
    return response


# ── Token extraction ──────────────────────────────────────────────────────────

def _extract_token(request: Request) -> Optional[str]:
    token = request.cookies.get(COOKIE_ACCESS)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return token or None


# ── Auth state container ──────────────────────────────────────────────────────

class AuthState:
    """Holds the authenticated user's context for a single request."""
    def __init__(self, user_id: str, role: str, ip: str = None):
        self.user_id = user_id
        self.role    = role
        self.ip      = ip


# ── Dependency factories ──────────────────────────────────────────────────────

def get_auth(request: Request) -> Optional[AuthState]:
    """Extract and validate the JWT; returns AuthState or None."""
    token = _extract_token(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return AuthState(
        user_id=payload["sub"],
        role=payload["role"],
        ip=request.client.host if request.client else None,
    )


def login_required(request: Request) -> AuthState:
    """FastAPI dependency — injects AuthState or raises 401."""
    auth = get_auth(request)
    if not auth:
        raise _http_exc(unauthorized("Authentication required"))
    return auth


def roles_required(*allowed):
    """FastAPI dependency factory — checks role after login_required."""
    def dependency(auth: AuthState = None, request: Request = None) -> AuthState:
        if auth is None:
            auth = login_required(request)
        if auth.role not in allowed:
            raise _http_exc(forbidden("Insufficient permissions"))
        return auth
    return dependency


# ── Helper to raise HTTP exceptions from JSONResponse ────────────────────────

class _HTTPException(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


def _http_exc(response: JSONResponse) -> _HTTPException:
    return _HTTPException(response)


def permission_required(permission_id: str):
    """
    Route-level permission guard based on the DB roles.permissions JSON array.

    ADMIN role always bypasses all permission checks (system-level bypass).
    All other roles must have the specific permission_id in their role's
    permissions array (stored in the roles table).

    Usage:
        auth = permission_required("edit_subjects")(request)
        auth = permission_required("approve_verification")(request)
    """
    def check(request: Request) -> AuthState:
        from app.db import fetchone as _fetchone
        auth = login_required(request)

        # ADMIN role has a full system-level bypass — never blocked
        if auth.role == "ADMIN":
            return auth

        row = _fetchone(
            """SELECT r.permissions
               FROM users u
               JOIN roles r ON u.role_id = r.id
               WHERE u.id = %s""",
            [auth.user_id],
        )
        if not row:
            raise _http_exc(forbidden("Role not found for user"))

        perms = row.get("permissions") or []
        if permission_id not in perms:
            raise _http_exc(forbidden(f"Missing permission: {permission_id}"))

        return auth
    return check