"""
Analytics + Dashboard routes
  /api/web/admin/dashboard        → admin summary stats
  /api/web/faculty/dashboard      → faculty summary stats
  /api/web/admin/analytics        → list students with summary
  /api/web/admin/analytics/:id    → full StudentRecord
  /api/web/faculty/analytics      → same, scoped to faculty's subjects
  /api/web/faculty/analytics/:id  → full StudentRecord
  /api/mobile/student/dashboard   → student own summary
  /api/mobile/student/progress    → student own full analytics
"""
from flask import Blueprint, g
from app.db import fetchone, fetchall, execute, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, not_found
from app.utils.pagination import get_page_params, get_search

admin_dash_bp    = Blueprint("admin_dash",    __name__, url_prefix="/api/web/admin")
faculty_dash_bp  = Blueprint("faculty_dash",  __name__, url_prefix="/api/web/faculty")
mobile_prog_bp   = Blueprint("mobile_prog",   __name__, url_prefix="/api/mobile/student")


# ─────────────────────────────────────────────────────────────────────────────
# Shared readiness calculator
# ─────────────────────────────────────────────────────────────────────────────

def _calc_readiness(student_id: str) -> dict:
    """
    Compute a student's overall readiness from submission history.
    Returns { level, percentage, subject_scores[] }
    """
    rows = fetchall(
        """SELECT a.type, s.name AS subject, AVG(sub.score) AS avg_score
           FROM assessment_submissions sub
           JOIN assessments a ON a.id = sub.assessment_id
           JOIN subjects s ON s.id = a.subject_id
           WHERE sub.student_id = %s
           GROUP BY a.type, s.name""",
        [student_id],
    )

    subject_map: dict[str, dict] = {}
    for r in rows:
        subj = r["subject"]
        if subj not in subject_map:
            subject_map[subj] = {"subject": subj, "scores": [], "pre_score": 0, "current_score": 0}
        score = float(r["avg_score"] or 0)
        subject_map[subj]["scores"].append(score)
        if r["type"] == "PRE_ASSESSMENT":
            subject_map[subj]["pre_score"] = score
        else:
            subject_map[subj]["current_score"] = max(subject_map[subj]["current_score"], score)

    subject_scores = []
    all_scores = []
    for subj_data in subject_map.values():
        avg = sum(subj_data["scores"]) / len(subj_data["scores"]) if subj_data["scores"] else 0
        all_scores.append(avg)
        subject_scores.append({
            "subject": subj_data["subject"],
            "preScore": round(subj_data["pre_score"], 1),
            "currentScore": round(subj_data["current_score"], 1),
            "fullMark": 100,
        })

    pct = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0
    level = "HIGH" if pct >= 80 else "MODERATE" if pct >= 65 else "LOW"
    return {"percentage": pct, "level": level, "subject_scores": subject_scores}


def _student_full_record(student_id: str) -> dict | None:
    student = fetchone(
        """SELECT u.id, u.first_name, u.last_name, u.email,
                  u.institutional_id, u.department, u.date_created AS enrollment_date
           FROM users u JOIN roles r ON u.role_id = r.id
           WHERE u.id = %s AND r.name = 'STUDENT'""",
        [student_id],
    )
    if not student:
        return None

    student["id"] = str(student["id"])
    student["name"] = f"{student['first_name']} {student['last_name']}"

    readiness = _calc_readiness(student_id)
    student["readinessProbability"] = readiness["level"]
    student["overallAverage"] = readiness["percentage"]
    student["subjectScores"] = readiness["subject_scores"]

    # Submission stats
    stats = fetchone(
        """SELECT COUNT(*) AS total_taken,
                  SUM(CASE WHEN passed THEN 1 ELSE 0 END) AS total_passed,
                  COALESCE(AVG(score), 0) AS avg_score
           FROM assessment_submissions WHERE student_id = %s""",
        [student_id],
    )
    student["assessmentsTaken"]  = int(stats["total_taken"]) if stats else 0
    student["assessmentsPassed"] = int(stats["total_passed"] or 0) if stats else 0

    # Mock exam history (POST_ASSESSMENT submissions over time)
    mock_history = fetchall(
        """SELECT sub.submitted_at AS date, sub.score, a.title AS label
           FROM assessment_submissions sub
           JOIN assessments a ON a.id = sub.assessment_id
           WHERE sub.student_id = %s AND a.type = 'POST_ASSESSMENT'
           ORDER BY sub.submitted_at DESC LIMIT 10""",
        [student_id],
    )
    student["mockExamHistory"] = [
        {"date": m["date"].strftime("%b %d"), "score": float(m["score"]), "label": m["label"]}
        for m in mock_history
    ]

    # Materials read
    materials_read = fetchone(
        "SELECT COUNT(*) AS c FROM student_progress WHERE student_id = %s",
        [student_id],
    )
    total_materials = fetchone("SELECT COUNT(*) AS c FROM content_modules WHERE status = 'APPROVED'")
    student["materialsRead"]  = int(materials_read["c"]) if materials_read else 0
    student["totalMaterials"] = int(total_materials["c"]) if total_materials else 0

    # Streak (consecutive days with submissions)
    student["streak"] = _calc_streak(student_id)

    # Study hours approximation (time_taken_s sum)
    time_row = fetchone(
        "SELECT COALESCE(SUM(time_taken_s), 0) AS total FROM assessment_submissions WHERE student_id = %s",
        [student_id],
    )
    student["totalStudyHours"] = round((time_row["total"] or 0) / 3600, 1) if time_row else 0

    # Platform logins approximation
    login_count = fetchone(
        "SELECT COUNT(*) AS c FROM activity_logs WHERE user_id = %s AND action LIKE '%logged in%'",
        [student_id],
    )
    student["platformLogins"] = int(login_count["c"]) if login_count else 0

    return student


def _calc_streak(student_id: str) -> int:
    """Count consecutive days with at least one submission going backwards from today."""
    rows = fetchall(
        """SELECT DISTINCT submitted_at::date AS day
           FROM assessment_submissions WHERE student_id = %s
           ORDER BY day DESC""",
        [student_id],
    )
    from datetime import date, timedelta
    streak, expected = 0, date.today()
    for r in rows:
        if r["day"] == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif r["day"] < expected:
            break
    return streak


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@admin_dash_bp.get("/dashboard")
@login_required
@roles_required("ADMIN")
def admin_dashboard():
    total_students = fetchone("SELECT COUNT(*) AS c FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name = 'STUDENT'")
    total_faculty  = fetchone("SELECT COUNT(*) AS c FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name = 'FACULTY'")
    total_subjects = fetchone("SELECT COUNT(*) AS c FROM subjects")
    total_topics   = fetchone("SELECT COUNT(*) AS c FROM topics")
    total_content  = fetchone("SELECT COUNT(*) AS c FROM content_modules")
    pending_content = fetchone("SELECT COUNT(*) AS c FROM content_modules WHERE status IN ('PENDING','REMOVAL_PENDING')")
    pending_assess  = fetchone("SELECT COUNT(*) AS c FROM assessments WHERE status = 'PENDING'")
    pending_users   = fetchone("SELECT COUNT(*) AS c FROM users WHERE status = 'PENDING'")
    settings        = fetchone("SELECT maintenance_mode FROM system_settings LIMIT 1")

    # Readiness average across all students
    readiness_row = fetchone(
        """SELECT COALESCE(AVG(score), 0) AS avg
           FROM assessment_submissions"""
    )

    # User growth – last 7 days
    growth = fetchall(
        """SELECT DATE(date_created) AS day, COUNT(*) AS new_users
           FROM users WHERE date_created >= NOW() - INTERVAL '7 days'
           GROUP BY day ORDER BY day"""
    )

    # Role distribution
    role_dist = fetchall(
        """SELECT r.name, COUNT(u.id) AS value
           FROM roles r LEFT JOIN users u ON u.role_id = r.id AND u.status = 'ACTIVE'
           GROUP BY r.name"""
    )

    # Recent activity
    recent = fetchall(
        """SELECT al.id, al.action, al.target, al.created_at,
                  u.first_name || ' ' || u.last_name AS user_name
           FROM activity_logs al LEFT JOIN users u ON u.id = al.user_id
           ORDER BY al.created_at DESC LIMIT 10"""
    )
    for r in recent:
        r["id"] = str(r["id"])
        r["created_at"] = r["created_at"].isoformat()

    color_map = {"STUDENT": "#8b5cf6", "FACULTY": "#22c55e", "ADMIN": "#ef4444"}

    return ok({
        "totalStudents":    int(total_students["c"]),
        "totalFaculty":     int(total_faculty["c"]),
        "totalSubjects":    int(total_subjects["c"]),
        "totalModularUnits": int(total_topics["c"]),
        "totalMaterials":   int(total_content["c"]),
        "pendingApprovals": int(pending_content["c"]) + int(pending_assess["c"]) + int(pending_users["c"]),
        "readinessAvg":     round(float(readiness_row["avg"]), 1),
        "systemStatus":     "MAINTENANCE" if settings and settings["maintenance_mode"] else "ACTIVE",
        "userGrowth": [{"date": str(r["day"]), "total": int(r["new_users"])} for r in growth],
        "roleDistribution": [
            {"name": r["name"], "value": int(r["value"]), "color": color_map.get(r["name"], "#94a3b8")}
            for r in role_dist
        ],
        "recentActivity": recent,
    })


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@faculty_dash_bp.get("/dashboard")
@login_required
@roles_required("FACULTY")
def faculty_dashboard():
    faculty_id = g.user_id
    settings   = fetchone("SELECT maintenance_mode FROM system_settings LIMIT 1")

    my_content   = fetchone("SELECT COUNT(*) AS c FROM content_modules WHERE author_id = %s", [faculty_id])
    my_assess    = fetchone("SELECT COUNT(*) AS c FROM assessments WHERE author_id = %s",      [faculty_id])
    pending_cont = fetchone("SELECT COUNT(*) AS c FROM content_modules WHERE author_id = %s AND status = 'PENDING'", [faculty_id])
    pending_ass  = fetchone("SELECT COUNT(*) AS c FROM assessments WHERE author_id = %s AND status = 'PENDING'",     [faculty_id])

    assess_counts = fetchall(
        """SELECT type, COUNT(*) AS c FROM assessments WHERE author_id = %s GROUP BY type""",
        [faculty_id],
    )
    counts_by_type = {r["type"]: int(r["c"]) for r in assess_counts}

    # Students enrolled in system (all active students for now)
    total_students = fetchone("SELECT COUNT(*) AS c FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name = 'STUDENT' AND u.status = 'ACTIVE'")
    total_subjects = fetchone("SELECT COUNT(*) AS c FROM subjects WHERE status = 'APPROVED'")

    return ok({
        "totalStudents":    int(total_students["c"]),
        "totalModules":     int(my_content["c"]),
        "totalSubjects":    int(total_subjects["c"]),
        "pendingRequests":  int(pending_cont["c"]) + int(pending_ass["c"]),
        "systemStatus":     "MAINTENANCE" if settings and settings["maintenance_mode"] else "ACTIVE",
        "assessmentCounts": {
            "preAssessments":  counts_by_type.get("PRE_ASSESSMENT", 0),
            "quizzes":         counts_by_type.get("QUIZ", 0),
            "postAssessments": counts_by_type.get("POST_ASSESSMENT", 0),
        },
    })


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS LIST — shared between admin and faculty
# ─────────────────────────────────────────────────────────────────────────────

def _analytics_list():
    page, per_page = get_page_params()
    search = get_search()
    sql = ["""
        SELECT u.id, u.first_name || ' ' || u.last_name AS name,
               u.email, u.institutional_id, u.department,
               COALESCE(AVG(sub.score), 0) AS overall_average,
               COUNT(sub.id) AS assessments_taken
        FROM users u
        JOIN roles r ON u.role_id = r.id
        LEFT JOIN assessment_submissions sub ON sub.student_id = u.id
        WHERE r.name = 'STUDENT' AND u.status = 'ACTIVE'
    """]
    params = []
    if search:
        sql.append("AND (LOWER(u.first_name || ' ' || u.last_name) LIKE LOWER(%s) OR LOWER(u.email) LIKE LOWER(%s))")
        params += [search, search]
    sql.append("GROUP BY u.id, u.first_name, u.last_name, u.email, u.institutional_id, u.department ORDER BY u.first_name")
    result = paginate(" ".join(sql), params, page, per_page)
    for r in result["items"]:
        r["id"] = str(r["id"])
        avg = float(r["overall_average"])
        r["overall_average"] = round(avg, 1)
        r["readiness_probability"] = "HIGH" if avg >= 80 else "MODERATE" if avg >= 65 else "LOW"
    return result


@admin_dash_bp.get("/analytics")
@login_required
@roles_required("ADMIN")
def admin_analytics_list():
    return ok(_analytics_list())


@admin_dash_bp.get("/analytics/<student_id>")
@login_required
@roles_required("ADMIN")
def admin_analytics_detail(student_id):
    record = _student_full_record(student_id)
    return ok(record) if record else not_found("Student not found")


@faculty_dash_bp.get("/analytics")
@login_required
@roles_required("FACULTY")
def faculty_analytics_list():
    return ok(_analytics_list())


@faculty_dash_bp.get("/analytics/<student_id>")
@login_required
@roles_required("FACULTY")
def faculty_analytics_detail(student_id):
    record = _student_full_record(student_id)
    return ok(record) if record else not_found("Student not found")


# ─────────────────────────────────────────────────────────────────────────────
# MOBILE — STUDENT DASHBOARD + PROGRESS
# ─────────────────────────────────────────────────────────────────────────────

@mobile_prog_bp.get("/dashboard")
@login_required
@roles_required("STUDENT")
def student_dashboard():
    student = fetchone(
        "SELECT id, first_name, last_name, email, institutional_id, department FROM users WHERE id = %s",
        [g.user_id],
    )
    readiness = _calc_readiness(g.user_id)

    # Per-subject breakdown
    subjects = fetchall(
        """SELECT s.id, s.name, s.color
           FROM subjects s WHERE s.status = 'APPROVED' ORDER BY s.name""",
    )
    subject_breakdown = []
    for s in subjects:
        sid = str(s["id"])
        total_content = fetchone("SELECT COUNT(*) AS c FROM content_modules WHERE subject_id = %s AND status = 'APPROVED'", [sid])
        completed     = fetchone("SELECT COUNT(*) AS c FROM student_progress sp JOIN content_modules cm ON cm.id = sp.content_id WHERE sp.student_id = %s AND cm.subject_id = %s", [g.user_id, sid])
        assess_avg    = fetchone(
            """SELECT COALESCE(AVG(sub.score), 0) AS avg FROM assessment_submissions sub
               JOIN assessments a ON a.id = sub.assessment_id
               WHERE sub.student_id = %s AND a.subject_id = %s""",
            [g.user_id, sid],
        )
        subj_scores   = next((x for x in readiness["subject_scores"] if x["subject"] == s["name"]), None)
        tc = int(total_content["c"]) if total_content else 0
        cp = int(completed["c"])     if completed else 0
        subject_breakdown.append({
            "id":               sid,
            "name":             s["name"],
            "color":            s["color"],
            "completionPct":    round((cp / tc * 100), 1) if tc else 0,
            "readinessScore":   subj_scores["currentScore"] if subj_scores else 0,
            "assessmentAvg":    round(float(assess_avg["avg"]), 1) if assess_avg else 0,
        })

    return ok({
        "student":         {k: str(v) if k == "id" else v for k, v in student.items()},
        "overallReadiness": readiness,
        "subjects":        subject_breakdown,
        "streak":          _calc_streak(g.user_id),
    })


@mobile_prog_bp.get("/progress")
@login_required
@roles_required("STUDENT")
def student_progress():
    record = _student_full_record(g.user_id)
    return ok(record) if record else not_found()