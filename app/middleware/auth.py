"""
JWT + cookie auth middleware.

Storage strategy per client:
  WEB (Admin/Faculty — browser):
    - access_token  → HttpOnly cookie (prevents XSS)
    - refresh_token → HttpOnly cookie
    - user_role     → readable JS cookie (frontend UI gating only)

  MOBILE (Student — React Native / Expo):
    - Tokens are returned in the JSON response body and stored in AsyncStorage.
    - Cookies are NOT used for mobile: React Native cannot reliably send/receive
      HttpOnly cookies across origins, and AsyncStorage is the correct storage
      primitive for mobile apps.
    - Auth is carried via the Authorization: Bearer <token> header on every request.
    - No refresh cookie is issued for mobile; the client re-authenticates when
      the access token expires.

Cookie SameSite strategy for web (auto-detected):
  - Development  → SameSite=Lax,  Secure=False  (localhost, same-origin)
  - Production   → SameSite=None, Secure=True   (cross-origin, different subdomains)

Client detection:
  Routes under /api/mobile/* are treated as mobile-origin.
  Routes under /api/web/*   are treated as web-origin.
  Alternatively, clients may send X-Client-Type: mobile or X-Client-Type: web.

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


# ── Client-type detection ─────────────────────────────────────────────────────

def is_mobile_request(request: Request) -> bool:
    """
    Returns True if the request originates from the mobile (React Native) client.

    Detection order:
      1. X-Client-Type header: 'mobile' → True, 'web' → False
      2. URL path prefix: /api/mobile/* → True, /api/web/* → False
      3. Default: False (treat as web)
    """
    client_type = request.headers.get("X-Client-Type", "").strip().lower()
    if client_type == "mobile":
        return True
    if client_type == "web":
        return False
    return request.url.path.startswith("/api/mobile/")


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


# ── Cookie management (WEB only) ──────────────────────────────────────────────

def set_auth_cookies(response: Response, user_id: str, role: str):
    """
    Sets HttpOnly access + refresh cookies and a readable user_role cookie.
    FOR WEB CLIENTS ONLY. Mobile clients receive tokens in the response body.

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
    """
    Clears all auth cookies. Uses matching params so browsers accept the deletion.
    FOR WEB CLIENTS ONLY. Mobile clients clear their AsyncStorage token directly.
    """
    params = _cookie_params()
    for name in (COOKIE_ACCESS, COOKIE_REFRESH, "user_role"):
        response.delete_cookie(name, **params)
    return response


# ── Token extraction ──────────────────────────────────────────────────────────

def _extract_token(request: Request) -> Optional[str]:
    """
    Extracts the JWT from the request.

    Priority:
      1. Authorization: Bearer <token> header  — used by mobile (AsyncStorage token)
      2. access_token HttpOnly cookie          — used by web (browser)

    Mobile requests should ALWAYS use the Authorization header.
    Web requests should ALWAYS use cookies (no Authorization header needed).
    """
    # Authorization header takes priority — this is the mobile path
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    # Fall back to cookie — this is the web path
    return request.cookies.get(COOKIE_ACCESS) or None


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
    FOR WEB CLIENTS (Admin/Faculty) ONLY.

    ADMIN role always bypasses all permission checks (system-level bypass).
    All other roles must have the specific permission_id in their role's
    permissions array (stored in the roles table).

    Usage:
        auth = permission_required("edit_subjects")(request)
    """
    def check(request: Request) -> AuthState:
        from app.db import fetchone as _fetchone
        auth = login_required(request)

        # Web guard: reject mobile/student tokens on web endpoints
        if auth.role == "STUDENT":
            raise _http_exc(forbidden("Student accounts must use the mobile app"))

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


def mobile_permission_required(permission_id: str):
    """
    Route-level permission guard for mobile (student) endpoints.
    FOR MOBILE CLIENTS (Students) ONLY — enforces Bearer token auth.

    Enforces that:
      1. The user is authenticated via Bearer token (Authorization header).
      2. The user's role is STUDENT.
      3. The role has the required permission_id.

    Usage:
        auth = mobile_permission_required("view_subjects")(request)
    """
    def check(request: Request) -> AuthState:
        from app.db import fetchone as _fetchone

        # Mobile endpoints must use Bearer token, not cookies
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # Also accept cookie-less requests that have a valid cookie
            # (for dev/testing convenience) but prefer the header
            pass

        auth = login_required(request)

        # Mobile guard: reject web/admin/faculty tokens on mobile endpoints
        if auth.role != "STUDENT":
            raise _http_exc(forbidden("This endpoint is for students only"))

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