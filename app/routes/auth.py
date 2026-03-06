"""
Auth routes — shared logic, two routers:
  /api/web/auth    → web_auth_router   (ADMIN + FACULTY only)
  /api/mobile/auth → mobile_auth_router (STUDENT only)
"""
import bcrypt
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from app.db import fetchone, fetchall, execute, execute_returning
from app.middleware.auth import (
    login_required, set_auth_cookies, clear_auth_cookies,
    decode_token, make_access_token, make_refresh_token,
    ACCESS_MINUTES, COOKIE_ACCESS, COOKIE_REFRESH,
    AuthState, _cookie_params, mobile_permission_required,
    is_mobile_request,
)
from app.utils.responses import accout_removed, ok, error, unauthorized, created, not_found
from app.utils.validators import validate_email, validate_password, require_fields, clean_str
from app.utils.log import log_action

web_auth_router    = APIRouter(prefix="/api/web/auth",    tags=["web-auth"])
mobile_auth_router = APIRouter(prefix="/api/mobile/auth", tags=["mobile-auth"])


# ── Shared helper ──────────────────────────────────────────────────────────────

def _fetch_user_by_email(email: str):
    return fetchone(
        """SELECT u.id, u.email, u.password, u.status,
                  u.first_name, u.last_name, u.cvsu_id,
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
    if user["status"] == "REMOVED":
        return None, accout_removed("Account is REMOVED")
    if user["status"] == "PENDING":
        # Distinguish between self-registered (awaiting admin approval) and
        # admin-added users who haven't completed their signup yet.
        reg_row = fetchone(
            "SELECT registration_type FROM users WHERE id = %s", [user["id"]]
        )
        reg_type = (reg_row or {}).get("registration_type", "SELF_REGISTERED")
        if reg_type == "MANUALLY_ADDED":
            return None, error(
                "Your account hasn't been set up yet. Please complete your registration "
                "by signing up with your email and student ID.",
                403,
                errors={"code": "ACCOUNT_NOT_SETUP"},
            )
        return None, error(
            "Your account is pending administrator approval. "
            "You will be able to log in once an admin activates your account.",
            403,
            errors={"code": "ACCOUNT_PENDING"},
        )

    # ── Permission-based login gate ──────────────────────────────────────────
    # Check that the role actually has the required login permission.
    # web_login  → required for /api/web/auth/login  (ADMIN + FACULTY)
    # mobile_login → required for /api/mobile/auth/login (STUDENT)
    required_perm = "mobile_login" if "STUDENT" in allowed_roles else "web_login"
    role_row = fetchone("SELECT permissions FROM roles WHERE name = %s", [user["role"]])
    if role_row:
        perms = role_row.get("permissions") or []
        if required_perm not in perms:
            wrong = "web application" if required_perm == "web_login" else "mobile app"
            return None, error(
                f"This account is not permitted to log in via the {wrong}.",
                403,
                errors={"code": "PERMISSION_DENIED"},
            )

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
        "cvsu_id": user.get("cvsu_id"),
    }
    response = JSONResponse({"success": True, "message": "Login successful", "data": payload})
    set_auth_cookies(response, str(user["id"]), user["role"])
    log_action("User logged in", user["email"], str(user["id"]), user_id=str(user["id"]))
    return response


def _register(body: dict, expected_role: str):
    """
    Registration algorithm:

    CASE 1 — Admin-pre-added user completing their account:
      - Admin previously added the user via the whitelist panel.
      - A row exists in `users` with registration_type='MANUALLY_ADDED',
        status='PENDING', and a placeholder password.
      - The user now signs up with their real password.
      - Result: password is set, status → ACTIVE. User can log in immediately.

    CASE 2 — Self-registration (new user, not pre-added):
      - No matching row in `users` for this email.
      - A new row is created with registration_type='SELF_REGISTERED', status='PENDING'.
      - Result: account is created but PENDING. Admin must approve before login.

    CASE 3 — Already fully registered:
      - A row exists with status='ACTIVE' (already completed registration).
      - Return 409 — account already exists.
    """
    required = ["cvsu_id", "first_name", "last_name", "email", "password"]
    missing = require_fields(body, required)
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    email = body["email"].strip().lower()
    if not validate_email(email):
        return error("Invalid email address")

    pw_err = validate_password(body["password"])
    if pw_err:
        return error(pw_err)

    # Hash the real password up front
    hashed = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()

    # Resolve role
    role_row = fetchone("SELECT id FROM roles WHERE name = %s", [expected_role])
    if not role_row:
        return error("Role configuration error. Contact admin.", 500)
    role_id = role_row["id"]

    # ── Look up any existing user row by email only ───────────────────────────
    # We search by email alone (not email+cvsu_id) because admin-added rows are
    # keyed by email — the cvsu_id they entered at signup is the source of truth.
    entry = fetchone(
        """SELECT u.id, u.status, u.registration_type, r.name AS role
           FROM users u
           JOIN roles r ON u.role_id = r.id
           WHERE LOWER(u.email) = %s""",
        [email],
    )

    # ── CASE 3: Already a fully active/registered account ────────────────────
    if entry and entry["status"] == "ACTIVE":
        return error("An account with this email is already registered. Please log in.", 409)

    # Guard: if a row exists for a different role, block cross-role signup
    if entry and entry["role"] != expected_role:
        wrong = "the mobile app" if expected_role == "STUDENT" else "the web application"
        return error(
            f"This email is registered as {entry['role']}. Please use {wrong}.",
            403,
        )

    # ── CASE 1: Admin pre-added user completing their account ─────────────────
    if entry and entry["registration_type"] == "MANUALLY_ADDED" and entry["status"] == "PENDING":
        # Overwrite the placeholder password, fill in the real personal details,
        # and immediately activate the account — no admin approval needed.
        user = execute_returning(
            """UPDATE users
               SET cvsu_id      = %s,
                   first_name   = %s,
                   middle_name  = %s,
                   last_name    = %s,
                   password     = %s,
                   department   = %s,
                   status       = 'ACTIVE'
               WHERE id = %s
               RETURNING id, first_name, last_name, email, status""",
            [
                clean_str(body["cvsu_id"]),
                clean_str(body["first_name"]),
                clean_str(body.get("middle_name")),
                clean_str(body["last_name"]),
                hashed,
                clean_str(body.get("department")),
                entry["id"],
            ],
        )
        log_action(f"{expected_role} completed admin-added registration", email, str(user["id"]))
        return created(
            {"id": str(user["id"]), "email": user["email"], "status": "ACTIVE"},
            "Account setup complete. You can now log in.",
        )

    # ── CASE 2: Self-registration — brand new user ────────────────────────────
    # Check for duplicate cvsu_id to prevent ID collision
    if fetchone("SELECT id FROM users WHERE LOWER(cvsu_id) = LOWER(%s)", [body["cvsu_id"]]):
        return error("This student ID is already associated with another account.", 409)

    user = execute_returning(
        """INSERT INTO users
               (cvsu_id, first_name, middle_name, last_name,
                email, password, role_id, status, department, registration_type)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', %s, 'SELF_REGISTERED')
           RETURNING id, first_name, last_name, email, status""",
        [
            clean_str(body["cvsu_id"]),
            clean_str(body["first_name"]),
            clean_str(body.get("middle_name")),
            clean_str(body["last_name"]),
            email,
            hashed,
            role_id,
            clean_str(body.get("department")),
        ],
    )

    log_action(f"{expected_role} self-registered — awaiting admin approval", email, str(user["id"]))
    return created(
        {"id": str(user["id"]), "email": user["email"], "status": "PENDING"},
        "Registration submitted. Your account is pending administrator approval.",
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

    # Mobile login returns tokens in the response body ONLY — no cookies.
    # React Native cannot reliably use HttpOnly cookies across origins.
    # The app stores tokens in AsyncStorage and sends Authorization: Bearer <token>.
    execute("UPDATE users SET last_login = NOW() WHERE id = %s", [user["id"]])
    access_token  = make_access_token(str(user["id"]), user["role"])
    refresh_token = make_refresh_token(str(user["id"]))

    role_row = fetchone("SELECT permissions FROM roles WHERE name = %s", [user["role"]])
    perms = (role_row.get("permissions") or []) if role_row else []

    payload = {
        "id":          str(user["id"]),
        "email":       user["email"],
        "first_name":  user["first_name"],
        "last_name":   user["last_name"],
        "role":        user["role"],
        "cvsu_id":     user.get("cvsu_id"),
        "permissions": perms,
    }
    # No Set-Cookie headers — mobile stores tokens in AsyncStorage only.
    log_action("Mobile login", user["email"], str(user["id"]), user_id=str(user["id"]))
    return JSONResponse({
        "success": True,
        "message": "Login successful",
        "data": payload,
        "token": access_token,
        "refresh_token": refresh_token,
        "expires_in": ACCESS_MINUTES * 60,
    })


@mobile_auth_router.post("/register")
async def mobile_register(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _register(body, "STUDENT")


@mobile_auth_router.post("/logout")
async def mobile_logout(request: Request):
    """
    Mobile logout is stateless — the client discards tokens from AsyncStorage.
    No cookies to clear. Optionally logs the action if a valid token is present.
    """
    try:
        from app.middleware.auth import get_auth as _get_auth
        auth = _get_auth(request)
        if auth:
            log_action("Mobile logout", user_id=auth.user_id)
    except Exception:
        pass
    return JSONResponse({"success": True, "message": "Logged out"})


@mobile_auth_router.post("/refresh")
async def mobile_refresh(request: Request):
    """
    Mobile token refresh — refresh_token is supplied in the request body
    (NOT a cookie) and a new access_token is returned in the response body.
    """
    return await _mobile_refresh_token(request)


@mobile_auth_router.get("/me")
async def mobile_me(request: Request):
    auth = mobile_permission_required("mobile_view_profile")(request)
    return _me_mobile(auth)


@web_auth_router.get("/signup-roles")
async def get_signup_roles(request: Request):
    """
    Returns roles that have `can_signup` in their permissions.
    Used by the frontend Sign Up form to show which roles are eligible.
    """
    rows = fetchall(
        "SELECT id, name FROM roles WHERE permissions @> '\"can_signup\"'::jsonb AND is_system = FALSE OR name = 'FACULTY'",
        []
    )
    # Re-query cleanly
    rows = fetchall(
        "SELECT id, name FROM roles WHERE permissions @> '\"can_signup\"'::jsonb",
        []
    )
    return ok([{"id": str(r["id"]), "name": r["name"]} for r in rows])


@web_auth_router.post("/signup")
async def web_signup(request: Request):
    """
    Self-registration — anyone can sign up; account is created as PENDING.

    Algorithm:
      1. Validate required fields: first_name, last_name, email, cvsu_id, password, role.
      2. Role must exist and have `can_signup` in its permissions.
      3. Email must not already be registered.
      4. Create user in `users` table with status = 'PENDING' and no session cookie.
      5. Admin must set status = 'ACTIVE' before the user can log in.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    import json as _json

    # 1. Required fields
    required = ["first_name", "last_name", "email", "cvsu_id", "password", "role"]
    missing = require_fields(body, required)
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    email = body["email"].strip().lower()
    if not validate_email(email):
        return error("Invalid email address.")

    pw_err = validate_password(body["password"])
    if pw_err:
        return error(pw_err)

    role_name = body["role"].strip().upper()

    # 2. Role must exist and allow self-signup
    role_row = fetchone(
        "SELECT id, name, permissions FROM roles WHERE name = %s",
        [role_name],
    )
    if not role_row:
        return error("Invalid role selected.", 400)

    perms = role_row["permissions"]
    if isinstance(perms, str):
        perms = _json.loads(perms)
    if "can_signup" not in (perms or []):
        return error("Self-registration is not enabled for this role. Please contact your administrator.", 403)

    # 3. Duplicate check
    if fetchone("SELECT id FROM users WHERE LOWER(email) = %s", [email]):
        return error("An account with this email already exists. Please log in or contact your administrator.", 409)

    # 4. Create PENDING user — no password hash needed for login since status = PENDING blocks it
    hashed = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()

    user = execute_returning(
        """INSERT INTO users
               (cvsu_id, first_name, middle_name, last_name,
                email, password, role_id, status, department,
                registration_type, added_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', %s,
                   'SELF_REGISTERED', NULL)
           RETURNING id, first_name, last_name, email, status""",
        [
            clean_str(body["cvsu_id"]),
            clean_str(body["first_name"]),
            clean_str(body.get("middle_name")),
            clean_str(body["last_name"]),
            email,
            hashed,
            role_row["id"],
            clean_str(body.get("department")),
        ],
    )

    log_action("User self-registered — awaiting admin approval", email, str(user["id"]))

    # 5. Return 201 — no session cookie; user cannot log in until approved
    return created(
        {"id": str(user["id"]), "email": email, "status": "PENDING"},
        "Registration complete! Your account is pending administrator approval. You will be notified once access is granted.",
    )


async def web_sync_permissions(request: Request):
    """
    Re-fetches the authenticated user's current role + permissions from the DB.
    Called by the frontend after any role permission update so active sessions
    pick up the change immediately — no logout/login required.
    """
    auth = login_required(request)
    return _me(auth)


# ── Auth helpers — web (cookie-based) ─────────────────────────────────────────

def _refresh_token(request: Request):
    """
    Web token refresh: reads the refresh_token HttpOnly cookie and issues a new
    access_token cookie. Web-only — mobile uses _mobile_refresh_token instead.
    """
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
    if not user or user["status"] == "REMOVED":
        return unauthorized("User not found or REMOVED")

    access = make_access_token(str(user["id"]), user["role"])
    response = JSONResponse({"success": True, "message": "Token refreshed"})
    params = _cookie_params()
    response.set_cookie(
        COOKIE_ACCESS, access,
        httponly=True,
        max_age=ACCESS_MINUTES * 60,
        **params,
    )
    return response


def _me(auth: AuthState):
    """Web /me — returns user + permissions. Role cookie is managed by the browser."""
    user = fetchone(
        """SELECT u.id, u.cvsu_id, u.first_name, u.middle_name, u.last_name,
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


# ── Auth helpers — mobile (Bearer token / AsyncStorage) ───────────────────────

async def _mobile_refresh_token(request: Request):
    """
    Mobile token refresh: reads refresh_token from the JSON request body
    (mobile stores it in AsyncStorage, not a cookie) and returns a new
    access_token + refresh_token in the response body.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Mobile sends refresh_token in the body; fall back to cookie for dev convenience
    token = body.get("refresh_token") or request.cookies.get(COOKIE_REFRESH)
    if not token:
        return unauthorized("No refresh token provided")

    payload = decode_token(token)
    if not payload:
        return unauthorized("Refresh token expired or invalid")

    user = fetchone(
        "SELECT u.id, u.status, r.name AS role FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = %s",
        [payload["sub"]],
    )
    if not user or user["status"] == "REMOVED":
        return unauthorized("User not found or removed")

    # Rotate both tokens so each refresh invalidates the old pair
    new_access  = make_access_token(str(user["id"]), user["role"])
    new_refresh = make_refresh_token(str(user["id"]))

    return JSONResponse({
        "success": True,
        "message": "Token refreshed",
        "token": new_access,
        "refresh_token": new_refresh,
        "expires_in": ACCESS_MINUTES * 60,
    })


def _me_mobile(auth: AuthState):
    """
    Mobile /me — returns user + full permissions array.
    The mobile app caches this in AsyncStorage to avoid extra calls.
    """
    user = fetchone(
        """SELECT u.id, u.cvsu_id, u.first_name, u.middle_name, u.last_name,
                  u.email, u.department, u.status, u.date_created, u.last_login,
                  r.id AS role_id, r.name AS role_name, r.permissions
           FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s""",
        [auth.user_id],
    )
    if not user:
        return unauthorized("User not found")
    user["id"] = str(user["id"])
    # Ensure permissions is always a list for the mobile client
    if user.get("permissions") is None:
        user["permissions"] = []
    return ok(user)