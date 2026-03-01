"""
Subjects routes - Admin, Faculty, and Mobile (Student)
"""
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

admin_subjects_router   = APIRouter(prefix="/api/web/admin/subjects",         tags=["admin-subjects"])
faculty_subjects_router = APIRouter(prefix="/api/web/faculty/subjects",       tags=["faculty-subjects"])
mobile_subjects_router  = APIRouter(prefix="/api/mobile/student/subjects",    tags=["mobile-subjects"])


def _get_subject_tree(subject_id: str) -> dict | None:
    s = fetchone(
        """SELECT s.*, u.first_name || ' ' || u.last_name AS created_by_name
           FROM subjects s LEFT JOIN users u ON u.id = s.created_by
           WHERE s.id = %s""",
        [subject_id],
    )
    if not s:
        return None
    s["id"] = str(s["id"])
    s["modules"] = _build_module_tree(subject_id)
    return s


def _build_module_tree(subject_id: str, parent_id=None) -> list:
    rows = fetchall(
        """SELECT t.*, u.first_name || ' ' || u.last_name AS created_by_name
           FROM modules t LEFT JOIN users u ON u.id = t.created_by
           WHERE t.subject_id = %s AND t.parent_id IS NOT DISTINCT FROM %s
           ORDER BY t.sort_order, t.created_at""",
        [subject_id, parent_id],
    )
    result = []
    for r in rows:
        r["id"] = str(r["id"])
        r["subject_id"] = str(r["subject_id"])
        r["subModules"] = _build_module_tree(subject_id, r["id"])
        result.append(r)
    return result


def _list_subjects(request: Request, status_filter=None):
    page, per_page = get_page_params(request)
    search = get_search(request)
    sql    = ["SELECT s.*, u.first_name || ' ' || u.last_name AS created_by_name FROM subjects s LEFT JOIN users u ON u.id = s.created_by WHERE 1=1"]
    params = []
    if search:
        sql.append("AND (LOWER(s.name) LIKE LOWER(%s) OR LOWER(s.description) LIKE LOWER(%s))")
        params += [search, search]
    if status_filter:
        sql.append("AND s.status = %s")
        params.append(status_filter)
    sql.append("ORDER BY s.name")
    result = paginate(" ".join(sql), params, page, per_page)
    for s in result["items"]:
        s["id"] = str(s["id"])
        cnt = fetchone("SELECT COUNT(*) AS c FROM modules WHERE subject_id = %s", [s["id"]])
        s["module_count"] = cnt["c"] if cnt else 0
    return result


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_subjects_router.get("")
async def admin_list(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return ok(_list_subjects(request))


@admin_subjects_router.get("/pending-changes")
async def admin_pending_changes(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    rows = fetchall(
        """SELECT psc.*, s.name AS subject_name,
                  u.first_name || ' ' || u.last_name AS submitted_by_name
           FROM pending_subject_changes psc
           JOIN subjects s ON s.id = psc.subject_id
           JOIN users u ON u.id = psc.submitted_by
           WHERE psc.status = 'PENDING'
           ORDER BY psc.created_at DESC"""
    )
    for r in rows:
        r["id"] = str(r["id"])
        r["subject_id"] = str(r["subject_id"])
    return ok(rows)


@admin_subjects_router.get("/{subject_id}")
async def admin_get(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    s = _get_subject_tree(subject_id)
    return ok(s) if s else not_found()


@admin_subjects_router.post("")
async def admin_create(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    missing = require_fields(body, ["name"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")
    if fetchone("SELECT id FROM subjects WHERE LOWER(name) = LOWER(%s)", [body["name"]]):
        return error("Subject name already exists", 409)
    s = execute_returning(
        """INSERT INTO subjects (name, description, color, status, created_by)
           VALUES (%s, %s, %s, 'APPROVED', %s) RETURNING *""",
        [clean_str(body["name"]), clean_str(body.get("description")),
         body.get("color", "#6366f1"), auth.user_id],
    )
    log_action("Created subject", s["name"], str(s["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(_get_subject_tree(str(s["id"])))


@admin_subjects_router.put("/{subject_id}")
async def admin_update(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    s = fetchone("SELECT * FROM subjects WHERE id = %s", [subject_id])
    if not s: return not_found()
    try:
        body = await request.json()
    except Exception:
        body = {}
    updated = execute_returning(
        """UPDATE subjects SET name = %s, description = %s, color = %s
           WHERE id = %s RETURNING *""",
        [clean_str(body.get("name", s["name"])),
         clean_str(body.get("description", s.get("description"))),
         body.get("color", s["color"]), subject_id],
    )
    log_action("Updated subject", updated["name"], subject_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_get_subject_tree(subject_id))


@admin_subjects_router.delete("/{subject_id}")
async def admin_delete(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    s = fetchone("SELECT name FROM subjects WHERE id = %s", [subject_id])
    if not s: return not_found()
    execute("DELETE FROM subjects WHERE id = %s", [subject_id])
    log_action("Deleted subject", s["name"], subject_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()


@admin_subjects_router.patch("/{change_id}/approve-change")
async def admin_approve_change(request: Request, change_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = (body.get("action") or "").upper()
    if action not in ("APPROVE", "REJECT"):
        return error("action must be APPROVE or REJECT")

    change = fetchone("SELECT * FROM pending_subject_changes WHERE id = %s AND status = 'PENDING'", [change_id])
    if not change:
        return not_found("Pending change not found")

    if action == "APPROVE":
        data = change["change_data"]
        execute(
            "UPDATE subjects SET name = %s, description = %s, color = %s WHERE id = %s",
            [data.get("name"), data.get("description"), data.get("color"), change["subject_id"]],
        )
        if data.get("modules"):
            _save_module_tree(str(change["subject_id"]), data["modules"])

    execute(
        "UPDATE pending_subject_changes SET status = %s, reviewed_by = %s, review_note = %s, reviewed_at = NOW() WHERE id = %s",
        [action, auth.user_id, body.get("note"), change_id],
    )
    log_action(f"Subject change {action.lower()}d", None, change_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"action": action})


@admin_subjects_router.post("/{subject_id}/modules")
async def admin_add_module(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _add_module(subject_id, body, auth, auto_approve=True)


@admin_subjects_router.put("/{subject_id}/modules/{module_id}")
async def admin_update_module(request: Request, subject_id: str, module_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update_module(module_id, body, auth, auto_approve=True)


@admin_subjects_router.delete("/{subject_id}/modules/{module_id}")
async def admin_delete_module(request: Request, subject_id: str, module_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    execute("DELETE FROM modules WHERE id = %s AND subject_id = %s", [module_id, subject_id])
    return no_content()


# ═══════════════════════════════════════════════════════════════
# FACULTY
# ═══════════════════════════════════════════════════════════════

@faculty_subjects_router.get("")
async def faculty_list(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    return ok(_list_subjects(request, status_filter="APPROVED"))


@faculty_subjects_router.get("/{subject_id}")
async def faculty_get(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    s = _get_subject_tree(subject_id)
    return ok(s) if s else not_found()


@faculty_subjects_router.post("/{subject_id}/modules")
async def faculty_add_module(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _add_module(subject_id, body, auth, auto_approve=False)


@faculty_subjects_router.put("/{subject_id}/modules/{module_id}")
async def faculty_update_module(request: Request, subject_id: str, module_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update_module(module_id, body, auth, auto_approve=False)


@faculty_subjects_router.post("/{subject_id}/submit-change")
async def faculty_submit_change(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    if not fetchone("SELECT id FROM subjects WHERE id = %s", [subject_id]):
        return not_found()
    try:
        body = await request.json()
    except Exception:
        body = {}
    change = execute_returning(
        "INSERT INTO pending_subject_changes (subject_id, change_data, submitted_by) VALUES (%s, %s, %s) RETURNING id",
        [subject_id, body, auth.user_id],
    )
    log_action("Submitted subject change for review", None, subject_id, user_id=auth.user_id, ip=auth.ip)
    return created({"change_id": str(change["id"])})


# ═══════════════════════════════════════════════════════════════
# MOBILE — read-only
# ═══════════════════════════════════════════════════════════════

@mobile_subjects_router.get("")
async def mobile_list(request: Request):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    return ok(_list_subjects(request, status_filter="APPROVED"))


@mobile_subjects_router.get("/{subject_id}")
async def mobile_get(request: Request, subject_id: str):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    s = _get_subject_tree(subject_id)
    return ok(s) if s else not_found()


# ── Shared topic helpers ───────────────────────────────────────────────────────

def _add_module(subject_id: str, body: dict, auth, auto_approve: bool):
    if not fetchone("SELECT id FROM subjects WHERE id = %s", [subject_id]):
        return not_found("Subject not found")
    missing = require_fields(body, ["title"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    status = "APPROVED" if auto_approve else "PENDING"
    topic = execute_returning(
        """INSERT INTO modules (subject_id, parent_id, title, description, content, sort_order, status, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        [subject_id, body.get("parent_id"), clean_str(body["title"]),
         clean_str(body.get("description")), body.get("content"),
         body.get("sort_order", 0), status, auth.user_id],
    )
    topic["id"] = str(topic["id"])
    topic["subModules"] = []
    log_action("Added module", topic["title"], str(topic["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(topic)


def _update_module(module_id: str, body: dict, auth, auto_approve: bool):
    existing = fetchone("SELECT * FROM modules WHERE id = %s", [module_id])
    if not existing:
        return not_found("Module not found")
    status = existing["status"]
    if not auto_approve and status == "APPROVED":
        status = "PENDING"

    updated = execute_returning(
        """UPDATE modules SET title = %s, description = %s, content = %s,
                            sort_order = %s, status = %s
           WHERE id = %s RETURNING *""",
        [clean_str(body.get("title", existing["title"])),
         clean_str(body.get("description", existing.get("description"))),
         body.get("content", existing.get("content")),
         body.get("sort_order", existing["sort_order"]),
         status, module_id],
    )
    updated["id"] = str(updated["id"])
    updated["subModules"] = _build_module_tree(str(updated["subject_id"]), updated["id"])
    return ok(updated)


def _save_module_tree(subject_id: str, modules: list, parent_id=None):
    for t in modules:
        existing = fetchone("SELECT id FROM modules WHERE id = %s", [t.get("id")]) if t.get("id") else None
        if existing:
            execute(
                "UPDATE modules SET title = %s, description = %s, content = %s, status = 'APPROVED' WHERE id = %s",
                [t.get("title"), t.get("description"), t.get("content"), t["id"]],
            )
        else:
            new_topic = execute_returning(
                "INSERT INTO modules (subject_id, parent_id, title, description, content, status) VALUES (%s, %s, %s, %s, %s, 'APPROVED') RETURNING id",
                [subject_id, parent_id, t.get("title"), t.get("description"), t.get("content")],
            )
            t["id"] = str(new_topic["id"])
        if t.get("subModules"):
            _save_module_tree(subject_id, t["subModules"], t["id"])