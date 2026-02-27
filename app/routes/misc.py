"""
Miscellaneous web routes:
  /api/web/admin/settings     → system settings CRUD (admin only)
  /api/web/admin/logs         → activity logs viewer (admin only)
  /api/web/admin/revisions    → revision management (admin only)
  /api/web/faculty/revisions  → faculty sees own revisions
  /api/web/admin/verification → pending approvals queue (admin)
  /api/web/faculty/verification → faculty submission queue
  /api/web/admin/roles        → role & permissions management
"""
import json
from flask import Blueprint, request, g
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, no_content, error, not_found
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import require_fields
from app.utils.log import log_action

settings_bp      = Blueprint("settings",      __name__, url_prefix="/api/web/admin/settings")
admin_logs_bp    = Blueprint("admin_logs",    __name__, url_prefix="/api/web/admin/logs")
admin_rev_bp     = Blueprint("admin_rev",     __name__, url_prefix="/api/web/admin/revisions")
faculty_rev_bp   = Blueprint("faculty_rev",   __name__, url_prefix="/api/web/faculty/revisions")
admin_verify_bp  = Blueprint("admin_verify",  __name__, url_prefix="/api/web/admin/verification")
faculty_verify_bp= Blueprint("faculty_verify",__name__, url_prefix="/api/web/faculty/verification")
roles_bp         = Blueprint("roles",         __name__, url_prefix="/api/web/admin/roles")


# ═══════════════════════════════════════════════════════════════
# SYSTEM SETTINGS
# ═══════════════════════════════════════════════════════════════

@settings_bp.get("")
@login_required
@roles_required("ADMIN")
def get_settings():
    row = fetchone("SELECT * FROM system_settings LIMIT 1")
    if row and row.get("updated_at"):
        row["updated_at"] = row["updated_at"].isoformat()
    return ok(row)


@settings_bp.put("")
@login_required
@roles_required("ADMIN")
def update_settings():
    body = request.get_json(silent=True) or {}
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
    log_action("Updated system settings")
    if updated and updated.get("updated_at"):
        updated["updated_at"] = updated["updated_at"].isoformat()
    return ok(updated)


# ═══════════════════════════════════════════════════════════════
# ACTIVITY LOGS
# ═══════════════════════════════════════════════════════════════

@admin_logs_bp.get("")
@login_required
@roles_required("ADMIN")
def list_logs():
    page, per_page = get_page_params()
    search  = get_search()
    user_id = (request.args.get("user_id") or "").strip() or None
    from_dt = (request.args.get("from") or "").strip() or None
    to_dt   = (request.args.get("to")   or "").strip() or None

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
        r["userName"] = r.pop("user_name", "—")
    return ok(result)


# ═══════════════════════════════════════════════════════════════
# REVISIONS
# ═══════════════════════════════════════════════════════════════

def _fmt_rev(r: dict) -> dict:
    r["id"] = str(r["id"])
    if r.get("target_id"): r["target_id"] = str(r["target_id"])
    if r.get("created_by"): r["created_by"] = str(r["created_by"])
    if r.get("created_at"): r["createdAt"] = r.pop("created_at").isoformat()
    r["category"] = r.get("target_type")
    return r


@admin_rev_bp.get("")
@login_required
@roles_required("ADMIN")
def admin_list_revisions():
    page, per_page = get_page_params()
    status = get_filter("status", {"PENDING", "RESOLVED"}) or "PENDING"
    result = paginate(
        """SELECT r.*, u.first_name || ' ' || u.last_name AS created_by_name
           FROM revisions r LEFT JOIN users u ON u.id = r.created_by
           WHERE r.status = %s ORDER BY r.created_at DESC""",
        [status], page, per_page,
    )
    result["items"] = [_fmt_rev(r) for r in result["items"]]
    return ok(result)


@admin_rev_bp.get("/<rev_id>")
@login_required
@roles_required("ADMIN")
def admin_get_revision(rev_id):
    r = fetchone(
        "SELECT r.*, u.first_name || ' ' || u.last_name AS created_by_name FROM revisions r LEFT JOIN users u ON u.id = r.created_by WHERE r.id = %s",
        [rev_id],
    )
    return ok(_fmt_rev(r)) if r else not_found()


@admin_rev_bp.patch("/<rev_id>/resolve")
@login_required
@roles_required("ADMIN")
def admin_resolve_revision(rev_id):
    r = fetchone("SELECT id, title FROM revisions WHERE id = %s", [rev_id])
    if not r:
        return not_found()
    execute("UPDATE revisions SET status = 'RESOLVED' WHERE id = %s", [rev_id])
    log_action("Revision resolved", r["title"], rev_id)
    return ok({"id": rev_id, "status": "RESOLVED"})


@faculty_rev_bp.get("")
@login_required
@roles_required("FACULTY")
def faculty_list_revisions():
    page, per_page = get_page_params()
    result = paginate(
        "SELECT * FROM revisions WHERE created_by = %s AND status = 'PENDING' ORDER BY created_at DESC",
        [g.user_id], page, per_page,
    )
    result["items"] = [_fmt_rev(r) for r in result["items"]]
    return ok(result)


@faculty_rev_bp.post("")
@login_required
@roles_required("FACULTY")
def faculty_create_revision():
    body = request.get_json(silent=True) or {}
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
            g.user_id,
        ],
    )
    log_action("Created revision request", r["title"], str(r["id"]))
    return created(_fmt_rev(r))


# ═══════════════════════════════════════════════════════════════
# VERIFICATION (pending approval queue)
# ═══════════════════════════════════════════════════════════════

@admin_verify_bp.get("")
@login_required
@roles_required("ADMIN")
def admin_verification_list():
    """Unified list of everything pending admin approval."""
    item_type = (request.args.get("type") or "all").lower()
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
            r["id"] = str(r["id"])
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
            r["id"] = str(r["id"])
            r["type"] = "Assessment"
            r["date"] = r["date"].isoformat()

    if item_type in ("all", "subjects"):
        result["subjects"] = fetchall(
            """SELECT s.id, s.name AS title, s.status, s.updated_at AS date
               FROM subjects s WHERE s.status = 'PENDING'
               ORDER BY s.updated_at"""
        )
        for r in result["subjects"]:
            r["id"] = str(r["id"])
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
            r["id"] = str(r["id"])
            r["type"] = "User"
            r["date"] = r["date"].isoformat()

    return ok(result)


@faculty_verify_bp.get("")
@login_required
@roles_required("FACULTY")
def faculty_verification_list():
    """Faculty sees their own pending submissions."""
    modules = fetchall(
        """SELECT cm.id, cm.title, cm.status, cm.last_updated AS date, s.name AS subject
           FROM content_modules cm LEFT JOIN subjects s ON s.id = cm.subject_id
           WHERE cm.author_id = %s AND cm.status IN ('PENDING','REVISION_REQUESTED','REMOVAL_PENDING')
           ORDER BY cm.last_updated""",
        [g.user_id],
    )
    assessments = fetchall(
        """SELECT a.id, a.title, a.status, a.updated_at AS date, s.name AS subject
           FROM assessments a LEFT JOIN subjects s ON s.id = a.subject_id
           WHERE a.author_id = %s AND a.status IN ('PENDING','REVISION_REQUESTED')
           ORDER BY a.updated_at""",
        [g.user_id],
    )
    for r in modules + assessments:
        r["id"] = str(r["id"])
        r["date"] = r["date"].isoformat()
    return ok({"modules": modules, "assessments": assessments})


# ═══════════════════════════════════════════════════════════════
# ROLES MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@roles_bp.get("")
@login_required
@roles_required("ADMIN")
def list_roles():
    rows = fetchall("SELECT id, name, permissions, is_system, created_at FROM roles ORDER BY name")
    for r in rows:
        r["id"] = str(r["id"])
        r["created_at"] = r["created_at"].isoformat()
    return ok(rows)


@roles_bp.get("/<role_id>")
@login_required
@roles_required("ADMIN")
def get_role(role_id):
    r = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not r:
        return not_found()
    r["id"] = str(r["id"])
    return ok(r)


@roles_bp.post("")
@login_required
@roles_required("ADMIN")
def create_role():
    body = request.get_json(silent=True) or {}
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
    log_action("Created role", r["name"], str(r["id"]))
    return created(r)


@roles_bp.put("/<role_id>")
@login_required
@roles_required("ADMIN")
def update_role(role_id):
    existing = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not existing:
        return not_found()
    if existing["is_system"]:
        return error("Cannot modify system roles", 403)
    body = request.get_json(silent=True) or {}
    r = execute_returning(
        "UPDATE roles SET name = %s, permissions = %s WHERE id = %s RETURNING *",
        [body.get("name", existing["name"]).upper(),
         json.dumps(body.get("permissions", existing["permissions"])),
         role_id],
    )
    r["id"] = str(r["id"])
    log_action("Updated role", r["name"], role_id)
    return ok(r)


@roles_bp.delete("/<role_id>")
@login_required
@roles_required("ADMIN")
def delete_role(role_id):
    r = fetchone("SELECT name, is_system FROM roles WHERE id = %s", [role_id])
    if not r:
        return not_found()
    if r["is_system"]:
        return error("Cannot delete system roles", 403)
    if fetchone("SELECT id FROM users WHERE role_id = %s LIMIT 1", [role_id]):
        return error("Cannot delete a role that has users assigned to it", 409)
    execute("DELETE FROM roles WHERE id = %s", [role_id])
    log_action("Deleted role", r["name"], role_id)
    return no_content()