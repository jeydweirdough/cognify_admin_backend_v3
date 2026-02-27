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
from flask import request, g
from app.utils.responses import unauthorized, forbidden
from app.db import fetchone

SECRET          = os.getenv("JWT_SECRET", "dev-secret")
ACCESS_MINUTES  = int(os.getenv("JWT_ACCESS_EXPIRY_MINUTES", 60))
REFRESH_DAYS    = int(os.getenv("JWT_REFRESH_EXPIRY_DAYS", 7))
COOKIE_ACCESS   = "access_token"
COOKIE_REFRESH  = "refresh_token"

# ── Token helpers ─────────────────────────────────────────────────────────────

def make_access_token(user_id: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MINUTES)
    return jwt.encode({"sub": user_id, "role": role, "exp": exp}, SECRET, algorithm="HS256")


def make_refresh_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS)
    return jwt.encode({"sub": user_id, "exp": exp}, SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _is_prod() -> bool:
    return os.getenv("FLASK_ENV") == "production"


def set_auth_cookies(response, user_id: str, role: str):
    prod = _is_prod()
    access  = make_access_token(user_id, role)
    refresh = make_refresh_token(user_id)
    response.set_cookie(COOKIE_ACCESS,  access,  httponly=True,  secure=prod, samesite="Lax", max_age=ACCESS_MINUTES * 60)
    response.set_cookie(COOKIE_REFRESH, refresh, httponly=True,  secure=prod, samesite="Lax", max_age=REFRESH_DAYS * 86400)
    response.set_cookie("user_role",    role,    httponly=False,  secure=prod, samesite="Lax", max_age=ACCESS_MINUTES * 60)
    return response


def clear_auth_cookies(response):
    for name in (COOKIE_ACCESS, COOKIE_REFRESH, "user_role"):
        response.delete_cookie(name)
    return response


# ── Token extraction ──────────────────────────────────────────────────────────

def _extract_token() -> str | None:
    token = request.cookies.get(COOKIE_ACCESS)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return token or None


# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    """Injects g.user_id and g.role. Rejects missing/expired tokens."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        token = _extract_token()
        if not token:
            return unauthorized("Authentication required")
        payload = decode_token(token)
        if not payload:
            return unauthorized("Token expired or invalid")
        g.user_id = payload["sub"]
        g.role    = payload["role"]
        return f(*args, **kwargs)
    return wrapper


def roles_required(*allowed):
    """Must follow @login_required."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if g.role not in allowed:
                return forbidden("Insufficient permissions")
            return f(*args, **kwargs)
        return wrapper
    return decorator


def owner_or_admin(id_param="user_id"):
    """Allow if requester owns the resource OR is ADMIN."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            target = kwargs.get(id_param)
            if g.role != "ADMIN" and g.user_id != str(target):
                return forbidden("Access denied")
            return f(*args, **kwargs)
        return wrapper
    return decorator