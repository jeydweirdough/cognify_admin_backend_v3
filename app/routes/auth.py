"""
Auth routes — shared logic, two routers:
  /api/web/auth    → web_auth_router   (ADMIN + FACULTY only)
  /api/mobile/auth → mobile_auth_router (STUDENT only)
"""
import os
import bcrypt
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from app.db import fetchone, execute, execute_returning
from app.middleware.auth import (
    login_required, set_auth_cookies, clear_auth_cookies,
    decode_token, make_access_token, ACCESS_MINUTES, COOKIE_ACCESS, COOKIE_REFRESH,
    AuthState,
)
from app.utils.responses import ok, error, unauthorized, created, not_found
from app.utils.validators import validate_email, validate_password, require_fields, clean_str
from app.utils.log import log_action

web_auth_router    = APIRouter(prefix="/api/web/auth",    tags=["web-auth"])
mobile_auth_router = APIRouter(prefix="/api/mobile/auth", tags=["mobile-auth"])


# ── Shared helper ──────────────────────────────────────────────────────────────

def _fetch_user_by_email(email: str):
    return fetchone(
        """SELECT u.id, u.email, u.password, u.status,
                  u.first_name, u.last_name, u.institutional_id,
                  r.name AS role
           FROM users u
           JOIN roles r ON u.role_id = r.id
           WHERE LOWER(u.email) = %s""",
        [email.strip().lower()],
    )


def _do_login(user, allowed_roles: list[str]):
    if user["role"] not in allowed_roles:
        wrong = "web application" if user["role"] == "STUDENT" else "mobile app"
        return None, error(
            f"This account must use the {wrong} to log in.",
            403,
            errors={"code": "WRONG_APP"},
        )
    if user["status"] == "DEACTIVATED":
        return None, unauthorized("Account is deactivated")
    if user["status"] == "PENDING":
        return None, unauthorized("Account is pending approval")

    if user["role"] != "ADMIN":
        settings = fetchone("SELECT maintenance_mode FROM system_settings LIMIT 1")
        if settings and settings.get("maintenance_mode"):
            return None, error("System is under maintenance. Please try again later.", 503)

    return user, None


def _build_login_response(user):
    execute("UPDATE users SET last_login = NOW() WHERE id = %s", [user["id"]])
    payload = {
        "id":           str(user["id"]),
        "email":        user["email"],
        "first_name":   user["first_name"],
        "last_name":    user["last_name"],
        "role":         user["role"],
        "institutional_id": user.get("institutional_id"),
    }
    response = JSONResponse({"success": True, "message": "Login successful", "data": payload})
    set_auth_cookies(response, str(user["id"]), user["role"])
    log_action("User logged in", user["email"], str(user["id"]), user_id=str(user["id"]))
    return response


def _register(body: dict, expected_role: str):
    required = ["institutional_id", "first_name", "last_name", "email", "password"]
    missing = require_fields(body, required)
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    email = body["email"].strip().lower()
    if not validate_email(email):
        return error("Invalid email address")

    pw_err = validate_password(body["password"])
    if pw_err:
        return error(pw_err)

    entry = fetchone(
        """SELECT id, role, status FROM whitelist
           WHERE LOWER(email) = %s AND LOWER(institutional_id) = LOWER(%s)""",
        [email, body["institutional_id"]],
    )
    if not entry:
        label = "student number" if expected_role == "STUDENT" else "faculty ID"
        return error(
            f"Not whitelisted. Ensure your email and {label} match your registration.",
            403,
        )
    if entry["status"] == "REGISTERED":
        return error("This account has already been registered.", 409)
    if entry["role"].upper() != expected_role:
        wrong = "the mobile app" if expected_role == "STUDENT" else "the web application"
        return error(f"This ID is registered as {entry['role']}. Please use {wrong}.", 403)

    if fetchone("SELECT id FROM users WHERE LOWER(email) = %s", [email]):
        return error("Email is already registered.", 409)

    role_row = fetchone("SELECT id FROM roles WHERE name = %s", [expected_role])
    if not role_row:
        return error("Role configuration error. Contact admin.", 500)

    hashed = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()
    user = execute_returning(
        """INSERT INTO users
               (institutional_id, first_name, middle_name, last_name,
                email, password, role_id, status, department)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', %s)
           RETURNING id, first_name, last_name, email, status""",
        [
            body["institutional_id"],
            clean_str(body["first_name"]),
            clean_str(body.get("middle_name")),
            clean_str(body["last_name"]),
            email,
            hashed,
            role_row["id"],
            clean_str(body.get("department")),
        ],
    )

    execute("UPDATE whitelist SET status = 'REGISTERED' WHERE id = %s", [entry["id"]])
    log_action(f"{expected_role} registered", email, str(user["id"]))

    return created(
        {"id": str(user["id"]), "email": user["email"]},
        "Registration submitted. Awaiting approval.",
    )


# ═══════════════════════════════════════════════════════════════
# WEB AUTH  —  Admin + Faculty
# ═══════════════════════════════════════════════════════════════

@web_auth_router.post("/login")
async def web_login(request: Request):
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not body.get("email") or not body.get("password"):
        return error("Email and password are required")

    user = _fetch_user_by_email(body["email"])
    if not user:
        return unauthorized("Invalid credentials")
    if not bcrypt.checkpw(body["password"].encode(), user["password"].encode()):
        return unauthorized("Invalid credentials")

    user, err = _do_login(user, ["ADMIN", "FACULTY"])
    if err:
        return err
    return _build_login_response(user)


@web_auth_router.post("/register")
async def web_register(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _register(body, "FACULTY")


@web_auth_router.post("/logout")
async def web_logout():
    response = JSONResponse({"success": True, "message": "Logged out"})
    clear_auth_cookies(response)
    return response


@web_auth_router.post("/refresh")
async def web_refresh(request: Request):
    return _refresh_token(request)


@web_auth_router.get("/me")
async def web_me(request: Request):
    auth = login_required(request)
    if auth.role not in ("ADMIN", "FACULTY"):
        return unauthorized("Use the mobile app to access your account")
    return _me(auth)


# ═══════════════════════════════════════════════════════════════
# MOBILE AUTH  —  Students
# ═══════════════════════════════════════════════════════════════

@mobile_auth_router.post("/login")
async def mobile_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not body.get("email") or not body.get("password"):
        return error("Email and password are required")

    user = _fetch_user_by_email(body["email"])
    if not user:
        return unauthorized("Invalid credentials")
    if not bcrypt.checkpw(body["password"].encode(), user["password"].encode()):
        return unauthorized("Invalid credentials")

    user, err = _do_login(user, ["STUDENT"])
    if err:
        return err
    return _build_login_response(user)


@mobile_auth_router.post("/register")
async def mobile_register(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _register(body, "STUDENT")


@mobile_auth_router.post("/logout")
async def mobile_logout():
    response = JSONResponse({"success": True, "message": "Logged out"})
    clear_auth_cookies(response)
    return response


@mobile_auth_router.post("/refresh")
async def mobile_refresh(request: Request):
    return _refresh_token(request)


@mobile_auth_router.get("/me")
async def mobile_me(request: Request):
    auth = login_required(request)
    if auth.role != "STUDENT":
        return unauthorized("Use the web application to access your account")
    return _me(auth)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _refresh_token(request: Request):
    token = request.cookies.get(COOKIE_REFRESH)
    if not token:
        return unauthorized("No refresh token")
    payload = decode_token(token)
    if not payload:
        return unauthorized("Refresh token expired or invalid")

    user = fetchone(
        "SELECT u.id, u.status, r.name AS role FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = %s",
        [payload["sub"]],
    )
    if not user or user["status"] == "DEACTIVATED":
        return unauthorized("User not found or deactivated")

    prod = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "")) == "production"
    access = make_access_token(str(user["id"]), user["role"])
    response = JSONResponse({"success": True, "message": "Token refreshed"})
    response.set_cookie(COOKIE_ACCESS, access, httponly=True, secure=prod,
                        samesite="lax", max_age=ACCESS_MINUTES * 60)
    return response


def _me(auth: AuthState):
    user = fetchone(
        """SELECT u.id, u.institutional_id, u.first_name, u.middle_name, u.last_name,
                  u.email, u.department, u.status, u.date_created, u.last_login,
                  r.id AS role_id, r.name AS role_name, r.permissions
           FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s""",
        [auth.user_id],
    )
    if not user:
        return unauthorized("User not found")
    user["id"] = str(user["id"])
    return ok(user)
