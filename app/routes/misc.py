"""
Miscellaneous web routes:
  /api/web/admin/settings     → system settings CRUD
  /api/web/admin/logs         → activity logs viewer
  /api/web/admin/revisions    → revision management
  /api/web/faculty/revisions  → faculty sees own revisions
  /api/web/admin/verification → pending approvals queue
  /api/web/faculty/verification → faculty submission queue
  /api/web/admin/roles        → role & permissions management
"""
import json
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import require_fields
from app.utils.log import log_action

settings_router       = APIRouter(prefix="/api/web/admin/settings",       tags=["settings"])
admin_logs_router     = APIRouter(prefix="/api/web/admin/logs",            tags=["admin-logs"])
admin_rev_router      = APIRouter(prefix="/api/web/admin/revisions",       tags=["admin-revisions"])
faculty_rev_router    = APIRouter(prefix="/api/web/faculty/revisions",     tags=["faculty-revisions"])
admin_verify_router   = APIRouter(prefix="/api/web/admin/verification",    tags=["admin-verification"])
faculty_verify_router = APIRouter(prefix="/api/web/faculty/verification",  tags=["faculty-verification"])
roles_router          = APIRouter(prefix="/api/web/admin/roles",           tags=["roles"])


# ═══════════════════════════════════════════════════════════════
# SYSTEM SETTINGS
# ═══════════════════════════════════════════════════════════════

@settings_router.get("")
async def get_settings(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    row = fetchone("SELECT * FROM system_settings LIMIT 1")
    if row and row.get("updated_at"):
        row["updated_at"] = row["updated_at"].isoformat()
    return ok(row)


@settings_router.put("")
async def update_settings(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    existing = fetchone("SELECT * FROM system_settings LIMIT 1")
    if not existing:
        return error("Settings not initialised", 500)

    updated = execute_returning(
        """UPDATE system_settings
           SET maintenance_mode            = %s,
               maintenance_banner         = %s,
               require_content_approval   = %s,
               allow_public_registration  = %s,
               institutional_passing_grade= %s,
               institution_name           = %s,
               academic_year              = %s,
               updated_at                 = NOW()
           WHERE id = 1 RETURNING *""",
        [
            bool(body.get("maintenanceMode",         existing["maintenance_mode"])),
            body.get("maintenanceBanner",              existing.get("maintenance_banner")),
            bool(body.get("requireContentApproval",  existing["require_content_approval"])),
            bool(body.get("allowPublicRegistration", existing["allow_public_registration"])),
            int(body.get("institutionalPassingGrade", existing["institutional_passing_grade"])),
            body.get("institutionName",               existing["institution_name"]),
            body.get("academicYear",                  existing["academic_year"]),
        ],
    )
    log_action("Updated system settings", user_id=auth.user_id, ip=auth.ip)
    if updated and updated.get("updated_at"):
        updated["updated_at"] = updated["updated_at"].isoformat()
    return ok(updated)


# ═══════════════════════════════════════════════════════════════
# ACTIVITY LOGS
# ═══════════════════════════════════════════════════════════════

@admin_logs_router.get("")
async def list_logs(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()

    page, per_page = get_page_params(request)
    search  = get_search(request)
    user_id = (request.query_params.get("user_id") or "").strip() or None
    from_dt = (request.query_params.get("from") or "").strip() or None
    to_dt   = (request.query_params.get("to")   or "").strip() or None

    sql = ["""
        SELECT al.id, al.action, al.target, al.target_id, al.ip_address, al.created_at,
               u.first_name || ' ' || u.last_name AS user_name,
               u.id AS user_id
        FROM activity_logs al LEFT JOIN users u ON u.id = al.user_id
        WHERE 1=1
    """]
    params = []

    if search:
        sql.append("AND (LOWER(al.action) LIKE LOWER(%s) OR LOWER(COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'')) LIKE LOWER(%s))")
        params += [search, search]
    if user_id:
        sql.append("AND al.user_id = %s")
        params.append(user_id)
    if from_dt:
        sql.append("AND al.created_at >= %s")
        params.append(from_dt)
    if to_dt:
        sql.append("AND al.created_at <= %s")
        params.append(to_dt)

    sql.append("ORDER BY al.created_at DESC")
    result = paginate(" ".join(sql), params, page, per_page)
    for r in result["items"]:
        r["id"] = str(r["id"])
        if r.get("user_id"): r["user_id"] = str(r["user_id"])
        r["timestamp"] = r.pop("created_at").isoformat()
        r["userName"]  = r.pop("user_name", "—")
    return ok(result)


# ═══════════════════════════════════════════════════════════════
# REVISIONS
# ═══════════════════════════════════════════════════════════════

def _fmt_rev(r: dict) -> dict:
    r["id"] = str(r["id"])
    if r.get("target_id"):  r["target_id"]  = str(r["target_id"])
    if r.get("created_by"): r["created_by"] = str(r["created_by"])
    if r.get("created_at"): r["createdAt"]  = r.pop("created_at").isoformat()
    r["category"] = r.get("target_type")
    return r


@admin_rev_router.get("")
async def admin_list_revisions(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    page, per_page = get_page_params(request)
    status = get_filter(request, "status", {"PENDING", "RESOLVED"}) or "PENDING"
    result = paginate(
        """SELECT r.*, u.first_name || ' ' || u.last_name AS created_by_name
           FROM revisions r LEFT JOIN users u ON u.id = r.created_by
           WHERE r.status = %s ORDER BY r.created_at DESC""",
        [status], page, per_page,
    )
    result["items"] = [_fmt_rev(r) for r in result["items"]]
    return ok(result)


@admin_rev_router.get("/{rev_id}")
async def admin_get_revision(request: Request, rev_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    r = fetchone(
        "SELECT r.*, u.first_name || ' ' || u.last_name AS created_by_name FROM revisions r LEFT JOIN users u ON u.id = r.created_by WHERE r.id = %s",
        [rev_id],
    )
    return ok(_fmt_rev(r)) if r else not_found()


@admin_rev_router.patch("/{rev_id}/resolve")
async def admin_resolve_revision(request: Request, rev_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    r = fetchone("SELECT id, title FROM revisions WHERE id = %s", [rev_id])
    if not r: return not_found()
    execute("UPDATE revisions SET status = 'RESOLVED' WHERE id = %s", [rev_id])
    log_action("Revision resolved", r["title"], rev_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"id": rev_id, "status": "RESOLVED"})


@faculty_rev_router.get("")
async def faculty_list_revisions(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    page, per_page = get_page_params(request)
    result = paginate(
        "SELECT * FROM revisions WHERE created_by = %s AND status = 'PENDING' ORDER BY created_at DESC",
        [auth.user_id], page, per_page,
    )
    result["items"] = [_fmt_rev(r) for r in result["items"]]
    return ok(result)


@faculty_rev_router.post("")
async def faculty_create_revision(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    missing = require_fields(body, ["target_type", "target_id", "title"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    r = execute_returning(
        """INSERT INTO revisions (target_type, target_id, title, details, category, notes, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        [
            body["target_type"].upper(),
            body["target_id"],
            body["title"],
            body.get("details"),
            body["target_type"].upper(),
            json.dumps(body.get("notes", [])),
            auth.user_id,
        ],
    )
    log_action("Created revision request", r["title"], str(r["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(_fmt_rev(r))


# ═══════════════════════════════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════════════════════════════

@admin_verify_router.get("")
async def admin_verification_list(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()

    item_type = (request.query_params.get("type") or "all").lower()
    result = {"modules": [], "assessments": [], "subjects": [], "users": []}

    if item_type in ("all", "modules"):
        result["modules"] = fetchall(
            """SELECT cm.id, cm.title, cm.status, cm.last_updated AS date,
                      u.first_name || ' ' || u.last_name AS author,
                      s.name AS subject
               FROM content_modules cm
               LEFT JOIN users u ON u.id = cm.author_id
               LEFT JOIN subjects s ON s.id = cm.subject_id
               WHERE cm.status IN ('PENDING','REMOVAL_PENDING')
               ORDER BY cm.last_updated"""
        )
        for r in result["modules"]:
            r["id"]   = str(r["id"])
            r["type"] = "Module"
            r["date"] = r["date"].isoformat()

    if item_type in ("all", "assessments"):
        result["assessments"] = fetchall(
            """SELECT a.id, a.title, a.status, a.updated_at AS date,
                      u.first_name || ' ' || u.last_name AS author,
                      s.name AS subject
               FROM assessments a
               LEFT JOIN users u ON u.id = a.author_id
               LEFT JOIN subjects s ON s.id = a.subject_id
               WHERE a.status = 'PENDING'
               ORDER BY a.updated_at"""
        )
        for r in result["assessments"]:
            r["id"]   = str(r["id"])
            r["type"] = "Assessment"
            r["date"] = r["date"].isoformat()

    if item_type in ("all", "subjects"):
        result["subjects"] = fetchall(
            """SELECT s.id, s.name AS title, s.status, s.updated_at AS date
               FROM subjects s WHERE s.status = 'PENDING'
               ORDER BY s.updated_at"""
        )
        for r in result["subjects"]:
            r["id"]   = str(r["id"])
            r["type"] = "Subject"
            r["date"] = r["date"].isoformat()

    if item_type in ("all", "users"):
        result["users"] = fetchall(
            """SELECT u.id, u.first_name || ' ' || u.last_name AS name,
                      u.email, u.date_created AS date, r.name AS role
               FROM users u JOIN roles r ON u.role_id = r.id
               WHERE u.status = 'PENDING' ORDER BY u.date_created"""
        )
        for r in result["users"]:
            r["id"]   = str(r["id"])
            r["type"] = "User"
            r["date"] = r["date"].isoformat()

    return ok(result)


@faculty_verify_router.get("")
async def faculty_verification_list(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()

    modules = fetchall(
        """SELECT cm.id, cm.title, cm.status, cm.last_updated AS date, s.name AS subject
           FROM content_modules cm LEFT JOIN subjects s ON s.id = cm.subject_id
           WHERE cm.author_id = %s AND cm.status IN ('PENDING','REVISION_REQUESTED','REMOVAL_PENDING')
           ORDER BY cm.last_updated""",
        [auth.user_id],
    )
    assessments = fetchall(
        """SELECT a.id, a.title, a.status, a.updated_at AS date, s.name AS subject
           FROM assessments a LEFT JOIN subjects s ON s.id = a.subject_id
           WHERE a.author_id = %s AND a.status IN ('PENDING','REVISION_REQUESTED')
           ORDER BY a.updated_at""",
        [auth.user_id],
    )
    for r in modules + assessments:
        r["id"]   = str(r["id"])
        r["date"] = r["date"].isoformat()
    return ok({"modules": modules, "assessments": assessments})


# ═══════════════════════════════════════════════════════════════
# ROLES
# ═══════════════════════════════════════════════════════════════

@roles_router.get("")
async def list_roles(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    rows = fetchall("SELECT id, name, permissions, is_system, created_at FROM roles ORDER BY name")
    for r in rows:
        r["id"]         = str(r["id"])
        r["created_at"] = r["created_at"].isoformat()
    return ok(rows)


@roles_router.get("/{role_id}")
async def get_role(request: Request, role_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    r = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not r: return not_found()
    r["id"] = str(r["id"])
    return ok(r)


@roles_router.post("")
async def create_role(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    missing = require_fields(body, ["name"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")
    if fetchone("SELECT id FROM roles WHERE LOWER(name) = LOWER(%s)", [body["name"]]):
        return error("Role already exists", 409)
    r = execute_returning(
        "INSERT INTO roles (name, permissions, is_system) VALUES (%s, %s, FALSE) RETURNING *",
        [body["name"].upper(), json.dumps(body.get("permissions", []))],
    )
    r["id"] = str(r["id"])
    log_action("Created role", r["name"], str(r["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(r)


@roles_router.put("/{role_id}")
async def update_role(request: Request, role_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    existing = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not existing: return not_found()
    if existing["is_system"]:
        return error("Cannot modify system roles", 403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    r = execute_returning(
        "UPDATE roles SET name = %s, permissions = %s WHERE id = %s RETURNING *",
        [body.get("name", existing["name"]).upper(),
         json.dumps(body.get("permissions", existing["permissions"])),
         role_id],
    )
    r["id"] = str(r["id"])
    log_action("Updated role", r["name"], role_id, user_id=auth.user_id, ip=auth.ip)
    return ok(r)


@roles_router.delete("/{role_id}")
async def delete_role(request: Request, role_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    r = fetchone("SELECT name, is_system FROM roles WHERE id = %s", [role_id])
    if not r: return not_found()
    if r["is_system"]:
        return error("Cannot delete system roles", 403)
    if fetchone("SELECT id FROM users WHERE role_id = %s LIMIT 1", [role_id]):
        return error("Cannot delete a role that has users assigned to it", 409)
    execute("DELETE FROM roles WHERE id = %s", [role_id])
    log_action("Deleted role", r["name"], role_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()
