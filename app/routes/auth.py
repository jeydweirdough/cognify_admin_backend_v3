"""
Auth routes — shared logic, two routers:
  /api/web/auth    → web_auth_router   (ADMIN + FACULTY only)
  /api/mobile/auth → mobile_auth_router (STUDENT only)
"""
import bcrypt
from fastapi import APIRouter, Request, Response, BackgroundTasks
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
from app.utils.email import queue_email

web_auth_router    = APIRouter(prefix="/api/web/auth",    tags=["web-auth"])
mobile_auth_router = APIRouter(prefix="/api/mobile/auth", tags=["mobile-auth"])


# ── Shared helper ──────────────────────────────────────────────────────────────

def _fetch_user_by_email(email: str):
    return fetchone(
        """
        SELECT u.id, u.email, u.password, u.status,
               u.first_name, u.middle_name, u.last_name, u.cvsu_id,
               u.photo_avatar,
               r.name AS role
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE LOWER(u.email) = %s
        """,
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
    
    role_row = fetchone("SELECT permissions FROM roles WHERE name = %s", [user["role"]])
    permissions = role_row.get("permissions") or [] if role_row else []
    
    payload = {
        "id":           str(user["id"]),
        "email":        user["email"],
        "first_name":   user["first_name"],
        "middle_name":  user.get("middle_name"),
        "last_name":    user["last_name"],
        "role":         user["role"],
        "cvsu_id":      user.get("cvsu_id"),
        "permissions":  permissions,
    }
    response = JSONResponse({"success": True, "message": "Login successful", "data": payload})
    set_auth_cookies(response, str(user["id"]), user["role"])
    log_action("User logged in", user["email"], str(user["id"]), user_id=str(user["id"]))
    return response


def _register(body: dict, expected_role: str, background_tasks: BackgroundTasks):
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

    hashed = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()

    if fetchone("SELECT id FROM users WHERE LOWER(email) = %s AND status != 'REMOVED'", [email]):
        return error("An account with this email is already registered. Please log in.", 409)

    role_row = fetchone("SELECT id FROM roles WHERE name = %s", [expected_role])
    if not role_row:
        return error("Role configuration error. Contact admin.", 500)

    wl_entry = fetchone(
        """SELECT * FROM whitelist
           WHERE LOWER(email) = %s
             AND LOWER(institutional_id) = LOWER(%s)""",
        [email, clean_str(body["cvsu_id"])],
    )

    if wl_entry:
        user = execute_returning(
            """INSERT INTO users
                   (cvsu_id, first_name, middle_name, last_name,
                    email, password, role_id, status, registration_type, added_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 'SELF_REGISTERED', %s)
               RETURNING id, first_name, last_name, email, status""",
            [
                clean_str(body["cvsu_id"]),
                clean_str(body["first_name"]),
                clean_str(body.get("middle_name")),
                clean_str(body["last_name"]),
                email,
                hashed,
                role_row["id"],
                str(wl_entry["added_by"]) if wl_entry.get("added_by") else None,
            ],
        )
        execute(
            """UPDATE whitelist
               SET first_name = %s, middle_name = %s, last_name = %s, status = 'REGISTERED'
               WHERE id = %s""",
            [clean_str(body["first_name"]), clean_str(body.get("middle_name")), clean_str(body["last_name"]), wl_entry["id"]],
        )
        execute("UPDATE users SET last_login = NOW() WHERE id = %s", [user["id"]])
        log_action(f"{expected_role} registered via whitelist", email, str(user["id"]))

        # Queued Email for Activated Registration
        html_body = f"""
        <div style="font-family: Arial, sans-serif; color: #333;">
            <h2>Registration Successful</h2>
            <p>Hello {body.get('first_name')},</p>
            <p>Your registration is complete! Because you were pre-authorized, your account is immediately <strong>ACTIVE</strong>.</p>
            <ul>
                <li><strong>Name:</strong> {body.get('first_name')} {body.get('last_name')}</li>
                <li><strong>Email:</strong> {email}</li>
                <li><strong>Role:</strong> {expected_role}</li>
                <li><strong>Institutional ID:</strong> {body.get('cvsu_id', 'N/A')}</li>
            </ul>
            <p>You can now log in using your registered email and password.</p>
        </div>
        """
        queue_email(background_tasks, email, "Registration Complete", html_body)

        access_token  = make_access_token(str(user["id"]), expected_role)
        refresh_token = make_refresh_token(str(user["id"]))
        perm_row = fetchone("SELECT permissions FROM roles WHERE name = %s", [expected_role])
        perms = (perm_row.get("permissions") or []) if perm_row else []

        return created(
            {
                "id":            str(user["id"]),
                "email":         user["email"],
                "first_name":    user["first_name"],
                "last_name":     user["last_name"],
                "cvsu_id":       clean_str(body["cvsu_id"]),
                "status":        "ACTIVE",
                "permissions":   perms,
                "photo_avatar":  None,
                "token":         access_token,
                "refresh_token": refresh_token,
            },
            "Account created successfully.",
        )
    else:
        user = execute_returning(
            """INSERT INTO users
                   (cvsu_id, first_name, middle_name, last_name,
                    email, password, role_id, status, registration_type)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', 'SELF_REGISTERED')
               RETURNING id, first_name, last_name, email, status""",
            [
                clean_str(body["cvsu_id"]),
                clean_str(body["first_name"]),
                clean_str(body.get("middle_name")),
                clean_str(body["last_name"]),
                email,
                hashed,
                role_row["id"],
            ],
        )
        log_action(f"{expected_role} self-registered (pending approval)", email, str(user["id"]))

        # Queued Email for Pending Registration
        html_body = f"""
        <div style="font-family: Arial, sans-serif; color: #333;">
            <h2>Registration Pending Approval</h2>
            <p>Hello {body.get('first_name')},</p>
            <p>Your registration request was received and is currently <strong>PENDING</strong> administrator approval.</p>
            <ul>
                <li><strong>Name:</strong> {body.get('first_name')} {body.get('last_name')}</li>
                <li><strong>Email:</strong> {email}</li>
                <li><strong>Role Requested:</strong> {expected_role}</li>
                <li><strong>Institutional ID:</strong> {body.get('cvsu_id', 'N/A')}</li>
            </ul>
            <p>You will receive another email once your account has been reviewed and activated.</p>
        </div>
        """
        queue_email(background_tasks, email, "Registration Pending Approval", html_body)

        return created(
            {"id": str(user["id"]), "email": user["email"], "status": "PENDING"},
            "Your account has been submitted for review. An administrator will approve it shortly.",
        )


# ═══════════════════════════════════════════════════════════════
# WEB AUTH  —  Admin + Faculty
# ═══════════════════════════════════════════════════════════════

@web_auth_router.post("/login")
async def web_login(request: Request):
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
async def web_register(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _register(body, "FACULTY", background_tasks)


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
        "photo_avatar": user.get("photo_avatar"),
    }
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
async def mobile_register(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _register(body, "STUDENT", background_tasks)


@mobile_auth_router.post("/logout")
async def mobile_logout(request: Request):
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
    return await _mobile_refresh_token(request)


@mobile_auth_router.get("/me")
async def mobile_me(request: Request):
    auth = mobile_permission_required("mobile_view_profile")(request)
    return _me_mobile(auth)


@web_auth_router.get("/signup-roles")
async def get_signup_roles(request: Request):
    rows = fetchall(
        "SELECT id, name FROM roles WHERE permissions @> '\"can_signup\"'::jsonb",
        []
    )
    return ok([{"id": str(r["id"]), "name": r["name"]} for r in rows])


@web_auth_router.post("/signup")
async def web_signup(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        body = {}

    import json as _json

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

    role_row = fetchone("SELECT id, name, permissions FROM roles WHERE name = %s", [role_name])
    if not role_row:
        return error("Invalid role selected.", 400)

    perms = role_row["permissions"]
    if isinstance(perms, str):
        perms = _json.loads(perms)
    if "can_signup" not in (perms or []):
        return error("Self-registration is not enabled for this role. Please contact your administrator.", 403)

    if fetchone("SELECT id FROM users WHERE LOWER(email) = %s AND status != 'REMOVED'", [email]):
        return error("An account with this email already exists. Please log in.", 409)

    wl_entry = fetchone(
        """SELECT * FROM whitelist
           WHERE LOWER(email) = %s
             AND LOWER(institutional_id) = LOWER(%s)
             AND role = %s
             AND status = 'PENDING'""",
        [email, clean_str(body["cvsu_id"]), role_name],
    )

    hashed = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()

    if wl_entry:
        user = execute_returning(
            """INSERT INTO users
                   (cvsu_id, first_name, middle_name, last_name,
                    email, password, role_id, status, department,
                    registration_type, added_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s,
                       'SELF_REGISTERED', %s)
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
                str(wl_entry["added_by"]) if wl_entry.get("added_by") else None,
            ],
        )
        execute("UPDATE whitelist SET status = 'REGISTERED' WHERE id = %s", [wl_entry["id"]])
        log_action("User registered via whitelist", email, str(user["id"]))

        # Queued Email for Activated Web Registration
        html_body = f"""
        <div style="font-family: Arial, sans-serif; color: #333;">
            <h2>Registration Successful</h2>
            <p>Hello {body.get('first_name')},</p>
            <p>Your registration is complete! Because you were pre-authorized, your account is immediately <strong>ACTIVE</strong>.</p>
            <ul>
                <li><strong>Name:</strong> {body.get('first_name')} {body.get('last_name')}</li>
                <li><strong>Email:</strong> {email}</li>
                <li><strong>Role:</strong> {role_name}</li>
                <li><strong>Institutional ID:</strong> {body.get('cvsu_id', 'N/A')}</li>
            </ul>
            <p>You can now log in using your registered email and password.</p>
        </div>
        """
        queue_email(background_tasks, email, "Registration Complete", html_body)

        return created(
            {"id": str(user["id"]), "email": email, "status": "ACTIVE"},
            "Account created successfully. You can now log in.",
        )
    else:
        user = execute_returning(
            """INSERT INTO users
                   (cvsu_id, first_name, middle_name, last_name,
                    email, password, role_id, status, department,
                    registration_type)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', %s,
                       'SELF_REGISTERED')
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
        log_action("User self-registered (pending approval)", email, str(user["id"]))

        # Queued Email for Pending Web Registration
        html_body = f"""
        <div style="font-family: Arial, sans-serif; color: #333;">
            <h2>Registration Pending Approval</h2>
            <p>Hello {body.get('first_name')},</p>
            <p>Your registration request was received and is currently <strong>PENDING</strong> administrator approval.</p>
            <ul>
                <li><strong>Name:</strong> {body.get('first_name')} {body.get('last_name')}</li>
                <li><strong>Email:</strong> {email}</li>
                <li><strong>Role Requested:</strong> {role_name}</li>
                <li><strong>Institutional ID:</strong> {body.get('cvsu_id', 'N/A')}</li>
            </ul>
            <p>You will receive another email once your account has been reviewed and activated.</p>
        </div>
        """
        queue_email(background_tasks, email, "Registration Pending Approval", html_body)

        return created(
            {"id": str(user["id"]), "email": email, "status": "PENDING"},
            "Your account has been submitted for review. An administrator will approve it shortly.",
        )


async def web_sync_permissions(request: Request):
    auth = login_required(request)
    return _me(auth)


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
    user = fetchone(
        """SELECT u.id, u.cvsu_id, u.first_name, u.middle_name, u.last_name,
                  u.email, u.department, u.status, u.date_created, u.last_login,
                  u.photo_avatar, r.id AS role_id, r.name AS role_name, r.permissions
           FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s""",
        [auth.user_id],
    )
    if not user:
        return unauthorized("User not found")
    user["id"] = str(user["id"])
    return ok(user)


async def _mobile_refresh_token(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

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
    user = fetchone(
        """SELECT u.id, u.cvsu_id, u.first_name, u.middle_name, u.last_name,
                  u.email, u.department, u.status, u.date_created, u.last_login,
                  u.photo_avatar, r.id AS role_id, r.name AS role_name, r.permissions
           FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s""",
        [auth.user_id],
    )
    if not user:
        return unauthorized("User not found")
    user["id"] = str(user["id"])
    if user.get("permissions") is None:
        user["permissions"] = []
    return ok(user)