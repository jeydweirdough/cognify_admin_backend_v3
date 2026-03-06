"""
Student mood tracking routes.

MOBILE (student):
  GET    /api/mobile/student/moods          — get all moods for the logged-in student
  PUT    /api/mobile/student/moods/:date    — upsert mood for a specific date (YYYY-MM-DD)
  DELETE /api/mobile/student/moods/:date    — delete mood for a specific date

WEB (admin / faculty):
  GET    /api/web/admin/analytics/:student_id/moods    — mood history for one student
  GET    /api/web/faculty/analytics/:student_id/moods  — same, faculty-scoped
  GET    /api/web/admin/analytics/moods/summary        — cohort-level mood distribution

Valid mood_key values (from mobile/constants/moods.ts — Inside Out 2):
  joy | sad | anger | disgust | fear | anxiety | envy | ennui | embarrassment
"""

from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning
from app.middleware.auth import permission_required, mobile_permission_required
from app.utils.responses import ok, error, not_found

# ── Routers ───────────────────────────────────────────────────────────────────

mobile_moods_router  = APIRouter(prefix="/api/mobile/student/moods",      tags=["mobile-moods"])
admin_moods_router   = APIRouter(prefix="/api/web/admin/analytics",        tags=["admin-moods"])
faculty_moods_router = APIRouter(prefix="/api/web/faculty/analytics",      tags=["faculty-moods"])

# ── Valid mood keys — must match MoodKey in mobile/constants/moods.ts ────────

VALID_MOOD_KEYS = {
    "joy", "sad", "anger", "disgust", "fear",
    "anxiety", "envy", "ennui", "embarrassment",
}

MOOD_LABELS = {
    "joy":          "Joy",
    "sad":          "Sad",
    "anger":        "Anger",
    "disgust":      "Disgust",
    "fear":         "Fear",
    "anxiety":      "Anxiety",
    "envy":         "Envy",
    "ennui":        "Ennui",
    "embarrassment": "Embarrassment",
}

MOOD_COLORS = {
    "joy":          "#FCD34D",
    "sad":          "#60A5FA",
    "anger":        "#F87171",
    "disgust":      "#86EFAC",
    "fear":         "#C084FC",
    "anxiety":      "#FB923C",
    "envy":         "#2DD4BF",
    "ennui":        "#818CF8",
    "embarrassment": "#F9A8D4",
}


def _fmt_mood(row: dict) -> dict:
    return {
        "id":        str(row["id"]),
        "date":      str(row["mood_date"]),
        "mood_key":  row["mood_key"],
        "label":     MOOD_LABELS.get(row["mood_key"], row["mood_key"].title()),
        "color":     MOOD_COLORS.get(row["mood_key"], "#94A3B8"),
        "source":    row.get("source", "home"),
        "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


# ═══════════════════════════════════════════════════════════════
# MOBILE — student reads / writes their own moods
# ═══════════════════════════════════════════════════════════════

@mobile_moods_router.get("")
async def mobile_get_moods(request: Request):
    """
    Return all mood entries for the logged-in student as a flat list.
    The mobile app converts this to a { 'YYYY-MM-DD': mood_key } map.

    Permission: mobile_view_home (moods are shown on the Home tab)
    """
    auth = mobile_permission_required("mobile_view_home")(request)
    rows = fetchall(
        """SELECT id, user_id, mood_date, mood_key, source, created_at, updated_at
           FROM student_moods
           WHERE user_id = %s
           ORDER BY mood_date DESC""",
        [auth.user_id],
    )
    return ok([_fmt_mood(r) for r in rows])


@mobile_moods_router.put("/{mood_date}")
async def mobile_upsert_mood(request: Request, mood_date: str):
    """
    Save or update a mood for a specific date (YYYY-MM-DD).
    Uses upsert so calling it again on the same date updates the mood.

    Body: { "mood_key": "joy", "source": "home" | "calendar" }

    Permission:
      - home source   → mobile_save_mood
      - calendar source → mobile_save_calendar_mood
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    mood_key = (body.get("mood_key") or "").lower().strip()
    source   = (body.get("source") or "home").lower().strip()

    if mood_key not in VALID_MOOD_KEYS:
        return error(f"Invalid mood_key. Must be one of: {', '.join(sorted(VALID_MOOD_KEYS))}")
    if source not in ("home", "calendar"):
        source = "home"

    # Gate by the appropriate permission based on source
    perm = "mobile_save_calendar_mood" if source == "calendar" else "mobile_save_mood"
    auth = mobile_permission_required(perm)(request)

    # Validate date format
    try:
        from datetime import date as _date
        _date.fromisoformat(mood_date)
    except ValueError:
        return error("Invalid date format. Use YYYY-MM-DD.")

    row = execute_returning(
        """INSERT INTO student_moods (user_id, mood_date, mood_key, source, updated_at)
           VALUES (%s, %s, %s, %s, NOW())
           ON CONFLICT (user_id, mood_date)
           DO UPDATE SET mood_key = EXCLUDED.mood_key,
                         source   = EXCLUDED.source,
                         updated_at = NOW()
           RETURNING id, user_id, mood_date, mood_key, source, created_at, updated_at""",
        [auth.user_id, mood_date, mood_key, source],
    )
    return ok(_fmt_mood(row))


@mobile_moods_router.delete("/{mood_date}")
async def mobile_delete_mood(request: Request, mood_date: str):
    """
    Delete the mood entry for a specific date.

    Permission: mobile_delete_mood
    """
    auth = mobile_permission_required("mobile_delete_mood")(request)

    existing = fetchone(
        "SELECT id FROM student_moods WHERE user_id = %s AND mood_date = %s",
        [auth.user_id, mood_date],
    )
    if not existing:
        return not_found("No mood entry found for this date")

    execute(
        "DELETE FROM student_moods WHERE user_id = %s AND mood_date = %s",
        [auth.user_id, mood_date],
    )
    return ok({"date": mood_date, "deleted": True})


# ═══════════════════════════════════════════════════════════════
# ADMIN / FACULTY — read student mood analytics
# ═══════════════════════════════════════════════════════════════

def _student_mood_data(student_id: str) -> dict:
    """
    Returns mood history + frequency breakdown for one student.
    Used by both admin and faculty analytics endpoints.
    """
    history = fetchall(
        """SELECT id, mood_date, mood_key, source, created_at, updated_at
           FROM student_moods
           WHERE user_id = %s
           ORDER BY mood_date DESC
           LIMIT 60""",
        [student_id],
    )

    # Frequency count per mood_key
    freq_rows = fetchall(
        """SELECT mood_key, COUNT(*) AS count
           FROM student_moods
           WHERE user_id = %s
           GROUP BY mood_key
           ORDER BY count DESC""",
        [student_id],
    )
    total = sum(int(r["count"]) for r in freq_rows)
    frequency = [
        {
            "mood_key":   r["mood_key"],
            "label":      MOOD_LABELS.get(r["mood_key"], r["mood_key"].title()),
            "color":      MOOD_COLORS.get(r["mood_key"], "#94A3B8"),
            "count":      int(r["count"]),
            "percentage": round(int(r["count"]) / total * 100, 1) if total else 0,
        }
        for r in freq_rows
    ]

    # Most common mood overall
    dominant = frequency[0] if frequency else None

    # Last 7 days streak — what mood appeared most in the past week
    recent_7 = fetchall(
        """SELECT mood_key, COUNT(*) AS c
           FROM student_moods
           WHERE user_id = %s AND mood_date >= CURRENT_DATE - INTERVAL '7 days'
           GROUP BY mood_key ORDER BY c DESC LIMIT 1""",
        [student_id],
    )
    recent_mood = recent_7[0]["mood_key"] if recent_7 else None

    return {
        "history":     [_fmt_mood(r) for r in history],
        "frequency":   frequency,
        "dominantMood": dominant,
        "recentMood":  {
            "mood_key": recent_mood,
            "label":    MOOD_LABELS.get(recent_mood, "") if recent_mood else None,
            "color":    MOOD_COLORS.get(recent_mood, "#94A3B8") if recent_mood else None,
        },
        "totalEntries": total,
    }


@admin_moods_router.get("/{student_id}/moods")
async def admin_student_moods(request: Request, student_id: str):
    """Mood history and frequency for one student (admin)."""
    auth = permission_required("view_student_analytics")(request)
    student = fetchone(
        "SELECT id FROM users WHERE id = %s",
        [student_id],
    )
    if not student:
        return not_found("Student not found")
    return ok(_student_mood_data(student_id))


@faculty_moods_router.get("/{student_id}/moods")
async def faculty_student_moods(request: Request, student_id: str):
    """Mood history and frequency for one student (faculty)."""
    auth = permission_required("view_student_analytics")(request)
    student = fetchone(
        "SELECT id FROM users WHERE id = %s",
        [student_id],
    )
    if not student:
        return not_found("Student not found")
    return ok(_student_mood_data(student_id))


@admin_moods_router.get("/moods/summary")
async def admin_mood_summary(request: Request):
    """
    Cohort-level mood distribution across all students.
    Returns frequency of each mood across the entire student body
    for the last 30 days.
    """
    auth = permission_required("view_analytics")(request)

    rows = fetchall(
        """SELECT sm.mood_key, COUNT(*) AS count
           FROM student_moods sm
           JOIN users u ON u.id = sm.user_id
           JOIN roles r ON r.id = u.role_id
           WHERE r.name = 'STUDENT'
             AND sm.mood_date >= CURRENT_DATE - INTERVAL '30 days'
           GROUP BY sm.mood_key
           ORDER BY count DESC""",
        [],
    )
    total = sum(int(r["count"]) for r in rows)
    distribution = [
        {
            "mood_key":   r["mood_key"],
            "label":      MOOD_LABELS.get(r["mood_key"], r["mood_key"].title()),
            "color":      MOOD_COLORS.get(r["mood_key"], "#94A3B8"),
            "count":      int(r["count"]),
            "percentage": round(int(r["count"]) / total * 100, 1) if total else 0,
        }
        for r in rows
    ]

    # Trend: daily dominant mood for last 14 days
    trend = fetchall(
        """SELECT mood_date,
                  MODE() WITHIN GROUP (ORDER BY mood_key) AS dominant_mood,
                  COUNT(*) AS total_entries
           FROM student_moods
           WHERE mood_date >= CURRENT_DATE - INTERVAL '14 days'
           GROUP BY mood_date
           ORDER BY mood_date""",
        [],
    )

    return ok({
        "distribution":  distribution,
        "totalEntries":  total,
        "periodDays":    30,
        "dailyTrend": [
            {
                "date":          str(r["mood_date"]),
                "dominantMood":  r["dominant_mood"],
                "label":         MOOD_LABELS.get(r["dominant_mood"], ""),
                "color":         MOOD_COLORS.get(r["dominant_mood"], "#94A3B8"),
                "totalEntries":  int(r["total_entries"]),
            }
            for r in trend
        ],
    })
