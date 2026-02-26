"""
auth.py - JWT + cookie auth middleware.

Strategy:
  - Access token stored in HttpOnly cookie (most secure, prevents XSS).
  - Refresh token stored in HttpOnly cookie.
  - Non-sensitive preferences (theme, locale) may use localStorage on client.
  - Role info stored in a readable JS cookie so the frontend can gate UI.
"""
import os
import jwt
import functools
from datetime import datetime, timezone, timedelta
from flask import request, g
from app.utils.responses import unauthorized, forbidden
from app.db import fetchone

SECRET = os.getenv("JWT_SECRET", "dev-secret")
ACCESS_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRY_MINUTES", 60))
REFRESH_DAYS = int(os.getenv("JWT_REFRESH_EXPIRY_DAYS", 7))

COOKIE_ACCESS = "access_token"
COOKIE_REFRESH = "refresh_token"


# ── Token creation ────────────────────────────────────────────────────────────

def make_access_token(user_id: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MINUTES)
    return jwt.encode({"sub": user_id, "role": role, "exp": exp}, SECRET, algorithm="HS256")


def make_refresh_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS)
    return jwt.encode({"sub": user_id, "exp": exp}, SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def set_auth_cookies(response, user_id: str, role: str):
    """Attach both tokens to the response as HttpOnly cookies."""
    access = make_access_token(user_id, role)
    refresh = make_refresh_token(user_id)
    is_prod = os.getenv("FLASK_ENV") == "production"

    response.set_cookie(
        COOKIE_ACCESS, access,
        httponly=True, secure=is_prod, samesite="Lax",
        max_age=ACCESS_MINUTES * 60,
    )
    response.set_cookie(
        COOKIE_REFRESH, refresh,
        httponly=True, secure=is_prod, samesite="Lax",
        max_age=REFRESH_DAYS * 86400,
    )
    # Non-sensitive readable cookie so JS can display role in the UI
    response.set_cookie(
        "user_role", role,
        httponly=False, secure=is_prod, samesite="Lax",
        max_age=ACCESS_MINUTES * 60,
    )
    return response


def clear_auth_cookies(response):
    response.delete_cookie(COOKIE_ACCESS)
    response.delete_cookie(COOKIE_REFRESH)
    response.delete_cookie("user_role")
    return response


# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    """Inject g.user_id and g.role; reject if token missing/invalid."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        token = request.cookies.get(COOKIE_ACCESS)
        # Also support Bearer for API clients / Swagger
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            return unauthorized("Authentication required")
        payload = decode_token(token)
        if not payload:
            return unauthorized("Token expired or invalid")
        g.user_id = payload["sub"]
        g.role = payload["role"]
        return f(*args, **kwargs)
    return wrapper


def roles_required(*allowed_roles):
    """Must be used AFTER @login_required."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if g.role not in allowed_roles:
                return forbidden("Insufficient permissions")
            return f(*args, **kwargs)
        return wrapper
    return decorator


def owner_or_admin(user_id_param="user_id"):
    """Allow if the requester owns the resource OR is an ADMIN."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            target = kwargs.get(user_id_param)
            if g.role != "ADMIN" and g.user_id != str(target):
                return forbidden("You can only access your own data")
            return f(*args, **kwargs)
        return wrapper
    return decorator
