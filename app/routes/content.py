"""
Content module routes
  Admin:   /api/web/admin/content    — CRUD + approve/reject
  Faculty: /api/web/faculty/content  — CRUD (creates as DRAFT/PENDING)
  Mobile:  /api/mobile/student/content — read approved only + mark read
"""
import json
from fastapi import APIRouter, Request
from app.db import fetchone, execute, execute_returning, paginate
from app.middleware.auth import login_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

admin_content_router   = APIRouter(prefix="/api/web/admin/content",        tags=["admin-content"])
faculty_content_router = APIRouter(prefix="/api/web/faculty/content",      tags=["faculty-content"])
mobile_content_router  = APIRouter(prefix="/api/mobile/student/content",   tags=["mobile-content"])

VALID_STATUSES = {"DRAFT", "PENDING", "APPROVED", "REVISION_REQUESTED", "REJECTED", "REMOVAL_PENDING"}

_SELECT = """
    SELECT cm.*,
           s.name AS subject_name,
           t.title AS topic_title,
           u.first_name || ' ' || u.last_name AS author_name_resolved
    FROM content_modules cm
    LEFT JOIN subjects s ON s.id = cm.subject_id
    LEFT JOIN topics t   ON t.id = cm.topic_id
    LEFT JOIN users u    ON u.id = cm.author_id
"""

def _fmt(c: dict) -> dict:
    c["id"] = str(c["id"])
    if c.get("subject_id"): c["subject_id"] = str(c["subject_id"])
    if c.get("topic_id"):   c["topic_id"]   = str(c["topic_id"])
    if c.get("author_id"):  c["author_id"]  = str(c["author_id"])
    c["author_name"] = c.pop("author_name_resolved", None) or c.get("author_name")
    return c


def _list(request: Request, extra_where: str = "", extra_params: list = None):
    page, per_page = get_page_params(request)
    search = get_search(request)
    status = get_filter(request, "status", VALID_STATUSES)
    subject_id = (request.query_params.get("subject_id") or "").strip() or None

    sql    = [_SELECT, "WHERE 1=1"]
    params = []

    if extra_where:
        sql.append(extra_where)
        params += (extra_params or [])

    if search:
        sql.append("AND (LOWER(cm.title) LIKE LOWER(%s) OR LOWER(s.name) LIKE LOWER(%s))")
        params += [search, search]

    if status:
        sql.append("AND cm.status = %s")
        params.append(status)

    if subject_id:
        sql.append("AND cm.subject_id = %s")
        params.append(subject_id)

    sql.append("ORDER BY cm.last_updated DESC")
    result = paginate(" ".join(sql), params, page, per_page)
    result["items"] = [_fmt(c) for c in result["items"]]
    return result


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_content_router.get("")
async def admin_list(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return ok(_list(request))


@admin_content_router.get("/{content_id}")
async def admin_get(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    c = fetchone(_SELECT + "WHERE cm.id = %s", [content_id])
    return ok(_fmt(c)) if c else not_found()


@admin_content_router.post("")
async def admin_create(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _create(body, auth, auto_approve=True)


@admin_content_router.put("/{content_id}")
async def admin_update(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update(content_id, body, auth, can_approve=True)


@admin_content_router.patch("/{content_id}/status")
async def admin_update_status(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = (body.get("status") or "").upper()
    allowed_transitions = {"APPROVED", "REJECTED", "REVISION_REQUESTED"}
    if action not in allowed_transitions:
        return error(f"status must be one of: {', '.join(allowed_transitions)}")

    c = fetchone("SELECT id, title, revision_notes FROM content_modules WHERE id = %s", [content_id])
    if not c: return not_found()

    notes = c["revision_notes"] or []
    if action == "REVISION_REQUESTED" and body.get("note"):
        from datetime import datetime, timezone
        notes.append({"note": body["note"], "date": datetime.now(timezone.utc).isoformat(), "by": auth.user_id})

    execute(
        "UPDATE content_modules SET status = %s, revision_notes = %s WHERE id = %s",
        [action, json.dumps(notes), content_id],
    )
    log_action(f"Content {action.lower()}", c["title"], content_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"id": content_id, "status": action})


@admin_content_router.delete("/{content_id}")
async def admin_delete(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return _delete(content_id, auth, only_own=False)


# ═══════════════════════════════════════════════════════════════
# FACULTY
# ═══════════════════════════════════════════════════════════════

@faculty_content_router.get("")
async def faculty_list(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    return ok(_list(request, "AND (cm.author_id = %s OR cm.status = 'APPROVED')", [auth.user_id]))


@faculty_content_router.get("/{content_id}")
async def faculty_get(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    c = fetchone(_SELECT + "WHERE cm.id = %s AND (cm.author_id = %s OR cm.status = 'APPROVED')",
                 [content_id, auth.user_id])
    return ok(_fmt(c)) if c else not_found()


@faculty_content_router.post("")
async def faculty_create(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _create(body, auth, auto_approve=False)


@faculty_content_router.put("/{content_id}")
async def faculty_update(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    existing = fetchone("SELECT author_id FROM content_modules WHERE id = %s", [content_id])
    if not existing: return not_found()
    if str(existing["author_id"]) != auth.user_id:
        return forbidden("You can only edit your own content")
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update(content_id, body, auth, can_approve=False)


@faculty_content_router.patch("/{content_id}/submit")
async def faculty_submit(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    c = fetchone("SELECT id, title, author_id, submission_count FROM content_modules WHERE id = %s", [content_id])
    if not c: return not_found()
    if str(c["author_id"]) != auth.user_id: return forbidden()
    execute("UPDATE content_modules SET status = 'PENDING', submission_count = %s WHERE id = %s",
            [c["submission_count"] + 1, content_id])
    log_action("Submitted content for review", c["title"], content_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"id": content_id, "status": "PENDING"})


@faculty_content_router.patch("/{content_id}/request-removal")
async def faculty_request_removal(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    c = fetchone("SELECT id, title, author_id, status FROM content_modules WHERE id = %s", [content_id])
    if not c: return not_found()
    if str(c["author_id"]) != auth.user_id: return forbidden()
    execute("UPDATE content_modules SET status = 'REMOVAL_PENDING' WHERE id = %s", [content_id])
    log_action("Requested content removal", c["title"], content_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"id": content_id, "status": "REMOVAL_PENDING"})


@faculty_content_router.delete("/{content_id}")
async def faculty_delete(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    return _delete(content_id, auth, only_own=True)


# ═══════════════════════════════════════════════════════════════
# MOBILE
# ═══════════════════════════════════════════════════════════════

@mobile_content_router.get("")
async def mobile_list(request: Request):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    return ok(_list(request, "AND cm.status = 'APPROVED'"))


@mobile_content_router.get("/{content_id}")
async def mobile_get(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    c = fetchone(_SELECT + "WHERE cm.id = %s AND cm.status = 'APPROVED'", [content_id])
    if not c: return not_found()
    c = _fmt(c)
    progress = fetchone(
        "SELECT completed_at FROM student_progress WHERE student_id = %s AND content_id = %s",
        [auth.user_id, content_id],
    )
    c["completed"] = progress is not None
    c["completed_at"] = progress["completed_at"].isoformat() if progress else None
    return ok(c)


@mobile_content_router.post("/{content_id}/complete")
async def mobile_mark_complete(request: Request, content_id: str):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    if not fetchone("SELECT id FROM content_modules WHERE id = %s AND status = 'APPROVED'", [content_id]):
        return not_found()
    execute(
        """INSERT INTO student_progress (student_id, content_id)
           VALUES (%s, %s) ON CONFLICT DO NOTHING""",
        [auth.user_id, content_id],
    )
    return ok({"content_id": content_id, "completed": True})


# ── Shared create / update / delete ───────────────────────────────────────────

def _create(body: dict, auth, auto_approve: bool):
    missing = require_fields(body, ["title"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    status = "APPROVED" if auto_approve else (body.get("status") or "DRAFT").upper()
    u = fetchone("SELECT first_name, last_name FROM users WHERE id = %s", [auth.user_id])
    author_name = f"{u['first_name']} {u['last_name']}" if u else None

    c = execute_returning(
        """INSERT INTO content_modules
               (title, subject_id, topic_id, content, format, file_url, status,
                submission_count, author_id, author_name)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING *""",
        [
            clean_str(body["title"]),
            body.get("subject_id") or None,
            body.get("topic_id") or None,
            body.get("content"),
            (body.get("format") or "TEXT").upper(),
            body.get("file_url"),
            status, 0,
            auth.user_id,
            author_name,
        ],
    )
    log_action("Created content module", c["title"], str(c["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(_fmt(c))


def _update(content_id: str, body: dict, auth, can_approve: bool):
    existing = fetchone("SELECT * FROM content_modules WHERE id = %s", [content_id])
    if not existing: return not_found()

    new_status = (body.get("status") or existing["status"]).upper()
    if not can_approve and new_status == "APPROVED":
        new_status = "PENDING"

    c = execute_returning(
        """UPDATE content_modules
           SET title = %s, subject_id = %s, topic_id = %s, content = %s,
               format = %s, file_url = %s, status = %s, revision_notes = %s,
               submission_count = %s, last_updated = NOW()
           WHERE id = %s RETURNING *""",
        [
            clean_str(body.get("title", existing["title"])),
            body.get("subject_id", existing.get("subject_id")),
            body.get("topic_id",   existing.get("topic_id")),
            body.get("content",    existing.get("content")),
            (body.get("format",    existing["format"]) or "TEXT").upper(),
            body.get("file_url",   existing.get("file_url")),
            new_status,
            json.dumps(body.get("revision_notes", existing.get("revision_notes", []))),
            body.get("submission_count", existing["submission_count"]),
            content_id,
        ],
    )
    log_action("Updated content module", c["title"], content_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_fmt(c))


def _delete(content_id: str, auth, only_own: bool):
    c = fetchone("SELECT author_id, title, status FROM content_modules WHERE id = %s", [content_id])
    if not c: return not_found()
    if only_own and str(c["author_id"]) != auth.user_id:
        return forbidden("You can only delete your own content")
    if c["status"] == "APPROVED":
        return error("Cannot delete approved content. Submit a removal request instead.", 409)
    execute("DELETE FROM content_modules WHERE id = %s", [content_id])
    log_action("Deleted content module", c["title"], content_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()
