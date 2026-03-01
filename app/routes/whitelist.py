"""
Whitelist routes — shows users with status = 'PENDING'

  The "whitelist" view is simply users in the users table whose status is PENDING.
  PENDING = registered an account but not yet approved/activated.

  GET  lists   → SELECT FROM users WHERE status = 'PENDING'
  POST/PUT/DEL → still manage the whitelist pre-registration table

  ADMIN  → /api/web/admin/whitelist   (all roles)
  FACULTY → /api/web/faculty/whitelist (STUDENT role only)
"""
import csv, io, json
from fastapi import APIRouter, Request
from app.db import fetchone, execute, execute_returning, paginate
from app.middleware.auth import login_required
from app.utils.responses import ok, created, no_content, error, not_found, conflict, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import validate_email, require_fields, clean_str
from app.utils.log import log_action

admin_whitelist_router   = APIRouter(prefix="/api/web/admin/whitelist",   tags=["admin-whitelist"])
faculty_whitelist_router = APIRouter(prefix="/api/web/faculty/whitelist", tags=["faculty-whitelist"])

VALID_ROLES = {"ADMIN", "FACULTY", "STUDENT"}


def _fmt_user(u: dict) -> dict:
    """Format a users-table row for the whitelist response."""
    u["id"]            = str(u["id"])
    u["name"]          = " ".join(filter(None, [u.get("first_name"), u.get("middle_name"), u.get("last_name")]))
    u["studentNumber"] = u.get("institutional_id")
    u["dateAdded"]     = u["date_created"].isoformat() if u.get("date_created") else None
    u.pop("password", None)
    if u.get("role_id"): u["role_id"] = str(u["role_id"])
    return u


def _apply_fmt(paginated: dict) -> dict:
    paginated["items"] = [_fmt_user(u) for u in paginated["items"]]
    return paginated


def _list_pending(request: Request, role_lock: str = None):
    """Return users WHERE status = 'PENDING', optionally filtered by role."""
    page, per_page = get_page_params(request)
    search = get_search(request)
    role   = role_lock or get_filter(request, "role", VALID_ROLES)

    sql    = ["""
        SELECT u.*, r.name AS role, r.id AS role_id
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.status = 'PENDING'
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

    sql.append("ORDER BY u.date_created DESC")
    return paginate(" ".join(sql), params, page, per_page)


# ─── Whitelist table helpers (for add/edit/delete) ───────────────────────────

def _fmt_wl(e: dict) -> dict:
    """Format a whitelist-table row."""
    e["id"]            = str(e["id"])
    e["name"]          = " ".join(filter(None, [e.get("first_name"), e.get("middle_name"), e.get("last_name")]))
    e["studentNumber"] = e.get("institutional_id")
    e["dateAdded"]     = e["date_added"].isoformat() if e.get("date_added") else None
    return e


def _add_entry(body: dict, role_lock: str = None, added_by: str = None, ip: str = None):
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

    if fetchone("SELECT id FROM users WHERE status = 'PENDING' AND LOWER(email) = %s", [email]):
        return conflict("Email already whitelisted")

    if fetchone("SELECT id FROM users WHERE LOWER(email) = %s", [email]):
        return conflict("Email already belongs to a registered user")

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
            email, role, added_by,
        ],
    )
    log_action("Whitelist entry added", email, str(entry["id"]), user_id=added_by, ip=ip)
    return created(_fmt_wl(entry))


def _update_entry(entry_id: str, body: dict, auth, role_lock: str = None):
    existing = fetchone("SELECT * FROM users WHERE status = 'PENDING' AND id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["status"] == "REGISTERED":
        return error("This entry has already been used for registration.", 409)

    new_email = body.get("email", existing["email"]).strip().lower()
    if new_email != existing["email"].lower():
        if not validate_email(new_email):
            return error("Invalid email address")
        if fetchone("SELECT id FROM users WHERE status = 'PENDING' AND LOWER(email) = %s AND id != %s", [new_email, entry_id]):
            return conflict("Email already whitelisted")
        if fetchone("SELECT id FROM users WHERE LOWER(email) = %s", [new_email]):
            return conflict("Email already belongs to a registered user")

    new_role = (role_lock or body.get("role") or existing["role"]).upper()

    updated = execute_returning(
        """UPDATE whitelist
           SET first_name = %s, middle_name = %s, last_name = %s,
               institutional_id = %s, email = LOWER(%s), role = %s
           WHERE id = %s
           RETURNING *""",
        [
            clean_str(body.get("first_name",      existing["first_name"])),
            clean_str(body.get("middle_name",      existing.get("middle_name"))),
            clean_str(body.get("last_name",        existing["last_name"])),
            clean_str(body.get("institutional_id", existing["institutional_id"])),
            new_email, new_role, entry_id,
        ],
    )
    log_action("Whitelist entry updated", updated["email"], entry_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_fmt_wl(updated))


def _delete_entry(entry_id: str, auth):
    existing = fetchone("SELECT email, status FROM users WHERE status = 'PENDING' AND id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["status"] == "REGISTERED":
        return error("This entry has already been used for registration.", 409)
    execute("DELETE FROM users WHERE status = 'PENDING' AND id = %s", [entry_id])
    log_action("Whitelist entry deleted", existing["email"], entry_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_whitelist_router.get("")
async def admin_list(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return ok(_apply_fmt(_list_pending(request)))


@admin_whitelist_router.post("")
async def admin_add(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _add_entry(body, added_by=auth.user_id, ip=auth.ip)


@admin_whitelist_router.post("/bulk")
async def admin_bulk(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()

    content_type = request.headers.get("content-type", "")
    records = []

    if "multipart" in content_type:
        form = await request.form()
        f = form.get("file")
        if not f:
            return error("No file provided")
        content = await f.read()
        stream = io.StringIO(content.decode("utf-8-sig"))
        reader = csv.DictReader(stream)
        records = [row for row in reader]
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        records = body if isinstance(body, list) else body.get("records", [])

    if not records:
        return error("No records provided")

    succeeded, failed = [], []
    for row in records:
        result = _add_entry(row, added_by=auth.user_id, ip=auth.ip)
        if hasattr(result, "body"):
            data = json.loads(result.body)
            if data.get("success"):
                succeeded.append(data["data"])
            else:
                failed.append({"record": row, "reason": data.get("message")})
        else:
            failed.append({"record": row, "reason": "Unknown error"})

    log_action("Bulk whitelist upload", f"{len(succeeded)} added, {len(failed)} failed",
               user_id=auth.user_id, ip=auth.ip)
    return ok({"added": len(succeeded), "failed": len(failed), "errors": failed})


@admin_whitelist_router.put("/{entry_id}")
async def admin_update(request: Request, entry_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update_entry(entry_id, body, auth)


@admin_whitelist_router.delete("/{entry_id}")
async def admin_delete(request: Request, entry_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return _delete_entry(entry_id, auth)


# ═══════════════════════════════════════════════════════════════
# FACULTY — STUDENT role only
# ═══════════════════════════════════════════════════════════════

@faculty_whitelist_router.get("")
async def faculty_list(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    return ok(_apply_fmt(_list_pending(request, role_lock="STUDENT")))


@faculty_whitelist_router.post("")
async def faculty_add(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _add_entry(body, role_lock="STUDENT", added_by=auth.user_id, ip=auth.ip)


@faculty_whitelist_router.put("/{entry_id}")
async def faculty_update(request: Request, entry_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    existing = fetchone("SELECT role FROM users WHERE status = 'PENDING' AND id = %s", [entry_id])
    if not existing: return not_found("Whitelist entry not found")
    if existing["role"] != "STUDENT": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update_entry(entry_id, body, auth, role_lock="STUDENT")


@faculty_whitelist_router.delete("/{entry_id}")
async def faculty_delete(request: Request, entry_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    existing = fetchone("SELECT role FROM users WHERE status = 'PENDING' AND id = %s", [entry_id])
    if not existing: return not_found("Whitelist entry not found")
    if existing["role"] != "STUDENT": return forbidden()
    return _delete_entry(entry_id, auth)