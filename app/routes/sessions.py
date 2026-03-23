"""
Student study-session / to-do routes.

MOBILE (student):
  GET    /api/mobile/student/sessions          — list all sessions for the logged-in student
  POST   /api/mobile/student/sessions          — create a new session
  PATCH  /api/mobile/student/sessions/:id      — update a session (title, time, completed, etc.)
  DELETE /api/mobile/student/sessions/:id      — delete a session

All endpoints require the mobile_add_session permission (already in the STUDENT role).
"""

from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning
from app.middleware.auth import mobile_permission_required
from app.utils.responses import ok, created, no_content, error, not_found

mobile_sessions_router = APIRouter(
    prefix="/api/mobile/student/sessions",
    tags=["mobile-sessions"],
)


def _fmt_session(row: dict) -> dict:
    """Serialize a DB row into the JSON shape expected by the mobile app."""
    # Reconstruct the combined time string the mobile uses: "HH:MM - HH:MM"
    start = row.get("start_time") or ""
    end   = row.get("end_time")   or ""
    time_str = f"{start} - {end}" if start and end else (start or end or "")

    return {
        "id":        str(row["id"]),
        "title":     row["title"],
        "subject":   row.get("subject") or "",
        "date":      str(row["session_date"]),
        "time":      time_str,
        "startTime": start,
        "endTime":   end,
        "completed": bool(row.get("completed", False)),
        "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


# ─── GET /api/mobile/student/sessions ────────────────────────────────────────

@mobile_sessions_router.get("")
async def list_sessions(request: Request):
    """
    Return all study sessions for the logged-in student, newest first.
    """
    auth = mobile_permission_required("mobile_add_session")(request)

    rows = fetchall(
        """SELECT id, user_id, title, subject, session_date,
                  start_time, end_time, completed, created_at, updated_at
           FROM   student_sessions
           WHERE  user_id = %s
           ORDER  BY session_date DESC, created_at DESC""",
        [auth.user_id],
    )
    return ok([_fmt_session(r) for r in rows])


# ─── POST /api/mobile/student/sessions ───────────────────────────────────────

@mobile_sessions_router.post("")
async def create_session(request: Request):
    """
    Create a new study session.

    Body:
      {
        "title":         "Review Psych Notes",   // required
        "subject":       "Psychology",           // optional
        "date":          "2026-03-25",           // required, YYYY-MM-DD
        "startTime":     "09:00",               // optional
        "endTime":       "10:30",               // optional
        "completed":     false                  // optional, default false
      }
    """
    auth = mobile_permission_required("mobile_add_session")(request)

    try:
        body = await request.json()
    except Exception:
        body = {}

    title = (body.get("title") or "").strip()
    if not title:
        return error("title is required")

    date_str = (body.get("date") or "").strip()
    if not date_str:
        return error("date is required (YYYY-MM-DD)")

    # Validate date
    try:
        from datetime import date as _date
        _date.fromisoformat(date_str)
    except ValueError:
        return error("Invalid date format. Use YYYY-MM-DD.")

    subject    = (body.get("subject")   or "").strip() or None
    start_time = (body.get("startTime") or "").strip() or None
    end_time   = (body.get("endTime")   or "").strip() or None
    completed  = bool(body.get("completed", False))

    row = execute_returning(
        """INSERT INTO student_sessions
               (user_id, title, subject, session_date, start_time, end_time, completed)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id, user_id, title, subject, session_date,
                     start_time, end_time, completed, created_at, updated_at""",
        [auth.user_id, title, subject, date_str, start_time, end_time, completed],
    )
    return created(_fmt_session(row))


# ─── PATCH /api/mobile/student/sessions/:id ──────────────────────────────────

@mobile_sessions_router.patch("/{session_id}")
async def update_session(request: Request, session_id: str):
    """
    Partially update a session (title, subject, date, times, completed flag).
    Only the fields present in the request body are changed.
    """
    auth = mobile_permission_required("mobile_edit_session")(request)

    existing = fetchone(
        "SELECT * FROM student_sessions WHERE id = %s AND user_id = %s",
        [session_id, auth.user_id],
    )
    if not existing:
        return not_found("Session not found")

    try:
        body = await request.json()
    except Exception:
        body = {}

    # Apply patches — keep existing values when field is absent from body
    title      = (body.get("title") or existing["title"]).strip()
    subject    = body.get("subject",    existing.get("subject"))
    date_str   = body.get("date",       str(existing["session_date"]))
    start_time = body.get("startTime",  existing.get("start_time"))
    end_time   = body.get("endTime",    existing.get("end_time"))
    completed  = body.get("completed",  existing.get("completed", False))

    if not title:
        return error("title cannot be empty")

    try:
        from datetime import date as _date
        _date.fromisoformat(date_str)
    except ValueError:
        return error("Invalid date format. Use YYYY-MM-DD.")

    row = execute_returning(
        """UPDATE student_sessions
           SET title        = %s,
               subject      = %s,
               session_date = %s,
               start_time   = %s,
               end_time     = %s,
               completed    = %s,
               updated_at   = NOW()
           WHERE id = %s AND user_id = %s
           RETURNING id, user_id, title, subject, session_date,
                     start_time, end_time, completed, created_at, updated_at""",
        [title, subject, date_str, start_time, end_time, bool(completed),
         session_id, auth.user_id],
    )
    return ok(_fmt_session(row))


# ─── DELETE /api/mobile/student/sessions/:id ─────────────────────────────────

@mobile_sessions_router.delete("/{session_id}")
async def delete_session(request: Request, session_id: str):
    """
    Delete a study session owned by the logged-in student.
    """
    auth = mobile_permission_required("mobile_delete_session")(request)

    existing = fetchone(
        "SELECT id FROM student_sessions WHERE id = %s AND user_id = %s",
        [session_id, auth.user_id],
    )
    if not existing:
        return not_found("Session not found")

    execute(
        "DELETE FROM student_sessions WHERE id = %s AND user_id = %s",
        [session_id, auth.user_id],
    )
    return ok({"id": session_id, "deleted": True})