"""
User management routes
  /api/web/admin/users   → full CRUD (ADMIN only)
  /api/web/faculty/users → read-only, filtered to students
"""
import bcrypt
from fastapi import APIRouter, Request, BackgroundTasks
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, permission_required, AuthState
from app.utils.responses import ok, created, no_content, error, not_found, conflict, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import validate_email, validate_password, require_fields, clean_str
from app.utils.log import log_action
from app.utils.email import queue_email

admin_users_router   = APIRouter(prefix="/api/web/admin/users",   tags=["admin-users"])
faculty_users_router = APIRouter(prefix="/api/web/faculty/users", tags=["faculty-users"])

VALID_ROLES    = {"ADMIN", "FACULTY", "STUDENT"}
VALID_STATUSES = {"PENDING", "ACTIVE", "REMOVED", "REMOVED"}


def _fmt(u: dict) -> dict:
    u["id"] = str(u["id"])
    u.pop("password", None)
    u["name"] = " ".join(filter(None, [u.get("first_name"), u.get("middle_name"), u.get("last_name")]))
    if u.get("role_id"):
        u["role_id"] = str(u["role_id"])
    if u.get("last_login"):
        u["last_login"] = u["last_login"].isoformat()
    if u.get("date_created"):
        u["date_created"] = u["date_created"].isoformat()
    if u.get("photo_avatar"):
        u["photo_avatar"] = str(u["photo_avatar"])
    return u


def _list_users(request: Request, role_lock: str = None):
    page, per_page = get_page_params(request)
    search = get_search(request)
    role   = role_lock or get_filter(request, "role", VALID_ROLES)
    status = get_filter(request, "status", VALID_STATUSES)

    sql = ["""
        SELECT u.*,
               r.name AS role, r.id AS role_id,
               ab.first_name || ' ' || ab.last_name AS added_by_name,
               apb.first_name || ' ' || apb.last_name AS approved_by_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        LEFT JOIN users ab  ON u.added_by   = ab.id
        LEFT JOIN users apb ON u.approved_by = apb.id
        WHERE 1=1
    """]
    params = []

    if search:
        sql.append("""AND (
            LOWER(u.first_name || ' ' || u.last_name) LIKE LOWER(%s)
            OR LOWER(u.email) LIKE LOWER(%s)
            OR LOWER(COALESCE(u.cvsu_id, '')) LIKE LOWER(%s)
        )""")
        params += [search, search, search]

    if role:
        sql.append("AND r.name = %s")
        params.append(role)

    if status:
        sql.append("AND u.status = %s")
        params.append(status)

    sql.append("ORDER BY u.date_created DESC")
    result = paginate(" ".join(sql), params, page, per_page)
    result["items"] = [_fmt(u) for u in result["items"]]
    return result


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_users_router.get("")
async def admin_list(request: Request):
    auth = permission_required("view_users")(request)
    return ok(_list_users(request))


@admin_users_router.get("/pending")
async def admin_pending(request: Request):
    auth = permission_required("view_users")(request)
    page, per_page = get_page_params(request)
    sql = """
        SELECT u.*, r.name AS role, r.id AS role_id
        FROM users u JOIN roles r ON u.role_id = r.id
        WHERE u.status = 'PENDING'
        ORDER BY u.date_created ASC
    """
    result = paginate(sql, [], page, per_page)
    result["items"] = [_fmt(u) for u in result["items"]]
    return ok(result)


@admin_users_router.get("/{user_id}")
async def admin_get(request: Request, user_id: str):
    auth = permission_required("view_users")(request)
    u = fetchone(
        """SELECT u.*, r.name AS role, r.id AS role_id,
                  ab.first_name || ' ' || ab.last_name AS added_by_name,
                  apb.first_name || ' ' || apb.last_name AS approved_by_name
           FROM users u
           JOIN roles r ON u.role_id = r.id
           LEFT JOIN users ab  ON u.added_by   = ab.id
           LEFT JOIN users apb ON u.approved_by = apb.id
           WHERE u.id = %s""",
        [user_id]
    )
    if not u: return not_found()
    return ok(_fmt(u))


@admin_users_router.post("")
async def admin_create(request: Request, background_tasks: BackgroundTasks):
    auth = permission_required("create_users")(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    required = ["first_name", "last_name", "email", "password", "role", "cvsu_id"]
    missing = require_fields(body, required)
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    email = body["email"].strip().lower()
    if not validate_email(email):
        return error("Invalid email")

    pw_err = validate_password(body["password"])
    if pw_err:
        return error(pw_err)

    if fetchone("SELECT id FROM users WHERE LOWER(email) = %s", [email]):
        return conflict("Email already registered")

    role_row = fetchone("SELECT id FROM roles WHERE name = %s", [body["role"].upper()])
    if not role_row:
        return error("Invalid role")

    hashed = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()
    user = execute_returning(
        """INSERT INTO users
               (cvsu_id, first_name, middle_name, last_name,
                email, password, role_id, status, department,
                registration_type, added_by, photo_avatar)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                   'MANUALLY_ADDED', %s, %s)
           RETURNING id, first_name, last_name, email, status, photo_avatar""",
        [
            clean_str(body["cvsu_id"]),
            clean_str(body["first_name"]),
            clean_str(body.get("middle_name")),
            clean_str(body["last_name"]),
            email, hashed, role_row["id"],
            (body.get("status") or "PENDING").upper(),
            clean_str(body.get("department")),
            auth.user_id,
            body.get("photo_avatar"),
        ],
    )
    log_action("Created user", email, str(user["id"]), user_id=auth.user_id, ip=auth.ip)

    # Queued Email for Manually Created User
    html_body = f"""
    <div style="font-family: Arial, sans-serif; color: #333;">
        <h2>Account Created Successfully</h2>
        <p>Hello {body.get('first_name')},</p>
        <p>An administrator has manually created an account for you on the platform.</p>
        <ul>
            <li><strong>Name:</strong> {body.get('first_name')} {body.get('last_name')}</li>
            <li><strong>Email:</strong> {email}</li>
            <li><strong>Assigned Role:</strong> {body.get('role')}</li>
            <li><strong>Institutional ID:</strong> {body.get('cvsu_id', 'N/A')}</li>
        </ul>
        <p><strong>Note:</strong> Please contact your administrator to securely receive your temporary password, or use the "Forgot Password" feature if available.</p>
    </div>
    """
    queue_email(background_tasks, email, "Your Account Has Been Created", html_body)

    return created(_fmt(user))


@admin_users_router.put("/{user_id}")
async def admin_update(request: Request, user_id: str):
    auth = permission_required("edit_users")(request)
    existing = fetchone("SELECT * FROM users WHERE id = %s", [user_id])
    if not existing: return not_found()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _do_update(user_id, existing, body, auth)


@admin_users_router.patch("/{user_id}/status")
async def admin_update_status(request: Request, user_id: str, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_status = (body.get("status") or "").upper()
    if new_status not in VALID_STATUSES:
        return error(f"status must be one of: {', '.join(VALID_STATUSES)}")

    existing = fetchone("SELECT id, email, first_name, status FROM users WHERE id = %s", [user_id])
    if not existing: return not_found()

    required_perm = "edit_users"
    auth = permission_required(required_perm)(request)

    execute("UPDATE users SET status = %s WHERE id = %s", [new_status, user_id])

    if existing["status"] == "PENDING" and new_status == "ACTIVE":
        execute(
            "UPDATE users SET approved_by = %s, approved_at = NOW() WHERE id = %s",
            [auth.user_id, user_id],
        )

        # Queued Email for Approved User
        html_body = f"""
        <div style="font-family: Arial, sans-serif; color: #333;">
            <h2>Account Approved!</h2>
            <p>Hello {existing['first_name']},</p>
            <p>Great news! Your registration request has been <strong>APPROVED</strong> by an administrator.</p>
            <p>You can now log in to the platform using your email (<strong>{existing['email']}</strong>) and the password you created during sign-up.</p>
        </div>
        """
        queue_email(background_tasks, existing['email'], "Your Account has been Approved", html_body)

    log_action(f"User status changed to {new_status}", existing["email"], user_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"id": user_id, "status": new_status})


@admin_users_router.delete("/{user_id}")
async def admin_delete(request: Request, user_id: str):
    auth = permission_required("delete_users")(request)
    existing = fetchone("SELECT email FROM users WHERE id = %s", [user_id])
    if not existing: return not_found()
    if user_id == auth.user_id:
        return error("Cannot delete your own account", 400)
    execute("DELETE FROM users WHERE id = %s", [user_id])
    log_action("Deleted user", existing["email"], user_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()


# ═══════════════════════════════════════════════════════════════
# FACULTY — read-only, students only
# ═══════════════════════════════════════════════════════════════

@faculty_users_router.get("")
async def faculty_list(request: Request):
    auth = permission_required("view_students")(request)
    return ok(_list_users(request, role_lock="STUDENT"))


@faculty_users_router.get("/{user_id}")
async def faculty_get(request: Request, user_id: str):
    auth = permission_required("view_students")(request)
    u = fetchone(
        """SELECT u.*, r.name AS role FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s AND r.name = 'STUDENT'""",
        [user_id],
    )
    if not u: return not_found()
    return ok(_fmt(u))


def _do_update(user_id: str, existing: dict, body: dict, auth: AuthState):
    email = (body.get("email") or existing["email"]).strip().lower()
    if email != existing["email"].lower():
        if not validate_email(email):
            return error("Invalid email")
        if fetchone("SELECT id FROM users WHERE LOWER(email) = %s AND id != %s", [email, user_id]):
            return conflict("Email already in use")

    role_id = existing["role_id"]
    if body.get("role"):
        role_row = fetchone("SELECT id FROM roles WHERE name = %s", [body["role"].upper()])
        if not role_row:
            return error("Invalid role")
        role_id = role_row["id"]

    password = existing["password"]
    if body.get("password"):
        pw_err = validate_password(body["password"])
        if pw_err:
            return error(pw_err)
        password = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()
    try:
        updated = execute_returning(
            """UPDATE users
            SET cvsu_id = %s, first_name = %s, middle_name = %s, last_name = %s,
                email = %s, password = %s, role_id = %s,
                status = %s, department = %s, photo_avatar = %s
            WHERE id = %s
            RETURNING id, cvsu_id, first_name, last_name, email, status, photo_avatar""",
            [
                clean_str(body.get("cvsu_id",  existing["cvsu_id"])),
                clean_str(body.get("first_name",  existing["first_name"])),
                clean_str(body.get("middle_name", existing.get("middle_name"))),
                clean_str(body.get("last_name",   existing["last_name"])),
                email, password, role_id,
                (body.get("status") or existing["status"]).upper(),
                clean_str(body.get("department",  existing.get("department"))),
                body.get("photo_avatar", existing.get("photo_avatar")),
                user_id,
            ],
        )
    except:
        return error("ID already in use.")

    log_action("Updated user", updated["email"], user_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_fmt(updated))