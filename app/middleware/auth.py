"""
JWT + cookie auth middleware.

Storage strategy:
  - access_token  → HttpOnly cookie (prevents XSS)
  - refresh_token → HttpOnly cookie
  - user_role     → readable JS cookie (frontend UI gating only)
  - Bearer header also accepted for API/mobile clients
"""
import os
import jwt
import functools
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from app.utils.responses import unauthorized, forbidden

SECRET         = os.getenv("JWT_SECRET", "dev-secret")
ACCESS_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRY_MINUTES", 60))
REFRESH_DAYS   = int(os.getenv("JWT_REFRESH_EXPIRY_DAYS", 7))
COOKIE_ACCESS  = "access_token"
COOKIE_REFRESH = "refresh_token"


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


def _is_prod() -> bool:
    return os.getenv("APP_ENV", os.getenv("FLASK_ENV", "")) == "production"


def set_auth_cookies(response: Response, user_id: str, role: str):
    prod = _is_prod()
    access  = make_access_token(user_id, role)
    refresh = make_refresh_token(user_id)
    response.set_cookie(COOKIE_ACCESS,  access,  httponly=True,  secure=prod, samesite="lax", max_age=ACCESS_MINUTES * 60)
    response.set_cookie(COOKIE_REFRESH, refresh, httponly=True,  secure=prod, samesite="lax", max_age=REFRESH_DAYS * 86400)
    response.set_cookie("user_role",    role,    httponly=False, secure=prod, samesite="lax", max_age=ACCESS_MINUTES * 60)
    return response


def clear_auth_cookies(response: Response):
    for name in (COOKIE_ACCESS, COOKIE_REFRESH, "user_role"):
        response.delete_cookie(name)
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
        # Resolve auth if not injected
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
