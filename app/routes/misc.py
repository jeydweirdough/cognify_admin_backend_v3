"""
Miscellaneous web routes:
  /api/web/admin/settings       → system settings CRUD
  /api/web/admin/logs           → activity logs viewer
  /api/web/admin/roles          → role & permissions management
  /api/web/admin/verification   → pending approvals queue (Modules & Subject Changes)
  /api/web/faculty/verification → faculty's own submission queue
  /api/web/admin/revisions      → revision management
"""
import json
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden, conflict
from app.utils.pagination import get_page_params, get_search
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

settings_router       = APIRouter(prefix="/api/web/admin/settings",       tags=["settings"])
admin_logs_router     = APIRouter(prefix="/api/web/admin/logs",           tags=["admin-logs"])
roles_router          = APIRouter(prefix="/api/web/admin/roles",          tags=["roles"])
admin_verify_router   = APIRouter(prefix="/api/web/admin/verification",   tags=["admin-verification"])
faculty_verify_router = APIRouter(prefix="/api/web/faculty/verification", tags=["faculty-verification"])
admin_rev_router      = APIRouter(prefix="/api/web/admin/revisions",      tags=["admin-revisions"])
faculty_rev_router    = APIRouter(prefix="/api/web/faculty/revisions",    tags=["faculty-revisions"])

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

@settings_router.get("")
async def get_settings(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    s = fetchone("SELECT * FROM system_settings WHERE id = 1")
    if s:
        s["id"] = str(s["id"])
    return ok(s or {})

@settings_router.put("")
async def update_settings(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
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
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
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
        sql += " AND (LOWER(al.action) LIKE LOWER(%s) OR LOWER(u.email) LIKE LOWER(%s))"
        params.extend([search, search])
        
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
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    roles = fetchall("SELECT * FROM roles ORDER BY name")
    for r in roles:
        r["id"] = str(r["id"])
        r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
    return ok(roles)


@roles_router.post("")
async def create_role(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
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
        [name, json.dumps(permissions)]
    )
    r["id"] = str(r["id"])
    r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
    log_action("Created role", r["name"], r["id"], user_id=auth.user_id, ip=auth.ip)
    return created(r)


@roles_router.put("/{role_id}")
async def update_role(request: Request, role_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    existing = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not existing: return not_found()

    try: body = await request.json()
    except Exception: body = {}

    # System roles: only permissions can be updated, not the name
    new_name = existing["name"]
    if not existing["is_system"]:
        new_name = (body.get("name") or existing["name"]).strip().upper()

    r = execute_returning(
        "UPDATE roles SET name = %s, permissions = %s WHERE id = %s RETURNING *",
        [new_name, json.dumps(body.get("permissions", existing["permissions"])), role_id]
    )
    r["id"] = str(r["id"])
    r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
    log_action("Updated role", r["name"], role_id, user_id=auth.user_id, ip=auth.ip)
    return ok(r)


@roles_router.delete("/{role_id}")
async def delete_role(request: Request, role_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    existing = fetchone("SELECT * FROM roles WHERE id = %s", [role_id])
    if not existing: return not_found()
    if existing["is_system"]:
        return error("Cannot delete a system role", 403)
    if fetchone("SELECT id FROM users WHERE role_id = %s LIMIT 1", [role_id]):
        return error("Cannot delete a role that is assigned to users", 409)
    execute("DELETE FROM roles WHERE id = %s", [role_id])
    log_action("Deleted role", existing["name"], role_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()

# ─────────────────────────────────────────────────────────────────────────────
# VERIFICATION QUEUE (Draft vs. Live Comparisons)
# ─────────────────────────────────────────────────────────────────────────────

def _get_verification_queue(user_id=None):
    """Fetches all PENDING items from the view_change_comparisons."""
    sql = "SELECT * FROM view_change_comparisons WHERE status = 'PENDING'"
    params = []
    
    if user_id:
        sql += " AND created_by = %s"
        params.append(user_id)
        
    sql += " ORDER BY created_at DESC"
    queue = fetchall(sql, params)
    
    for item in queue:
        for key in ["request_id", "entity_id", "created_by", "subject_id"]:
            if item.get(key): item[key] = str(item[key])
        if item.get("created_at"): item["created_at"] = item["created_at"].isoformat()

        # For assessments, enrich live_data with the current questions from the questions table
        if item.get("entity_module") == "ASSESSMENT" and item.get("entity_id"):
            questions = fetchall(
                """SELECT id, text, options, correct_answer
                   FROM questions
                   WHERE assessment_id = %s
                   ORDER BY date_created""",
                [item["entity_id"]]
            )
            normalized = []
            for q in questions:
                opts = q.get("options") or []
                if isinstance(opts, str):
                    import json as _j
                    opts = _j.loads(opts)
                normalized.append({
                    "id":            str(q["id"]),
                    "text":          q.get("text", ""),
                    "options":       opts,
                    "correctAnswer": q.get("correct_answer", 0),
                })
            live_data = item.get("live_data") or {}
            if isinstance(live_data, str):
                live_data = json.loads(live_data)
            live_data["questions"] = normalized
            item["live_data"] = live_data

    return queue

@admin_verify_router.get("")
async def admin_get_queue(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return ok(_get_verification_queue())

@faculty_verify_router.get("")
async def faculty_get_queue(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    return ok(_get_verification_queue(auth.user_id))

@admin_verify_router.post("/requests/{request_id}/approve")
async def approve_request_change(request: Request, request_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    
    req = fetchone("SELECT * FROM request_changes WHERE id = %s AND status = 'PENDING'", [request_id])
    if not req: return not_found("Pending request not found")
    
    changes = req["content"]
    action = changes.get("action")
    target_id = str(req["target_id"])
    
    # 1. Apply Subject Metadata Changes
    if req["type"] == "SUBJECT" and action == "UPDATE_METADATA":
        execute("""
            UPDATE subjects SET name = COALESCE(%s, name), description = COALESCE(%s, description),
            color = COALESCE(%s, color), weight = COALESCE(%s, weight), passing_rate = COALESCE(%s, passing_rate), status = 'APPROVED'
            WHERE id = %s
        """, [changes.get("name"), changes.get("description"), changes.get("color"), changes.get("weight"), changes.get("passingRate"), target_id])
    
    # 2. Apply Module Content Updates
    elif req["type"] == "MODULE" and action == "UPDATE_MODULE":
        execute("""
            UPDATE modules SET 
                title = COALESCE(%s, title), description = COALESCE(%s, description),
                content = COALESCE(%s, content), format = COALESCE(%s, format),
                file_url = COALESCE(%s, file_url), file_name = COALESCE(%s, file_name), status = 'APPROVED'
            WHERE id = %s
        """, [changes.get("title"), changes.get("description"), changes.get("content"), 
              changes.get("format"), changes.get("file_url"), changes.get("file_name"), target_id])
              
    # 3. Apply Assessment Updates
    elif req["type"] == "ASSESSMENT" and action in {"UPDATE_ASSESSMENT", "CREATE_ASSESSMENT"}:
        if action == "UPDATE_ASSESSMENT":
            execute("""
                UPDATE assessments SET
                    title = COALESCE(%s, title), type = COALESCE(%s, type),
                    subject_id = COALESCE(%s::uuid, subject_id),
                    module_id  = COALESCE(%s::uuid, module_id),
                    items = COALESCE(%s, items), status = 'APPROVED', updated_at = NOW()
                WHERE id = %s
            """, [changes.get("title"), changes.get("type"),
                  changes.get("subject_id"), changes.get("module_id"),
                  changes.get("items"), target_id])
            # Apply questions if they were staged
            if changes.get("questions"):
                from app.routes.assessments import _upsert_questions
                _upsert_questions(target_id, changes["questions"], str(req["created_by"]))
        else:
            # CREATE_ASSESSMENT: just approve the status
            execute("UPDATE assessments SET status = 'APPROVED', updated_at = NOW() WHERE id = %s", [target_id])

    # Deletions
    elif req["type"] == "MODULE" and action == "DELETE_MODULE":
        execute("DELETE FROM modules WHERE id = %s", [target_id])
        
    elif req["type"] == "SUBJECT" and action == "DELETE_SUBJECT":
        execute("DELETE FROM subjects WHERE id = %s", [target_id])

    elif req["type"] == "ASSESSMENT" and action == "DELETE_ASSESSMENT":
        execute("DELETE FROM assessments WHERE id = %s", [target_id])
    else:
        return error("Unsupported request type or action", 400)
    
    execute("UPDATE request_changes SET status = 'APPROVED' WHERE id = %s", [request_id])
    

@admin_verify_router.post("/requests/{request_id}/reject")
async def reject_request_change(request: Request, request_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try: body = await request.json()
    except Exception: body = {}
    note = (body.get("note") or body.get("notes") or "").strip()

    req = fetchone("SELECT revisions_list, target_id, type FROM request_changes WHERE id = %s", [request_id])
    if not req: return not_found("Request not found")

    rev_list = req.get("revisions_list") or []
    if isinstance(rev_list, str):
        rev_list = json.loads(rev_list)
    rev_list.append({"notes": note, "status": "REJECTED", "author_id": auth.user_id})

    execute(
        "UPDATE request_changes SET status = 'REJECTED', revisions_list = %s WHERE id = %s",
        [json.dumps(rev_list), request_id]
    )

    target_id   = str(req["target_id"])
    entity_type = req["type"]
    if entity_type == "ASSESSMENT":
        execute("UPDATE assessments SET status = 'REVISION_REQUESTED', updated_at = NOW() WHERE id = %s", [target_id])
    elif entity_type == "MODULE":
        execute("UPDATE modules SET status = 'REJECTED' WHERE id = %s", [target_id])
    elif entity_type == "SUBJECT":
        execute("UPDATE subjects SET status = 'REJECTED' WHERE id = %s", [target_id])

    log_action("Rejected change request", None, request_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"message": "Request rejected successfully"})

@faculty_rev_router.get("")
async def list_revisions(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    page, per_page = get_page_params(request)
    search = get_search(request)
    
    sql = """
        SELECT r.id, r.target_id, r.type, r.status, r.created_by,
		r.type,  r.content, r.revisions_list, r.status, r.created_at
        FROM request_changes r
        WHERE r.status = 'REJECTED' AND r.created_by = %s
    """
    params = [auth.user_id]
    if search:
        sql += " AND LOWER(r.category) LIKE LOWER(%s)"
        params.append(f"%{search}%")
        
    sql += " ORDER BY r.created_at DESC"
    result = paginate(sql, params, page, per_page)
    
    for r in result["items"]:
        r["id"] = str(r["id"])
        if r.get("target_id"): r["target_id"] = str(r["target_id"])
        if r.get("created_by"): r["created_by"] = str(r["created_by"])
        if r.get("created_at"): r["created_at"] = r["created_at"].isoformat()
        if r.get("revisions_list") is None: r["revisions_list"] = []
        
    return ok(result)

@faculty_rev_router.get("/{revision_id}")
async def get_revision(revision_id: str, request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()

    r = fetchone("""
         SELECT r.id, r.target_id, r.type, r.status, r.created_by,
		r.type,  r.content, r.revisions_list, r.status, r.created_at
        FROM request_changes r
        WHERE r.id = %s AND r.created_by = %s
    """, [revision_id, auth.user_id])

    if not r:
        return not_found("Revision not found")

    r["id"] = str(r["id"])
    if r.get("target_id"): r["target_id"] = str(r["target_id"])
    if r.get("created_by"): r["created_by"] = str(r["created_by"])
    if r.get("created_at"): r["created_at"] = r["created_at"].isoformat()
    if r.get("revisions_list") is None: r["revisions_list"] = []

    return ok(r)