"""
Auth routes — shared logic, two blueprints:
  /api/web/auth   → web_auth_bp   (ADMIN + FACULTY only)
  /api/mobile/auth → mobile_auth_bp (STUDENT only)

Both surfaces share the same DB but enforce role restrictions
so the wrong client type gets a clear WRONG_APP error.
"""
import os
import bcrypt
from flask import Blueprint, request, jsonify, make_response, g
from app.db import fetchone, execute, execute_returning
from app.middleware.auth import (
    login_required, set_auth_cookies, clear_auth_cookies,
    decode_token, make_access_token, ACCESS_MINUTES, COOKIE_ACCESS, COOKIE_REFRESH
)
from app.utils.responses import ok, error, unauthorized, created, not_found
from app.utils.validators import validate_email, validate_password, require_fields, clean_str
from app.utils.log import log_action

# ── Blueprint pair ────────────────────────────────────────────────────────────
web_auth_bp    = Blueprint("web_auth",    __name__, url_prefix="/api/web/auth")
mobile_auth_bp = Blueprint("mobile_auth", __name__, url_prefix="/api/mobile/auth")


# ── Shared helper ─────────────────────────────────────────────────────────────

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
    """
    Validates credentials and role, sets cookies, returns response.
    allowed_roles: which roles are permitted on this surface.
    """
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

    # Maintenance check: block non-admins when maintenance mode is on
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
    resp = make_response(jsonify({"success": True, "message": "Login successful", "data": payload}))
    set_auth_cookies(resp, str(user["id"]), user["role"])
    log_action("User logged in", user["email"], str(user["id"]))
    return resp


# ── Shared register logic ─────────────────────────────────────────────────────

def _register(body: dict, expected_role: str):
    """
    Shared registration logic for students and faculty.
    expected_role: 'STUDENT' or 'FACULTY'
    """
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

    # Check whitelist
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

    # Check email not already taken
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

    # Mark whitelist entry as registered
    execute("UPDATE whitelist SET status = 'REGISTERED' WHERE id = %s", [entry["id"]])
    log_action(f"{expected_role} registered", email, str(user["id"]))

    return created(
        {"id": str(user["id"]), "email": user["email"]},
        "Registration submitted. Awaiting approval.",
    )


# ═══════════════════════════════════════════════════════════════
# WEB AUTH  —  Admin + Faculty
# ═══════════════════════════════════════════════════════════════

@web_auth_bp.post("/login")
def web_login():
    body = request.get_json(silent=True) or {}
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


@web_auth_bp.post("/register")
def web_register():
    """Faculty self-registration (creates PENDING account)."""
    body = request.get_json(silent=True) or {}
    return _register(body, "FACULTY")


@web_auth_bp.post("/logout")
def web_logout():
    resp = make_response(jsonify({"success": True, "message": "Logged out"}))
    return clear_auth_cookies(resp)


@web_auth_bp.post("/refresh")
def web_refresh():
    return _refresh_token()


@web_auth_bp.get("/me")
@login_required
def web_me():
    if g.role not in ("ADMIN", "FACULTY"):
        return unauthorized("Use the mobile app to access your account")
    return _me()


# ═══════════════════════════════════════════════════════════════
# MOBILE AUTH  —  Students
# ═══════════════════════════════════════════════════════════════

@mobile_auth_bp.post("/login")
def mobile_login():
    body = request.get_json(silent=True) or {}
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


@mobile_auth_bp.post("/register")
def mobile_register():
    """Student self-registration (creates PENDING account)."""
    body = request.get_json(silent=True) or {}
    return _register(body, "STUDENT")


@mobile_auth_bp.post("/logout")
def mobile_logout():
    resp = make_response(jsonify({"success": True, "message": "Logged out"}))
    return clear_auth_cookies(resp)


@mobile_auth_bp.post("/refresh")
def mobile_refresh():
    return _refresh_token()


@mobile_auth_bp.get("/me")
@login_required
def mobile_me():
    if g.role != "STUDENT":
        return unauthorized("Use the web application to access your account")
    return _me()


# ── Shared helpers for refresh + me ──────────────────────────────────────────

def _refresh_token():
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

    prod = os.getenv("FLASK_ENV") == "production"
    access = make_access_token(str(user["id"]), user["role"])
    resp = make_response(jsonify({"success": True, "message": "Token refreshed"}))
    resp.set_cookie(COOKIE_ACCESS, access, httponly=True, secure=prod,
                    samesite="Lax", max_age=ACCESS_MINUTES * 60)
    return resp


def _me():
    user = fetchone(
        """SELECT u.id, u.institutional_id, u.first_name, u.middle_name, u.last_name,
                  u.email, u.department, u.status, u.date_created, u.last_login,
                  r.id AS role_id, r.name AS role_name, r.permissions
           FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s""",
        [g.user_id],
    )
    if not user:
        return unauthorized("User not found")
    user["id"] = str(user["id"])
    return ok(user)