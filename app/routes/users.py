"""
Users CRUD — ADMIN full access, FACULTY/STUDENT read own profile only.
Whitelist (PENDING) management is admin-only.
"""
import bcrypt
from flask import Blueprint, request, g
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required, owner_or_admin
from app.utils.responses import ok, created, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search

bp = Blueprint("users", __name__, url_prefix="/api/users")

# ── Admin: list all registered (non-pending) users ───────────────────────────

@bp.get("/")
@login_required
@roles_required("ADMIN")
def list_users():
    page, per_page = get_page_params()
    search = get_search()
    role_filter = request.args.get("role")
    status_filter = request.args.get("status")

    conditions = ["u.status != 'PENDING'"]
    params = []

    if search:
        conditions.append(
            "(LOWER(u.first_name) LIKE LOWER(%s) OR LOWER(u.last_name) LIKE LOWER(%s) "
            "OR LOWER(u.email) LIKE LOWER(%s))"
        )
        params += [search, search, search]
    if role_filter:
        conditions.append("r.name = %s")
        params.append(role_filter.upper())
    if status_filter:
        conditions.append("u.status = %s")
        params.append(status_filter.upper())

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT u.id, u.first_name, u.middle_name, u.last_name,
               CONCAT(u.first_name,' ',u.last_name) AS full_name,
               u.email, u.department, u.status,
               r.id AS role_id, r.name AS role_name,
               u.date_created, u.last_login, u.last_updated
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        {where}
        ORDER BY u.date_created DESC
    """
    result = paginate(sql, params, page, per_page)
    return ok(result)


# ── Admin: pending (whitelist) users ─────────────────────────────────────────

@bp.get("/pending")
@login_required
@roles_required("ADMIN")
def list_pending():
    page, per_page = get_page_params()
    search = get_search()
    params = []
    conditions = ["u.status = 'PENDING'"]
    if search:
        conditions.append(
            "(LOWER(u.first_name) LIKE LOWER(%s) OR LOWER(u.last_name) LIKE LOWER(%s) "
            "OR LOWER(u.email) LIKE LOWER(%s))"
        )
        params += [search, search, search]
    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT u.id, u.first_name, u.last_name, u.email, u.department,
               u.status, r.name AS role_name, u.date_created
        FROM users u LEFT JOIN roles r ON u.role_id = r.id
        {where} ORDER BY u.date_created DESC
    """
    return ok(paginate(sql, params, page, per_page))


# ── View single user (own profile or admin) ───────────────────────────────────

@bp.get("/<user_id>")
@login_required
def get_user(user_id):
    if g.role != "ADMIN" and g.user_id != user_id:
        return forbidden("Access denied")
    user = fetchone(
        """SELECT u.id, u.first_name, u.middle_name, u.last_name, u.email,
                  u.department, u.status, u.date_created, u.last_login, u.last_updated,
                  r.id AS role_id, r.name AS role_name, r.permissions,
                  COUNT(DISTINCT ar.id) AS total_assessments_taken,
                  MAX(ar.date_taken) AS last_assessment_date
           FROM users u
           LEFT JOIN roles r ON u.role_id = r.id
           LEFT JOIN assessment_results ar ON ar.student_id = u.id
           WHERE u.id = %s
           GROUP BY u.id, r.id""",
        [user_id]
    )
    if not user:
        return not_found("User not found")
    return ok(user)


# ── Admin: create user ────────────────────────────────────────────────────────

@bp.post("/")
@login_required
@roles_required("ADMIN")
def create_user():
    body = request.get_json(silent=True) or {}
    required = ["first_name", "last_name", "email", "password", "role_id"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    existing = fetchone("SELECT id FROM users WHERE LOWER(email) = LOWER(%s)", [body["email"]])
    if existing:
        return error("Email already registered", 409)

    role = fetchone("SELECT id FROM roles WHERE id = %s", [body["role_id"]])
    if not role:
        return error("Invalid role_id")

    hashed = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()
    user = execute_returning(
        """INSERT INTO users (first_name, middle_name, last_name, email, password,
                              department, role_id, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, first_name, last_name, email, status""",
        [body["first_name"], body.get("middle_name"), body["last_name"],
         body["email"].lower(), hashed, body.get("department"), body["role_id"],
         body.get("status", "ACTIVE")]
    )
    return created(user, "User created")


# ── Admin: approve pending user ───────────────────────────────────────────────

@bp.patch("/<user_id>/approve")
@login_required
@roles_required("ADMIN")
def approve_user(user_id):
    user = fetchone("SELECT id, status FROM users WHERE id = %s", [user_id])
    if not user:
        return not_found()
    if user["status"] != "PENDING":
        return error("User is not pending")
    execute("UPDATE users SET status = 'ACTIVE' WHERE id = %s", [user_id])
    return ok(message="User approved and activated")


# ── Update user (own profile or admin) ───────────────────────────────────────

@bp.put("/<user_id>")
@login_required
def update_user(user_id):
    if g.role != "ADMIN" and g.user_id != user_id:
        return forbidden("Access denied")

    body = request.get_json(silent=True) or {}
    allowed = ["first_name", "middle_name", "last_name", "department"]
    admin_only = ["status", "role_id"]

    updates, params = [], []
    for field in allowed:
        if field in body:
            updates.append(f"{field} = %s")
            params.append(body[field])
    if g.role == "ADMIN":
        for field in admin_only:
            if field in body:
                updates.append(f"{field} = %s")
                params.append(body[field])
    if "password" in body and body["password"]:
        updates.append("password = %s")
        params.append(bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode())

    if not updates:
        return error("No valid fields to update")

    params.append(user_id)
    execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", params)
    return ok(message="User updated")


# ── Admin: deactivate user ────────────────────────────────────────────────────

@bp.delete("/<user_id>")
@login_required
@roles_required("ADMIN")
def deactivate_user(user_id):
    if user_id == g.user_id:
        return error("Cannot deactivate yourself")
    rows = execute("UPDATE users SET status = 'DEACTIVATED' WHERE id = %s AND status != 'DEACTIVATED'", [user_id])
    if rows == 0:
        return not_found("User not found or already deactivated")
    return ok(message="User deactivated")


# ── Roles listing ─────────────────────────────────────────────────────────────

@bp.get("/roles/list")
@login_required
@roles_required("ADMIN")
def list_roles():
    roles = fetchall("SELECT id, name, permissions, is_system FROM roles ORDER BY name")
    return ok(roles)
