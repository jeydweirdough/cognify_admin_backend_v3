"""
Whitelist routes — manages the pre-registration whitelist table.

  The whitelist table stores entries added by admins/faculty BEFORE a user
  registers.  status=PENDING means the entry is waiting for the user to sign up;
  status=REGISTERED means the user has already used this entry to create an account.

  Signup (auth.py) checks this table: entry must exist with status=PENDING.
  When signup succeeds the entry is flipped to REGISTERED (one-time use).

  ADMIN  → /api/web/admin/whitelist   (all roles)
  FACULTY → /api/web/faculty/whitelist (STUDENT role only)
"""
import csv, io, json
from fastapi import APIRouter, Request
from app.db import fetchone, execute, execute_returning, paginate
from app.middleware.auth import permission_required
from app.utils.responses import ok, created, no_content, error, not_found, conflict, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import validate_email, require_fields, clean_str
from app.utils.log import log_action

admin_whitelist_router   = APIRouter(prefix="/api/web/admin/whitelist",   tags=["admin-whitelist"])
faculty_whitelist_router = APIRouter(prefix="/api/web/faculty/whitelist", tags=["faculty-whitelist"])

VALID_ROLES    = {"ADMIN", "FACULTY", "STUDENT"}
VALID_STATUSES = {"PENDING", "REGISTERED"}


def _fmt_wl(e: dict) -> dict:
    """Format a whitelist table row for API responses."""
    e["id"]            = str(e["id"])
    e["name"]          = " ".join(filter(None, [e.get("first_name"), e.get("middle_name"), e.get("last_name")]))
    e["studentNumber"] = e.get("institutional_id")
    e["dateAdded"]     = e["date_added"].isoformat() if e.get("date_added") else None
    if e.get("added_by"): e["added_by"] = str(e["added_by"])
    e["yearLevel"]     = e.get("year_level") # Provide camelCase for frontend consistency
    return e


def _apply_wl_fmt(paginated: dict) -> dict:
    paginated["items"] = [_fmt_wl(e) for e in paginated["items"]]
    return paginated


def _list_whitelist(request: Request, role_lock: str = None):
    """Return whitelist table entries, optionally filtered by role."""
    page, per_page = get_page_params(request)
    search = get_search(request)
    role   = role_lock or get_filter(request, "role", VALID_ROLES)
    status = get_filter(request, "status", VALID_STATUSES)

    sql    = ["""
        SELECT w.*, u.first_name || ' ' || u.last_name AS added_by_name
        FROM whitelist w
        LEFT JOIN users u ON w.added_by = u.id
        WHERE 1=1
    """]
    params = []

    if search:
        like = f"%{search}%"
        sql.append("""AND (
            LOWER(w.first_name || ' ' || w.last_name) LIKE LOWER(%s)
            OR LOWER(w.email) LIKE LOWER(%s)
            OR LOWER(COALESCE(w.institutional_id, '')) LIKE LOWER(%s)
        )""")
        params += [like, like, like]

    if role:
        sql.append("AND w.role = %s")
        params.append(role)

    if status:
        sql.append("AND w.status = %s")
        params.append(status)

    sql.append("ORDER BY w.date_added DESC")
    return paginate(" ".join(sql), params, page, per_page)


def _add_entry(body: dict, role_lock: str = None, added_by: str = None, ip: str = None):
    """Insert a new entry into the whitelist table.  Does NOT create a user account."""
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

    # Duplicate checks in the whitelist table itself
    if fetchone("SELECT id FROM whitelist WHERE LOWER(email) = %s", [email]):
        return conflict("Email is already in the whitelist")
    if fetchone("SELECT id FROM whitelist WHERE LOWER(institutional_id) = LOWER(%s)", [clean_str(body["institutional_id"])]):
        return conflict("Institutional ID is already in the whitelist")

    # Block re-whitelisting someone who already has an active account
    if fetchone("SELECT id FROM users WHERE LOWER(email) = %s AND status != 'REMOVED'", [email]):
        return conflict("A registered account already exists with this email")

    entry = execute_returning(
        """INSERT INTO whitelist
               (first_name, middle_name, last_name, institutional_id, email, role, status, added_by, year_level)
           VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s)
           RETURNING *""",
        [
            clean_str(body["first_name"]),
            clean_str(body.get("middle_name")),
            clean_str(body["last_name"]),
            clean_str(body["institutional_id"]),
            email,
            role,
            added_by,
            # Accept various key formats (snake_case, camelCase, or Space Separated)
            body.get("year_level") or body.get("yearLevel") or body.get("Year Level") or body.get("year level"),
        ],
    )
    log_action("Whitelist entry added", email, str(entry["id"]), user_id=added_by, ip=ip)
    return created(_fmt_wl(entry))


def _update_entry(entry_id: str, body: dict, auth, role_lock: str = None):
    """Update a PENDING whitelist entry. REGISTERED entries cannot be edited."""
    existing = fetchone("SELECT * FROM whitelist WHERE status = 'PENDING' AND id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found or already used for registration")

    new_email = body.get("email", existing["email"]).strip().lower()
    if new_email != existing["email"].lower():
        if not validate_email(new_email):
            return error("Invalid email address")
        if fetchone("SELECT id FROM whitelist WHERE LOWER(email) = %s AND id != %s", [new_email, entry_id]):
            return conflict("Email already in whitelist")
        if fetchone("SELECT id FROM users WHERE LOWER(email) = %s AND status != 'REMOVED'", [new_email]):
            return conflict("Email already belongs to a registered user")

    new_role = (role_lock or body.get("role") or existing["role"]).upper()
    if new_role not in VALID_ROLES:
        return error(f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    updated = execute_returning(
        """UPDATE whitelist
           SET first_name = %s, middle_name = %s, last_name = %s,
               institutional_id = %s, email = LOWER(%s), role = %s,
               year_level = %s
           WHERE id = %s AND status = 'PENDING'
           RETURNING *""",
        [
            clean_str(body.get("first_name",      existing["first_name"])),
            clean_str(body.get("middle_name",      existing.get("middle_name"))),
            clean_str(body.get("last_name",        existing["last_name"])),
            clean_str(body.get("institutional_id", existing["institutional_id"])),
            new_email, new_role, 
            body.get("year_level") or body.get("yearLevel") or body.get("Year Level") or body.get("year level") or existing.get("year_level"),
            entry_id,
        ],
    )
    if not updated:
        return not_found("Entry not found or already used")
    log_action("Whitelist entry updated", updated["email"], entry_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_fmt_wl(updated))


def _delete_entry(entry_id: str, auth):
    """Delete a PENDING whitelist entry. REGISTERED entries cannot be deleted."""
    existing = fetchone("SELECT email, status FROM whitelist WHERE id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["status"] == "REGISTERED":
        return error("This entry has already been used for registration and cannot be deleted.", 409)
    execute("DELETE FROM whitelist WHERE id = %s", [entry_id])
    log_action("Whitelist entry deleted", existing["email"], entry_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_whitelist_router.get("")
async def admin_list(request: Request):
    auth = permission_required("view_whitelist")(request)
    return ok(_apply_wl_fmt(_list_whitelist(request)))


@admin_whitelist_router.get("/{entry_id}")
async def admin_get(request: Request, entry_id: str):
    """Fetch a single whitelist entry by ID (used by the edit page)."""
    auth = permission_required("view_whitelist")(request)
    entry = fetchone("SELECT * FROM whitelist WHERE id = %s", [entry_id])
    if not entry:
        return not_found("Whitelist entry not found")
    return ok(_fmt_wl(entry))


@admin_whitelist_router.post("")
async def admin_add(request: Request):
    auth = permission_required("add_whitelist")(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _add_entry(body, added_by=auth.user_id, ip=auth.ip)


@admin_whitelist_router.post("/bulk")
async def admin_bulk(request: Request):
    auth = permission_required("add_whitelist")(request)

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
    auth = permission_required("edit_whitelist")(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update_entry(entry_id, body, auth)


@admin_whitelist_router.delete("/{entry_id}")
async def admin_delete(request: Request, entry_id: str):
    auth = permission_required("delete_whitelist")(request)
    return _delete_entry(entry_id, auth)


# ═══════════════════════════════════════════════════════════════
# FACULTY — STUDENT role only
# ═══════════════════════════════════════════════════════════════

@faculty_whitelist_router.get("")
async def faculty_list(request: Request):
    auth = permission_required("view_whitelist")(request)
    return ok(_apply_wl_fmt(_list_whitelist(request, role_lock="STUDENT")))


@faculty_whitelist_router.post("")
async def faculty_add(request: Request):
    auth = permission_required("add_whitelist")(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _add_entry(body, role_lock="STUDENT", added_by=auth.user_id, ip=auth.ip)


@faculty_whitelist_router.get("/{entry_id}")
async def faculty_get(request: Request, entry_id: str):
    """Fetch a single student whitelist entry by ID (used by the edit page)."""
    auth = permission_required("view_whitelist")(request)
    entry = fetchone("SELECT * FROM whitelist WHERE id = %s AND role = 'STUDENT'", [entry_id])
    if not entry:
        return not_found("Whitelist entry not found")
    return ok(_fmt_wl(entry))


@faculty_whitelist_router.put("/{entry_id}")
async def faculty_update(request: Request, entry_id: str):
    auth = permission_required("edit_whitelist")(request)
    existing = fetchone("SELECT * FROM whitelist WHERE status = 'PENDING' AND id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["role"].upper() != "STUDENT":
        return forbidden("Faculty can only edit student entries")
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update_entry(entry_id, body, auth, role_lock="STUDENT")


@faculty_whitelist_router.delete("/{entry_id}")
async def faculty_delete(request: Request, entry_id: str):
    auth = permission_required("delete_whitelist")(request)
    existing = fetchone("SELECT * FROM whitelist WHERE id = %s", [entry_id])
    if not existing:
        return not_found("Whitelist entry not found")
    if existing["role"].upper() != "STUDENT":
        return forbidden("Faculty can only delete student entries")
    return _delete_entry(entry_id, auth)