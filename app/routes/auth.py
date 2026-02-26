"""Auth routes: login, logout, refresh, me."""
import bcrypt
from flask import Blueprint, request, jsonify, g
from app.db import fetchone, execute
from app.middleware.auth import (
    login_required, set_auth_cookies, clear_auth_cookies,
    decode_token, make_access_token, COOKIE_REFRESH
)
from app.utils.responses import ok, error, unauthorized, created

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return error("Email and password are required")

    user = fetchone(
        """SELECT u.id, u.email, u.password, u.status,
                  u.first_name, u.last_name, r.name AS role
           FROM users u
           JOIN roles r ON u.role_id = r.id
           WHERE LOWER(u.email) = %s""",
        [email]
    )

    if not user:
        return unauthorized("Invalid credentials")
    if user["status"] == "DEACTIVATED":
        return unauthorized("Account is deactivated")
    if user["status"] == "PENDING":
        return unauthorized("Account is pending approval")

    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return unauthorized("Invalid credentials")

    # Update last_login
    execute("UPDATE users SET last_login = NOW() WHERE id = %s", [user["id"]])

    payload = {
        "id": str(user["id"]),
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "role": user["role"],
    }
    resp = jsonify({"success": True, "message": "Login successful", "data": payload})
    return set_auth_cookies(resp, str(user["id"]), user["role"])


@bp.post("/logout")
def logout():
    resp = jsonify({"success": True, "message": "Logged out"})
    return clear_auth_cookies(resp)


@bp.post("/refresh")
def refresh():
    token = request.cookies.get(COOKIE_REFRESH)
    if not token:
        return unauthorized("No refresh token")
    payload = decode_token(token)
    if not payload:
        return unauthorized("Refresh token expired or invalid")

    user = fetchone(
        "SELECT u.id, r.name AS role FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = %s",
        [payload["sub"]]
    )
    if not user or user.get("status") == "DEACTIVATED":
        return unauthorized("User not found or deactivated")

    from app.middleware.auth import make_access_token, ACCESS_MINUTES, COOKIE_ACCESS
    import os
    from flask import make_response
    access = make_access_token(str(user["id"]), user["role"])
    resp = make_response(jsonify({"success": True, "message": "Token refreshed"}))
    is_prod = os.getenv("FLASK_ENV") == "production"
    resp.set_cookie(COOKIE_ACCESS, access, httponly=True, secure=is_prod,
                    samesite="Lax", max_age=ACCESS_MINUTES * 60)
    return resp


@bp.get("/me")
@login_required
def me():
    user = fetchone(
        """SELECT u.id, u.first_name, u.middle_name, u.last_name, u.email,
                  u.department, u.status, u.date_created, u.last_login, u.last_updated,
                  r.id AS role_id, r.name AS role_name, r.permissions
           FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s""",
        [g.user_id]
    )
    if not user:
        return unauthorized("User not found")
    user["id"] = str(user["id"])
    return ok(user)
