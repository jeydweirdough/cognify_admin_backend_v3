"""
Whitelist routes
  ADMIN  → /api/web/admin/whitelist  (any role)
  FACULTY → /api/web/faculty/whitelist  (STUDENT only)
Both blueprints share the same query/mutation helpers below.
"""
import csv, io, json
from flask import Blueprint, request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, no_content, error, not_found, conflict
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import validate_email, require_fields, clean_str
from app.utils.log import log_action

admin_whitelist_bp   = Blueprint("admin_whitelist",   __name__, url_prefix="/api/web/admin/whitelist")
faculty_whitelist_bp = Blueprint("faculty_whitelist", __name__, url_prefix="/api/web/faculty/whitelist")

VALID_ROLES = {"ADMIN", "FACULTY", "STUDENT"}

# ── Shared query builder ──────────────────────────────────────────────────────

def _list_query(role_filter_lock=None):
    """
    Build a paginated whitelist response.
    role_filter_lock: if set, only that role is queryable (faculty sees STUDENT only).
    """
    page, per_page = get_page_params()
    search = get_search()
    role   = role_filter_lock or get_filter("role", VALID_ROLES)
    status = get_filter("status", {"PENDING", "REGISTERED"})

    sql   = ["SELECT * FROM whitelist WHERE 1=1"]
    params = []

    if search:
        sql.append("""AND (
            LOWER(first_name || ' ' || last_name) LIKE LOWER(%s)
            OR LOWER(email) LIKE LOWER(%s)
            OR LOWER(institutional_id) LIKE LOWER(%s)
        )""")
        params += [search, search, search]

    if role:
        sql.append("AND role = %s")
        params.append(role)

    if status:
        sql.append("AND status = %s")
        params.append(status)

    sql.append("ORDER BY date_added DESC")
    return paginate(" ".join(sql), params, page, per_page)


def _add_entry(body: dict, role_lock: str = None, added_by: str = None):
    required = ["first_name", "last_name", "institutional_id", "email"]
    if not role_lock:
        required.append("role")
    missing = require_fields(body, required)
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    email = body["email"].strip().lower()
    if not validate_email(email):
        return error("Invalid email address")

    role = (role_lock or body.get("role", "")).upper()
    if role not in VALID_ROLES:
        return error(f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    if fetchone("SELECT id FROM whitelist WHERE LOWER(email) = %s", [email]):
        return conflict("Email already whitelisted")

    entry = execute_returning(
        """INSERT INTO whitelist
               (first_name, middle_name, last_name, institutional_id, email, role, added_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING *""",
        [
            clean_str(body["first_name"]),
            clean_str(body.get("middle_name")),
            clean_str(body["last_name"]),
            clean_str(body["institutional_id"]),
            email, role,
            added_by,
        ],
    )
    log_action("Whitelist entry added", email, str(entry["id"]))
    return created(_fmt(entry))


def _fmt(e: dict) -> dict:
    """Serialize a whitelist row to the expected frontend shape."""
    e["id"] = str(e["id"])
    e["name"] = " ".join(filter(None, [e.get("first_name"), e.get("middle_name"), e.get("last_name")]))
    e["studentNumber"] = e.get("institutional_id")
    e["dateAdded"] = e["date_added"].isoformat() if e.get("date_added") else None
    return e


# ═══════════════════════════════════════════════════════════════
# ADMIN WHITELIST
# ═══════════════════════════════════════════════════════════════

@admin_whitelist_bp.get("")
@login_required
@roles_required("ADMIN")
def admin_list():
    return ok(_apply_fmt(_list_query()))


@admin_whitelist_bp.post("")
@login_required
@roles_required("ADMIN")
def admin_add():
    return _add_entry(request.get_json(silent=True) or {}, added_by=request.environ.get("user_id"))


@admin_whitelist_bp.post("/bulk")
@login_required
@roles_required("ADMIN")
def admin_bulk():
    """Accept JSON array or CSV file upload."""
    records = []

    if request.content_type and "multipart" in request.content_type:
        f = request.files.get("file")
        if not f:
            return error("No file provided")
        stream = io.StringIO(f.read().decode("utf-8-sig"))
        reader = csv.DictReader(stream)
        records = [row for row in reader]
    else:
        body = request.get_json(silent=True) or {}
        records = body if isinstance(body, list) else body.get("records", [])

    if not records:
        return error("No records provided")

    succeeded, failed = [], []
    for row in records:
        resp, status_code = _add_entry(row)
        data = resp.get_json()
        if data.get("success"):
            succeeded.append(data["data"])
        else:
            failed.append({"record": row, "reason": data.get("message")})

    log_action("Bulk whitelist upload", f"{len(succeeded)} added, {len(failed)} failed")
    return ok({"added": len(succeeded), "failed": len(failed), "errors": failed})


@admin_whitelist_bp.put("/<entry_id>")
@login_required
@roles_required("ADMIN")
def admin_update(entry_id):
    return _update_entry(entry_id, request.get_json(silent=True) or {})


@admin_whitelist_bp.delete("/<entry_id>")
@login_required
@roles_required("ADMIN")
def admin_delete(entry_id):
    return _delete_entry(entry_id)


# ═══════════════════════════════════════════════════════════════
# FACULTY WHITELIST  (STUDENT-only view)
# ═══════════════════════════════════════════════════════════════

@faculty_whitelist_bp.get("")
@login_required
@roles_required("FACULTY")
def faculty_list():
    return ok(_apply_fmt(_list_query(role_filter_lock="STUDENT")))


@faculty_whitelist_bp.post("")
@login_required
@roles_required("FACULTY")
def faculty_add():
    return _add_entry(
        request.get_json(silent=True) or {},
        role_lock="STUDENT",
        added_by=request.environ.get("user_id"),
    )


@faculty_whitelist_bp.put("/<entry_id>")
@login_required
@roles_required("FACULTY")
def faculty_update(entry_id):
    # Faculty may only edit STUDENT entries
    existing = fetchone("SELECT role FROM whitelist WHERE id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["role"] != "STUDENT":
        return error("Faculty can only manage STUDENT whitelist entries", 403)
    return _update_entry(entry_id, request.get_json(silent=True) or {})


@faculty_whitelist_bp.delete("/<entry_id>")
@login_required
@roles_required("FACULTY")
def faculty_delete(entry_id):
    existing = fetchone("SELECT role FROM whitelist WHERE id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["role"] != "STUDENT":
        return error("Faculty can only manage STUDENT whitelist entries", 403)
    return _delete_entry(entry_id)


# ── Shared mutation helpers ────────────────────────────────────────────────────

def _update_entry(entry_id: str, body: dict):
    existing = fetchone("SELECT * FROM whitelist WHERE id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["status"] == "REGISTERED":
        return error("Cannot edit a registered whitelist entry", 409)

    updated = execute_returning(
        """UPDATE whitelist
           SET first_name = %s, middle_name = %s, last_name = %s,
               institutional_id = %s, email = LOWER(%s), role = %s
           WHERE id = %s
           RETURNING *""",
        [
            clean_str(body.get("first_name", existing["first_name"])),
            clean_str(body.get("middle_name", existing.get("middle_name"))),
            clean_str(body.get("last_name",  existing["last_name"])),
            clean_str(body.get("institutional_id", existing["institutional_id"])),
            body.get("email", existing["email"]),
            (body.get("role") or existing["role"]).upper(),
            entry_id,
        ],
    )
    log_action("Whitelist entry updated", updated["email"], entry_id)
    return ok(_fmt(updated))


def _delete_entry(entry_id: str):
    existing = fetchone("SELECT email, status FROM whitelist WHERE id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["status"] == "REGISTERED":
        return error("Cannot delete a registered whitelist entry", 409)
    execute("DELETE FROM whitelist WHERE id = %s", [entry_id])
    log_action("Whitelist entry deleted", existing["email"], entry_id)
    return no_content()


def _apply_fmt(paginated: dict) -> dict:
    paginated["items"] = [_fmt(e) for e in paginated["items"]]
    return paginated