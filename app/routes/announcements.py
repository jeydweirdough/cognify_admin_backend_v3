"""
Announcements routes.

/api/web/admin/announcements  → full CRUD (admin only)
/api/web/announcements        → read-only for any logged-in web user
"""
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, permission_required
from app.utils.responses import ok, created, no_content, error, not_found
from app.utils.pagination import get_page_params, get_search
from app.utils.log import log_action

admin_announcements_router = APIRouter(
    prefix="/api/web/admin/announcements",
    tags=["announcements"],
)

public_announcements_router = APIRouter(
    prefix="/api/web/announcements",
    tags=["announcements-public"],
)


def _serialize(row: dict) -> dict:
    row["id"] = str(row["id"])
    if row.get("created_by"):
        row["created_by"] = str(row["created_by"])
    if row.get("created_at"):
        row["created_at"] = row["created_at"].isoformat()
    if row.get("updated_at"):
        row["updated_at"] = row["updated_at"].isoformat()
    if row.get("expires_at"):
        row["expires_at"] = row["expires_at"].isoformat()
    return row


# ─── Admin CRUD ───────────────────────────────────────────────────────────────

@admin_announcements_router.get("")
async def list_announcements(request: Request):
    auth = permission_required("view_announcements")(request)
    page, per_page = get_page_params(request)
    search = get_search(request)

    sql = """
        SELECT a.id, a.title, a.body, a.type, a.audience, a.is_active,
               a.tos_progress, a.expires_at, a.created_at, a.updated_at,
               u.first_name || ' ' || u.last_name AS created_by_name
        FROM announcements a
        LEFT JOIN users u ON u.id = a.created_by
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (LOWER(a.title) LIKE LOWER(%s) OR LOWER(a.body) LIKE LOWER(%s))"
        params.extend([f"%{search}%", f"%{search}%"])
    sql += " ORDER BY a.created_at DESC"
    result = paginate(sql, params, page, per_page)
    result["items"] = [_serialize(r) for r in result["items"]]
    return ok(result)


@admin_announcements_router.post("")
async def create_announcement(request: Request):
    auth = permission_required("create_announcements")(request)
    try:
        body = await request.json()
    except Exception:
        return error("Invalid JSON body")

    title = (body.get("title") or "").strip()
    content = (body.get("body") or "").strip()
    ann_type = body.get("type", "INFO")
    audience = body.get("audience", "ALL")
    is_active = bool(body.get("is_active", True))
    tos_progress = body.get("tos_progress")  # 0-100 or None
    expires_at = body.get("expires_at")  # ISO string or None

    if not title:
        return error("Title is required")
    if not content:
        return error("Body is required")
    if ann_type not in ("INFO", "WARNING", "SUCCESS", "TOS_PROGRESS"):
        return error("Invalid type")
    if audience not in ("ALL", "ADMIN", "FACULTY", "STUDENT"):
        return error("Invalid audience")

    row = execute_returning(
        """INSERT INTO announcements
               (title, body, type, audience, is_active, tos_progress, expires_at, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING *""",
        [title, content, ann_type, audience, is_active, tos_progress, expires_at, auth.user_id],
    )
    log_action("Created announcement", title, str(row["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(_serialize(row))


@admin_announcements_router.get("/{ann_id}")
async def get_announcement(ann_id: str, request: Request):
    auth = permission_required("view_announcements")(request)
    row = fetchone("SELECT * FROM announcements WHERE id = %s", [ann_id])
    if not row:
        return not_found("Announcement not found")
    return ok(_serialize(row))


@admin_announcements_router.put("/{ann_id}")
async def update_announcement(ann_id: str, request: Request):
    auth = permission_required("edit_announcements")(request)
    existing = fetchone("SELECT * FROM announcements WHERE id = %s", [ann_id])
    if not existing:
        return not_found("Announcement not found")

    try:
        body = await request.json()
    except Exception:
        return error("Invalid JSON body")

    title = (body.get("title") or existing["title"]).strip()
    content = (body.get("body") or existing["body"]).strip()
    ann_type = body.get("type", existing["type"])
    audience = body.get("audience", existing["audience"])
    is_active = bool(body.get("is_active", existing["is_active"]))
    tos_progress = body.get("tos_progress", existing.get("tos_progress"))
    expires_at = body.get("expires_at", existing.get("expires_at"))

    row = execute_returning(
        """UPDATE announcements
           SET title=%s, body=%s, type=%s, audience=%s, is_active=%s,
               tos_progress=%s, expires_at=%s, updated_at=NOW()
           WHERE id=%s RETURNING *""",
        [title, content, ann_type, audience, is_active, tos_progress, expires_at, ann_id],
    )
    log_action("Updated announcement", title, ann_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_serialize(row))


@admin_announcements_router.patch("/{ann_id}/toggle")
async def toggle_announcement(ann_id: str, request: Request):
    auth = permission_required("edit_announcements")(request)
    existing = fetchone("SELECT * FROM announcements WHERE id = %s", [ann_id])
    if not existing:
        return not_found("Announcement not found")

    row = execute_returning(
        "UPDATE announcements SET is_active = NOT is_active, updated_at=NOW() WHERE id=%s RETURNING *",
        [ann_id],
    )
    return ok(_serialize(row))


@admin_announcements_router.delete("/{ann_id}")
async def delete_announcement(ann_id: str, request: Request):
    auth = permission_required("delete_announcements")(request)
    existing = fetchone("SELECT title FROM announcements WHERE id = %s", [ann_id])
    if not existing:
        return not_found("Announcement not found")
    execute("DELETE FROM announcements WHERE id = %s", [ann_id])
    log_action("Deleted announcement", existing["title"], ann_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()


# ─── Public read (any logged-in web user) ────────────────────────────────────

@public_announcements_router.get("")
async def get_active_announcements(request: Request):
    auth = login_required(request)
    rows = fetchall(
        """SELECT a.id, a.title, a.body, a.type, a.audience, a.tos_progress,
                  a.expires_at, a.created_at,
                  CASE WHEN nr.id IS NOT NULL THEN TRUE ELSE FALSE END AS is_read
           FROM announcements a
           LEFT JOIN notification_reads nr
             ON nr.announcement_id = a.id AND nr.user_id = %s
           WHERE a.is_active = TRUE
             AND (a.expires_at IS NULL OR a.expires_at > NOW())
             AND (a.audience = 'ALL' OR a.audience = %s)
           ORDER BY a.created_at DESC
           LIMIT 20""",
        [auth.user_id, auth.role.upper()],
    )
    serialized = []
    for r in rows:
        s = _serialize(dict(r))
        s["read"] = bool(r["is_read"])
        serialized.append(s)
    return ok(serialized)

# ─── Mobile student notifications ────────────────────────────────────────────
# Students see:
#   1. Active announcements targeting ALL or STUDENT audience (from admin/faculty)
#   2. This endpoint is read-only — mobile students cannot create announcements

from app.middleware.auth import mobile_permission_required

mobile_notifications_router = APIRouter(
    prefix="/api/mobile/student/notifications",
    tags=["mobile-notifications"],
)


@public_announcements_router.patch("/{notif_id}/read")
async def web_mark_announcement_read(request: Request, notif_id: str):
    """Mark an announcement as read for the logged-in web user (admin/faculty)."""
    auth = login_required(request)
    execute(
        """INSERT INTO notification_reads (user_id, announcement_id)
           VALUES (%s, %s)
           ON CONFLICT (user_id, announcement_id) DO NOTHING""",
        [auth.user_id, notif_id],
    )
    return ok({"read": True})


@mobile_notifications_router.get("")
async def mobile_get_notifications(request: Request):
    """
    Return active announcements for the authenticated student.
    Filters to audience = 'ALL' or 'STUDENT', not expired, active only.
    Includes per-user read status via LEFT JOIN on notification_reads.
    Returns newest first, max 50.
    """
    auth = mobile_permission_required("mobile_login")(request)

    rows = fetchall(
        """SELECT a.id, a.title, a.body, a.type, a.tos_progress, a.created_at, a.expires_at,
                  CASE WHEN nr.id IS NOT NULL THEN TRUE ELSE FALSE END AS is_read
           FROM announcements a
           LEFT JOIN notification_reads nr
             ON nr.announcement_id = a.id AND nr.user_id = %s
           WHERE a.is_active = TRUE
             AND (a.expires_at IS NULL OR a.expires_at > NOW())
             AND a.audience IN ('ALL', 'STUDENT')
           ORDER BY a.created_at DESC
           LIMIT 50""",
        [auth.user_id],
    )

    items = []
    for r in rows:
        items.append({
            "id":           str(r["id"]),
            "title":        r["title"],
            "body":         r["body"],
            "type":         r["type"],
            "tos_progress": r["tos_progress"],
            "read":         bool(r["is_read"]),
            "created_at": r["created_at"].isoformat(),
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
        })

    return ok({"items": items, "total": len(items)})


@mobile_notifications_router.patch("/{notif_id}/read")
async def mobile_mark_read(request: Request, notif_id: str):
    """
    Mark a notification as read for this student.
    Stored in notification_reads table (per-user read tracking).
    """
    auth = mobile_permission_required("mobile_login")(request)
    # Upsert a read record — ignore if already exists
    execute(
        """INSERT INTO notification_reads (user_id, announcement_id)
           VALUES (%s, %s)
           ON CONFLICT (user_id, announcement_id) DO NOTHING""",
        [auth.user_id, notif_id],
    )
    return ok({"read": True})


@mobile_notifications_router.get("/unread-count")
async def mobile_unread_count(request: Request):
    """Return count of unread notifications for badge display."""
    auth = mobile_permission_required("mobile_login")(request)
    row = fetchone(
        """SELECT COUNT(*) AS c
           FROM announcements a
           WHERE a.is_active = TRUE
             AND (a.expires_at IS NULL OR a.expires_at > NOW())
             AND a.audience IN ('ALL', 'STUDENT')
             AND NOT EXISTS (
                 SELECT 1 FROM notification_reads nr
                 WHERE nr.user_id = %s AND nr.announcement_id = a.id
             )""",
        [auth.user_id],
    )
    return ok({"unread": int(row["c"] or 0) if row else 0})