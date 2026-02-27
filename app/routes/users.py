"""
User management routes
  /api/web/admin/users   → full CRUD (ADMIN only)
  /api/web/faculty/users → read-only, filtered to their subjects' students
  /api/web/admin/users/pending → list & approve pending registrations
"""
import bcrypt
from flask import Blueprint, request, g
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, no_content, error, not_found, conflict, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import validate_email, validate_password, require_fields, clean_str
from app.utils.log import log_action

admin_users_bp   = Blueprint("admin_users",   __name__, url_prefix="/api/web/admin/users")
faculty_users_bp = Blueprint("faculty_users", __name__, url_prefix="/api/web/faculty/users")

VALID_ROLES    = {"ADMIN", "FACULTY", "STUDENT"}
VALID_STATUSES = {"PENDING", "ACTIVE", "INACTIVE", "DEACTIVATED"}


# ── Shared formatter ───────────────────────────────────────────────────────────

def _fmt(u: dict) -> dict:
    u["id"] = str(u["id"])
    u.pop("password", None)   # never expose hash
    u["name"] = " ".join(filter(None, [u.get("first_name"), u.get("middle_name"), u.get("last_name")]))
    if u.get("role_id"):
        u["role_id"] = str(u["role_id"])
    if u.get("last_login"):
        u["last_login"] = u["last_login"].isoformat()
    if u.get("date_created"):
        u["date_created"] = u["date_created"].isoformat()
    return u


# ── Shared list builder ────────────────────────────────────────────────────────

def _list_users(role_lock: str = None):
    page, per_page = get_page_params()
    search = get_search()
    role   = role_lock or get_filter("role", VALID_ROLES)
    status = get_filter("status", VALID_STATUSES)

    sql = ["""
        SELECT u.*, r.name AS role, r.id AS role_id
        FROM users u JOIN roles r ON u.role_id = r.id
        WHERE 1=1
    """]
    params = []

    if search:
        sql.append("""AND (
            LOWER(u.first_name || ' ' || u.last_name) LIKE LOWER(%s)
            OR LOWER(u.email) LIKE LOWER(%s)
            OR LOWER(u.institutional_id) LIKE LOWER(%s)
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
# ADMIN — full CRUD
# ═══════════════════════════════════════════════════════════════

@admin_users_bp.get("")
@login_required
@roles_required("ADMIN")
def admin_list():
    return ok(_list_users())


@admin_users_bp.get("/pending")
@login_required
@roles_required("ADMIN")
def admin_pending():
    """Pending approval list (newly registered users)."""
    result = _list_users()
    # Override with status filter
    page, per_page = get_page_params()
    sql = """
        SELECT u.*, r.name AS role, r.id AS role_id
        FROM users u JOIN roles r ON u.role_id = r.id
        WHERE u.status = 'PENDING'
        ORDER BY u.date_created ASC
    """
    result = paginate(sql, [], page, per_page)
    result["items"] = [_fmt(u) for u in result["items"]]
    return ok(result)


@admin_users_bp.get("/<user_id>")
@login_required
@roles_required("ADMIN")
def admin_get(user_id):
    u = fetchone(
        "SELECT u.*, r.name AS role, r.id AS role_id FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = %s",
        [user_id]
    )
    if not u:
        return not_found()
    return ok(_fmt(u))


@admin_users_bp.post("")
@login_required
@roles_required("ADMIN")
def admin_create():
    body = request.get_json(silent=True) or {}
    required = ["first_name", "last_name", "email", "password", "role", "institutional_id"]
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
               (institutional_id, first_name, middle_name, last_name,
                email, password, role_id, status, department)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id, first_name, last_name, email, status""",
        [
            clean_str(body["institutional_id"]),
            clean_str(body["first_name"]),
            clean_str(body.get("middle_name")),
            clean_str(body["last_name"]),
            email, hashed, role_row["id"],
            (body.get("status") or "ACTIVE").upper(),
            clean_str(body.get("department")),
        ],
    )
    log_action("Created user", email, str(user["id"]))
    return created(_fmt(user))


@admin_users_bp.put("/<user_id>")
@login_required
@roles_required("ADMIN")
def admin_update(user_id):
    existing = fetchone("SELECT * FROM users WHERE id = %s", [user_id])
    if not existing:
        return not_found()
    body = request.get_json(silent=True) or {}
    return _do_update(user_id, existing, body)


@admin_users_bp.patch("/<user_id>/status")
@login_required
@roles_required("ADMIN")
def admin_update_status(user_id):
    body = request.get_json(silent=True) or {}
    new_status = (body.get("status") or "").upper()
    if new_status not in VALID_STATUSES:
        return error(f"status must be one of: {', '.join(VALID_STATUSES)}")

    existing = fetchone("SELECT id, email FROM users WHERE id = %s", [user_id])
    if not existing:
        return not_found()

    execute("UPDATE users SET status = %s WHERE id = %s", [new_status, user_id])
    log_action(f"User status changed to {new_status}", existing["email"], user_id)
    return ok({"id": user_id, "status": new_status})


@admin_users_bp.delete("/<user_id>")
@login_required
@roles_required("ADMIN")
def admin_delete(user_id):
    existing = fetchone("SELECT email FROM users WHERE id = %s", [user_id])
    if not existing:
        return not_found()
    if user_id == g.user_id:
        return error("Cannot delete your own account", 400)
    execute("DELETE FROM users WHERE id = %s", [user_id])
    log_action("Deleted user", existing["email"], user_id)
    return no_content()


# ═══════════════════════════════════════════════════════════════
# FACULTY — read-only, students only
# ═══════════════════════════════════════════════════════════════

@faculty_users_bp.get("")
@login_required
@roles_required("FACULTY")
def faculty_list():
    return ok(_list_users(role_lock="STUDENT"))


@faculty_users_bp.get("/<user_id>")
@login_required
@roles_required("FACULTY")
def faculty_get(user_id):
    u = fetchone(
        """SELECT u.*, r.name AS role FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s AND r.name = 'STUDENT'""",
        [user_id],
    )
    if not u:
        return not_found()
    return ok(_fmt(u))


# ── Shared update logic ───────────────────────────────────────────────────────

def _do_update(user_id: str, existing: dict, body: dict):
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

    # Optional password change
    password = existing["password"]
    if body.get("password"):
        pw_err = validate_password(body["password"])
        if pw_err:
            return error(pw_err)
        password = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()

    updated = execute_returning(
        """UPDATE users
           SET first_name = %s, middle_name = %s, last_name = %s,
               email = %s, password = %s, role_id = %s,
               status = %s, department = %s
           WHERE id = %s
           RETURNING id, first_name, last_name, email, status""",
        [
            clean_str(body.get("first_name",  existing["first_name"])),
            clean_str(body.get("middle_name", existing.get("middle_name"))),
            clean_str(body.get("last_name",   existing["last_name"])),
            email, password, role_id,
            (body.get("status") or existing["status"]).upper(),
            clean_str(body.get("department",  existing.get("department"))),
            user_id,
        ],
    )
    log_action("Updated user", updated["email"], user_id)
    return ok(_fmt(updated))