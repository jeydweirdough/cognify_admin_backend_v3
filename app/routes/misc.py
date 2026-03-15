"""
Miscellaneous web routes:
  /api/web/admin/settings  → system settings CRUD
  /api/web/admin/logs      → activity logs viewer
  /api/web/admin/roles     → role & permissions management
"""
import json
from psycopg2.extras import Json as PgJson
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, permission_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden, conflict
from app.utils.pagination import get_page_params, get_search
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

settings_router   = APIRouter(prefix="/api/web/admin/settings", tags=["settings"])
admin_logs_router = APIRouter(prefix="/api/web/admin/logs",     tags=["admin-logs"])
roles_router      = APIRouter(prefix="/api/web/admin/roles",    tags=["roles"])

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

@settings_router.get("")
async def get_settings(request: Request):
    auth = permission_required("view_settings")(request)
    s = fetchone("SELECT * FROM system_settings WHERE id = 1")
    if s:
        s["id"] = str(s["id"])
    return ok(s or {})

@settings_router.put("")
async def update_settings(request: Request):
    auth = permission_required("edit_settings")(request)
    try: body = await request.json()
    except Exception: body = {}
    
    s = fetchone("SELECT * FROM system_settings WHERE id = 1")
    if not s: return not_found("Settings not initialized")
    
    updated = execute_returning(
        """UPDATE system_settings SET 
            maintenance_mode = %s, maintenance_banner = %s,
            require_content_approval = %s, allow_public_registration = %s,
            institutional_passing_grade = %s, institution_name = %s,
            academic_year = %s, updated_at = NOW()
           WHERE id = 1 RETURNING *""",
        [
            bool(body.get("maintenance_mode", s["maintenance_mode"])),
            clean_str(body.get("maintenance_banner", s.get("maintenance_banner"))),
            bool(body.get("require_content_approval", s["require_content_approval"])),
            bool(body.get("allow_public_registration", s["allow_public_registration"])),
            int(body.get("institutional_passing_grade", s["institutional_passing_grade"])),
            clean_str(body.get("institution_name", s["institution_name"])),
            clean_str(body.get("academic_year", s["academic_year"]))
        ]
    )
    log_action("Updated system settings", user_id=auth.user_id, ip=auth.ip)
    updated["id"] = str(updated["id"])
    return ok(updated)

# ─────────────────────────────────────────────────────────────────────────────
# ACTIVITY LOGS
# ─────────────────────────────────────────────────────────────────────────────

@admin_logs_router.get("")
async def list_logs(request: Request):
    auth = permission_required("view_logs")(request)
    page, per_page = get_page_params(request)
    search = get_search(request)
    
    sql = """
        SELECT al.id, al.action, al.target, al.target_id, al.ip_address, al.created_at,
               u.email, u.first_name || ' ' || u.last_name AS user_name
        FROM activity_logs al
        LEFT JOIN users u ON u.id = al.user_id
        WHERE 1=1
    """
    params = []
    if search:
        like = f"%{search}%"
        sql += " AND (LOWER(al.action) LIKE LOWER(%s) OR LOWER(u.email) LIKE LOWER(%s) OR LOWER(u.first_name || ' ' || u.last_name) LIKE LOWER(%s))"
        params.extend([like, like, like])
        
    sql += " ORDER BY al.created_at DESC"
    result = paginate(sql, params, page, per_page)
    
    for r in result["items"]:
        r["id"] = str(r["id"])
        if r["target_id"]: r["target_id"] = str(r["target_id"])
        r["created_at"] = r["created_at"].isoformat()
        
    return ok(result)

# ─────────────────────────────────────────────────────────────────────────────
# ROLES
# ─────────────────────────────────────────────────────────────────────────────

@roles_router.get("")
async def list_roles(request: Request):
    auth = permission_required("view_roles")(request)
    roles = fetchall("SELECT * FROM roles ORDER BY name")
    for r in roles:
        r["id"] = str(r["id"])
        r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
    return ok(roles)


@roles_router.post("")
async def create_role(request: Request):
    auth = permission_required("manage_roles")(request)
    try: body = await request.json()
    except Exception: body = {}

    name = (body.get("name") or "").strip().upper()
    if not name:
        return error("Role name is required")

    if fetchone("SELECT id FROM roles WHERE UPPER(name) = %s", [name]):
        return error("A role with that name already exists", 409)

    permissions = body.get("permissions", [])
    r = execute_returning(
        "INSERT INTO roles (name, permissions, is_system) VALUES (%s, %s, FALSE) RETURNING *",
        [name, PgJson(permissions)]
    )
    r["id"] = str(r["id"])
    r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
    log_action("Created role", r["name"], r["id"], user_id=auth.user_id, ip=auth.ip)
    return created(r)


@roles_router.put("/{role_id}")
async def update_role(request: Request, role_id: str):
    auth = permission_required("manage_roles")(request)
    existing = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not existing: return not_found()

    try: body = await request.json()
    except Exception: body = {}

    new_name = existing["name"]
    if not existing["is_system"]:
        new_name = (body.get("name") or existing["name"]).strip().upper()

    r = execute_returning(
        "UPDATE roles SET name = %s, permissions = %s WHERE id = %s RETURNING *",
        [new_name, PgJson(body.get("permissions") if body.get("permissions") is not None else existing["permissions"]), role_id]
    )
    r["id"] = str(r["id"])
    r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
    log_action("Updated role", r["name"], role_id, user_id=auth.user_id, ip=auth.ip)
    return ok(r)


@roles_router.delete("/{role_id}")
async def delete_role(request: Request, role_id: str):
    auth = permission_required("manage_roles")(request)
    existing = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not existing: return not_found()
    if existing["is_system"]:
        return error("Cannot delete a system role", 403)
    if fetchone("SELECT id FROM users WHERE role_id = %s LIMIT 1", [role_id]):
        return error("Cannot delete a role that is assigned to users", 409)
    execute("DELETE FROM roles WHERE id = %s", [role_id])
    log_action("Deleted role", existing["name"], role_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()
