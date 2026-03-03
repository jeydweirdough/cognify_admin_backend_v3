"""
Subjects routes - Admin, Faculty, and Mobile (Student)
"""
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, permission_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action
import json
from psycopg2.extras import Json as PgJson

admin_subjects_router   = APIRouter(prefix="/api/web/admin/subjects",         tags=["admin-subjects"])
faculty_subjects_router = APIRouter(prefix="/api/web/faculty/subjects",       tags=["faculty-subjects"])
mobile_subjects_router  = APIRouter(prefix="/api/mobile/student/subjects",    tags=["mobile-subjects"])

# ─────────────────────────────────────────────────────────────────────────────
# CORE HELPERS & CONDITIONAL ACCESS LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def _format_module(m: dict) -> dict:
    m["id"] = str(m["id"])
    m["subject_id"] = str(m["subject_id"])
    if m.get("parent_id"): 
        m["parent_id"] = str(m["parent_id"])
    m["fileUrl"] = m.pop("file_url", None)
    m["fileName"] = m.pop("file_name", None)
    
    if m.get("format") == "PDF":
        m["fileData"] = m.pop("content", None)
    else:
        m["fileData"] = None
        
    return m

def _build_module_tree(subject_id: str, parent_id=None, role: str = "ADMIN", user_id: str = None) -> list:
    """Recursively builds the curriculum tree based on strict role conditionals."""
    sql = """SELECT t.*, u.first_name || ' ' || u.last_name AS created_by_name
             FROM modules t LEFT JOIN users u ON u.id = t.created_by
             WHERE t.subject_id = %s AND t.parent_id IS NOT DISTINCT FROM %s"""
    params = [subject_id, parent_id]

    # Rule: Faculty see APPROVED + their own PENDING content
    if role == "FACULTY":
        sql += " AND (t.status = 'APPROVED' OR t.created_by = %s)"
        params.append(user_id)
    # Rule: Students ONLY see APPROVED content
    elif role == "STUDENT":
        sql += " AND t.status = 'APPROVED'"
    # Admin sees everything.

    sql += " ORDER BY t.sort_order, t.created_at"
    
    rows = fetchall(sql, params)
    result = []
    for r in rows:
        r = _format_module(r)
        r["subTopics"] = _build_module_tree(subject_id, r["id"], role, user_id)
        result.append(r)
    return result

def _get_subject_tree(subject_id: str, role: str = "ADMIN", user_id: str = None) -> dict | None:
    s = fetchone(
        """SELECT s.*, u.first_name || ' ' || u.last_name AS created_by_name
           FROM subjects s LEFT JOIN users u ON u.id = s.created_by
           WHERE s.id = %s""",
        [subject_id],
    )
    if not s: return None
    
    # Rule: Faculty and Students can only view the tree if the subject is APPROVED
    if role in ["FACULTY", "STUDENT"] and s["status"] != "APPROVED":
        return None
    
    s["id"] = str(s["id"])
    s["passingRate"] = s.pop("passing_rate", 75)
    s["topics"] = _build_module_tree(subject_id, None, role, user_id)
    return s

def _list_subjects(request: Request, role: str):
    page, per_page = get_page_params(request)
    search = get_search(request)
    sql    = ["SELECT s.*, u.first_name || ' ' || u.last_name AS created_by_name FROM subjects s LEFT JOIN users u ON u.id = s.created_by WHERE 1=1"]
    params = []
    
    # Rule: Non-admins only see live, approved subjects
    if role in ["FACULTY", "STUDENT"]:
        sql.append("AND s.status = 'APPROVED'")
        
    if search:
        sql.append("AND (LOWER(s.name) LIKE LOWER(%s) OR LOWER(s.description) LIKE LOWER(%s))")
        params += [search, search]
        
    sql.append("ORDER BY s.name")
    result = paginate(" ".join(sql), params, page, per_page)
    
    for s in result["items"]:
        s["id"] = str(s["id"])
        s["passingRate"] = s.pop("passing_rate", 75)
        
        # Count modules conditionally as well
        if role == "ADMIN":
            cnt = fetchone("SELECT COUNT(*) AS c FROM modules WHERE subject_id = %s", [s["id"]])
        else:
            cnt = fetchone("SELECT COUNT(*) AS c FROM modules WHERE subject_id = %s AND status = 'APPROVED'", [s["id"]])
        
        s["module_count"] = cnt["c"] if cnt else 0
        
    return result


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN ROUTES (Full Access)
# ─────────────────────────────────────────────────────────────────────────────

@admin_subjects_router.get("")
async def admin_list(request: Request):
    auth = permission_required("view_subjects")(request)
    return ok(_list_subjects(request, "ADMIN"))

@admin_subjects_router.get("/{subject_id}")
async def admin_get(request: Request, subject_id: str):
    auth = permission_required("view_subjects")(request)
    s = _get_subject_tree(subject_id, "ADMIN", auth.user_id)
    return ok(s) if s else not_found()

@admin_subjects_router.post("")
async def admin_create(request: Request):
    auth = permission_required("create_subjects")(request)
    try: body = await request.json()
    except Exception: body = {}
    
    s = execute_returning(
        """INSERT INTO subjects (name, description, color, weight, passing_rate, status, created_by)
           VALUES (%s, %s, %s, %s, %s, 'APPROVED', %s) RETURNING *""",
        [clean_str(body["name"]), clean_str(body.get("description")), body.get("color", "#6366f1"), 
         int(body.get("weight", 0)), int(body.get("passingRate", 75)), auth.user_id],
    )
    log_action("Created subject", s["name"], str(s["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(_get_subject_tree(str(s["id"]), "ADMIN"))

@admin_subjects_router.put("/{subject_id}")
async def admin_update(request: Request, subject_id: str):
    auth = permission_required("edit_subjects")(request)
    s = fetchone("SELECT * FROM subjects WHERE id = %s", [subject_id])
    if not s: return not_found()
    try: body = await request.json()
    except Exception: body = {}
    
    updated = execute_returning(
        """UPDATE subjects SET name = %s, description = %s, color = %s, weight = %s, passing_rate = %s
           WHERE id = %s RETURNING *""",
        [clean_str(body.get("name", s["name"])), clean_str(body.get("description", s.get("description"))),
         body.get("color", s["color"]), int(body.get("weight", s.get("weight", 0))), 
         int(body.get("passingRate", s.get("passing_rate", 75))), subject_id],
    )
    log_action("Updated subject", updated["name"], subject_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_get_subject_tree(subject_id, "ADMIN"))

@admin_subjects_router.delete("/{subject_id}")
async def admin_delete(request: Request, subject_id: str):
    auth = permission_required("delete_subjects")(request)
    s = fetchone("SELECT name FROM subjects WHERE id = %s", [subject_id])
    if not s: return not_found()
    execute("DELETE FROM subjects WHERE id = %s", [subject_id])
    log_action("Deleted subject", s["name"], subject_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()

@admin_subjects_router.post("/{subject_id}/modules")
async def admin_add_module(request: Request, subject_id: str):
    auth = permission_required("create_content")(request)
    try: body = await request.json()
    except Exception: body = {}
    return _add_module(subject_id, body, auth, auto_approve=True)

@admin_subjects_router.put("/{subject_id}/modules/{module_id}")
async def admin_update_module(request: Request, subject_id: str, module_id: str):
    auth = permission_required("edit_content")(request)
    try: body = await request.json()
    except Exception: body = {}
    return _update_module(module_id, body, auth, auto_approve=True)

@admin_subjects_router.delete("/{subject_id}/modules/{module_id}")
async def admin_delete_module(request: Request, subject_id: str, module_id: str):
    auth = permission_required("delete_content")(request)
    execute("DELETE FROM modules WHERE id = %s AND subject_id = %s", [module_id, subject_id])
    return no_content()

# ─────────────────────────────────────────────────────────────────────────────
# FACULTY ROUTES (Conditional Access)
# ─────────────────────────────────────────────────────────────────────────────

@faculty_subjects_router.get("")
async def faculty_list(request: Request):
    auth = permission_required("view_subjects")(request)
    return ok(_list_subjects(request, "FACULTY"))

@faculty_subjects_router.get("/{subject_id}")
async def faculty_get(request: Request, subject_id: str):
    auth = permission_required("view_subjects")(request)
    s = _get_subject_tree(subject_id, "FACULTY", auth.user_id)
    return ok(s) if s else not_found()

@faculty_subjects_router.post("/{subject_id}/modules")
async def faculty_add_module(request: Request, subject_id: str):
    auth = permission_required("create_content")(request)
    try: body = await request.json()
    except Exception: body = {}
    return _add_module(subject_id, body, auth, auto_approve=False)

@faculty_subjects_router.put("/{subject_id}/modules/{module_id}")
async def faculty_update_module(request: Request, subject_id: str, module_id: str):
    auth = permission_required("edit_content")(request)
    try: body = await request.json()
    except Exception: body = {}
    return _update_module(module_id, body, auth, auto_approve=False)

@faculty_subjects_router.post("/{subject_id}/submit-change")
async def faculty_submit_change(request: Request, subject_id: str):
    auth = permission_required("edit_subjects")(request)
    if not fetchone("SELECT id FROM subjects WHERE id = %s", [subject_id]):
        return not_found()
    try: body = await request.json()
    except Exception: body = {}
    
    change = execute_returning(
        "INSERT INTO request_changes (target_id, created_by, type, content) VALUES (%s, %s, 'SUBJECT', %s) RETURNING id",
        [subject_id, auth.user_id, body]
    )
    log_action("Submitted subject change for review", None, subject_id, user_id=auth.user_id, ip=auth.ip)
    return created({"change_id": str(change["id"])})

# ─────────────────────────────────────────────────────────────────────────────
# SHARED TOPIC WRITE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _add_module(subject_id: str, body: dict, auth, auto_approve: bool):
    if not fetchone("SELECT id FROM subjects WHERE id = %s", [subject_id]):
        return not_found("Subject not found")
    if require_fields(body, ["title"]): return error("Missing title")

    status = "APPROVED" if auto_approve else "PENDING"
    content_payload = body.get("fileData") if body.get("format") == "PDF" else body.get("content")

    topic = execute_returning(
        """INSERT INTO modules (subject_id, parent_id, title, description, content, format, file_url, file_name, sort_order, status, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        [subject_id, body.get("parent_id"), clean_str(body["title"]), clean_str(body.get("description")), 
         content_payload, body.get("format", "TEXT"), body.get("fileUrl"), body.get("fileName"),
         body.get("sort_order", 0), status, auth.user_id],
    )
    log_action("Added module", topic["title"], str(topic["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(_format_module(topic))

def _update_module(module_id: str, body: dict, auth, auto_approve: bool):
    existing = fetchone("SELECT * FROM modules WHERE id = %s", [module_id])
    if not existing: return not_found("Module not found")
    
    content_payload = body.get("fileData") if body.get("format") == "PDF" else body.get("content", existing.get("content"))

    if not auto_approve:
        # FACULTY MODE: Intercept the update and push to staging table (request_changes)
        payload = {
            "action": "UPDATE_MODULE",
            "title": clean_str(body.get("title", existing["title"])),
            "description": clean_str(body.get("description", existing.get("description"))),
            "content": content_payload,
            "format": body.get("format", existing.get("format", "TEXT")),
            "file_url": body.get("fileUrl", existing.get("file_url")),
            "file_name": body.get("fileName", existing.get("file_name")),
            "sort_order": body.get("sort_order", existing["sort_order"])
        }
        
        execute(
            "INSERT INTO request_changes (target_id, created_by, type, content, status) VALUES (%s, %s, 'MODULE', %s, 'PENDING')",
            [module_id, auth.user_id, PgJson(payload)]
        )
        log_action("Submitted module edit for review", payload["title"], module_id, user_id=auth.user_id, ip=auth.ip)
        
        # Return the existing module so the UI doesn't crash, but flag it as pending review
        formatted = _format_module(existing)
        formatted["status"] = "PENDING_UPDATE"
        return ok(formatted)

    # ADMIN MODE: Auto-approve and write directly to live modules table
    updated = execute_returning(
        """UPDATE modules SET title = %s, description = %s, content = %s,
                              format = %s, file_url = %s, file_name = %s,
                              sort_order = %s, status = 'APPROVED'
           WHERE id = %s RETURNING *""",
        [clean_str(body.get("title", existing["title"])), clean_str(body.get("description", existing.get("description"))),
         content_payload, body.get("format", existing.get("format", "TEXT")), body.get("fileUrl", existing.get("file_url")),
         body.get("fileName", existing.get("file_name")), body.get("sort_order", existing["sort_order"]), module_id],
    )
    
    formatted = _format_module(updated)
    formatted["subTopics"] = _build_module_tree(str(updated["subject_id"]), formatted["id"], "ADMIN", auth.user_id)

# ─── Module lookup by ID (used by RevisionDetail to resolve subject) ──────────

@faculty_subjects_router.get("/modules/{module_id}/resolve")
async def resolve_module_subject_faculty(request: Request, module_id: str):
    auth = permission_required("view_subjects")(request)
    m = fetchone("SELECT id, subject_id, title FROM modules WHERE id = %s", [module_id])
    if not m: return not_found("Module not found")
    return ok({"module_id": str(m["id"]), "subject_id": str(m["subject_id"]), "title": m["title"]})

@admin_subjects_router.get("/modules/{module_id}/resolve")
async def resolve_module_subject_admin(request: Request, module_id: str):
    auth = permission_required("view_subjects")(request)
    m = fetchone("SELECT id, subject_id, title FROM modules WHERE id = %s", [module_id])
    if not m: return not_found("Module not found")
    return ok({"module_id": str(m["id"]), "subject_id": str(m["subject_id"]), "title": m["title"]})