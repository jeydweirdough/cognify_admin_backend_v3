import datetime
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, paginate
from app.middleware.auth import login_required, permission_required, mobile_permission_required
from app.utils.responses import ok, not_found, forbidden
from app.utils.pagination import get_page_params, get_search
import uuid

admin_dash_router   = APIRouter(prefix="/api/web/admin",         tags=["admin-dashboard"])
faculty_dash_router = APIRouter(prefix="/api/web/faculty",       tags=["faculty-dashboard"])
mobile_prog_router  = APIRouter(prefix="/api/mobile/student",    tags=["mobile-progress"])

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@admin_dash_router.get("/dashboard")
async def admin_dashboard(request: Request):
    auth = permission_required("view_admin_dashboard")(request)

    # 1. Fetch all core stats instantly from our optimized PostgreSQL View
    stats = fetchone("SELECT * FROM view_admin_dashboard_stats")

    # 2. Fetch data for the charts
    growth = fetchall(
        """SELECT DATE(date_created) AS day, COUNT(*) AS new_users
           FROM users WHERE date_created >= NOW() - INTERVAL '7 days'
           GROUP BY day ORDER BY day"""
    )
    role_dist = fetchall(
        """SELECT r.name, COUNT(u.id) AS value
           FROM roles r LEFT JOIN users u ON u.role_id = r.id AND u.status = 'ACTIVE'
           GROUP BY r.name"""
    )
    recent = fetchall(
        """SELECT al.id, al.action, al.target, al.created_at,
                  u.first_name || ' ' || u.last_name AS user_name
           FROM activity_logs al LEFT JOIN users u ON u.id = al.user_id
           ORDER BY al.created_at DESC LIMIT 10"""
    )
    
    for r in recent:
        r["id"]         = str(r["id"])
        r["created_at"] = r["created_at"].isoformat()

    color_map = {"STUDENT": "#8b5cf6", "FACULTY": "#22c55e", "ADMIN": "#ef4444"}

    return ok({
        # Mapped directly from view_admin_dashboard_stats
        "totalStudents":     int(stats["total_active_students"] or 0),
        "totalSubjects":     int(stats["total_approved_subjects"] or 0),
        "totalModules":      int(stats["total_approved_modules"] or 0),
        "readinessAvg":      float(stats["general_student_readiness_avg"] or 0),
        "systemStatus":      "MAINTENANCE" if stats["is_maintenance_mode"] else "ACTIVE",
        
        # Chart Data
        "userGrowth":        [{"date": str(r["day"]), "total": int(r["new_users"])} for r in growth],
        "roleDistribution":  [
            {"name": r["name"], "value": int(r["value"]), "color": color_map.get(r["name"], "#94a3b8")}
            for r in role_dist
        ],
        "recentActivity": recent,
    })

@faculty_dash_router.get("/dashboard")
async def faculty_dashboard(request: Request):
    auth = permission_required("view_faculty_dashboard")(request)

    my_modules   = fetchone("SELECT COUNT(*) AS c FROM modules WHERE created_by = %s", [auth.user_id])
    pending_mod  = fetchone("SELECT COUNT(*) AS c FROM modules WHERE created_by = %s AND status = 'PENDING'", [auth.user_id])
    pending_ass  = fetchone("SELECT COUNT(*) AS c FROM assessments WHERE author_id = %s AND status = 'PENDING'", [auth.user_id])
    
    assess_counts = fetchall(
        "SELECT type, COUNT(*) AS c FROM assessments WHERE author_id = %s GROUP BY type",
        [auth.user_id],
    )
    counts_by_type = {r["type"]: int(r["c"]) for r in assess_counts}

    total_students = fetchone("SELECT COUNT(*) AS c FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name = 'STUDENT' AND u.status = 'ACTIVE'")
    total_subjects = fetchone("SELECT COUNT(*) AS c FROM subjects WHERE status = 'APPROVED'")
    settings       = fetchone("SELECT maintenance_mode FROM system_settings LIMIT 1")

    return ok({
        "totalStudents":   int(total_students["c"] if total_students else 0),
        "totalSubjects":   int(total_subjects["c"] if total_subjects else 0),
        "totalMaterials":  int(my_modules["c"] if my_modules else 0),
        "pendingRequests": int(pending_mod["c"] if pending_mod else 0) + int(pending_ass["c"] if pending_ass else 0),
        "systemStatus":    "MAINTENANCE" if settings and settings["maintenance_mode"] else "ACTIVE",
        "assessmentCounts": {
            "preAssessments":  counts_by_type.get("PRE_ASSESSMENT", 0),
            "quizzes":         counts_by_type.get("QUIZ", 0),
            "postAssessments": counts_by_type.get("POST_ASSESSMENT", 0),
        },
    })

# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_active_tos_subjects() -> list[str]:
    """Fetch the list of subject names from the currently ACTIVE TOS version."""
    row = fetchone("SELECT data FROM tos_versions WHERE status = 'ACTIVE' LIMIT 1")
    if not row or not row.get("data") or "subjects" not in row["data"]:
        return []
    return [s["subject"] for s in row["data"]["subjects"] if "subject" in s]

def _get_pass_probability(avg_score: float) -> dict:
    """Compute pass probability key and label from average score.
    Thresholds: >=75 HIGH_CHANCE, >=60 LIKELY, >=25 NEEDS_IMPROVEMENT, >=1 AT_RISK, 0 NO_PROGRESS."""
    if avg_score >= 75:
        return {"key": "HIGH_CHANCE", "label": "High Chance"}
    if avg_score >= 60:
        return {"key": "LIKELY", "label": "Likely to Pass"}
    if avg_score >= 25:
        return {"key": "NEEDS_IMPROVEMENT", "label": "Needs Improvement"}
    if avg_score >= 1:
        return {"key": "AT_RISK", "label": "At Risk"}
    return {"key": "NO_PROGRESS", "label": "Not Started"}

def _get_board_readiness(avg_score: float) -> str:
    """Compute board readiness level from average score.
    Thresholds: >=75 READY, >=60 MID, else LOW."""
    if avg_score >= 75:
        return "READY"
    if avg_score >= 60:
        return "MID"
    return "LOW"

def _cohort_analytics_data() -> dict:
    """Helper to fetch and calculate system-wide cohort analytics."""
    active_subjects = _get_active_tos_subjects()
    
    if not active_subjects:
        # If no TOS is active, return empty stats
        return {
            "subjectCompetency": [],
            "probabilityDistribution": [],
            "totalStudents": 0,
            "stats": None
        }

    placeholders = ",".join(["%s"] * len(active_subjects))
    subj_data = fetchall(f"""
        SELECT s.name AS subject, AVG((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) as cohort_score
        FROM subjects s
        LEFT JOIN assessments a ON a.subject_id = s.id
        LEFT JOIN assessment_results ar ON ar.assessment_id = a.id
        WHERE s.status = 'APPROVED' AND s.name IN ({placeholders})
        GROUP BY s.name
        ORDER BY s.name
    """, active_subjects)
    competency = [{"subject": r["subject"], "fullSubject": r["subject"], "cohortScore": round(float(r["cohort_score"] or 0)), "passingStandard": 75} for r in subj_data]

    students = fetchall("SELECT readiness_percentage FROM view_student_individual_readiness")
    total = len(students)

    buckets = {"HIGH_CHANCE": 0, "LIKELY": 0, "NEEDS_IMPROVEMENT": 0, "AT_RISK": 0, "NO_PROGRESS": 0}
    for s in students:
        key = _get_pass_probability(float(s["readiness_percentage"] or 0))["key"]
        buckets[key] += 1

    dist = [
        {"name": "High Chance (≥75%)",         "value": round((buckets["HIGH_CHANCE"]      / max(1, total)) * 100), "color": "#10b981", "count": buckets["HIGH_CHANCE"]},
        {"name": "Likely to Pass (60–74%)",     "value": round((buckets["LIKELY"]           / max(1, total)) * 100), "color": "#3b82f6", "count": buckets["LIKELY"]},
        {"name": "Needs Improvement (25–59%)",  "value": round((buckets["NEEDS_IMPROVEMENT"]/ max(1, total)) * 100), "color": "#f59e0b", "count": buckets["NEEDS_IMPROVEMENT"]},
        {"name": "At Risk (1–24%)",             "value": round((buckets["AT_RISK"]          / max(1, total)) * 100), "color": "#ef4444", "count": buckets["AT_RISK"]},
        {"name": "Not Started (0%)",            "value": round((buckets["NO_PROGRESS"]      / max(1, total)) * 100), "color": "#94a3b8", "count": buckets["NO_PROGRESS"]},
    ]

    sorted_competency = sorted(competency, key=lambda x: x["cohortScore"], reverse=True)
    avg_score = round(sum(c["cohortScore"] for c in competency) / max(1, len(competency))) if competency else 0
    passing_rate = round(((buckets["HIGH_CHANCE"] + buckets["LIKELY"]) / max(1, total)) * 100) if total else 0

    # Handling multiple strongest/weakest subjects
    strongest_score = sorted_competency[0]["cohortScore"] if sorted_competency else 0
    weakest_score = sorted_competency[-1]["cohortScore"] if sorted_competency else 0
    
    strongest_subjects = [c for c in competency if c["cohortScore"] == strongest_score] if competency else []
    weakest_subjects = [c for c in competency if c["cohortScore"] == weakest_score] if competency else []

    return {
        "subjectCompetency": competency,
        "probabilityDistribution": dist,
        "totalStudents": total,
        "stats": {
            "total": total,
            "avgScore": avg_score,
            "passingRate": passing_rate,
            "strongestSubject": strongest_subjects[0] if strongest_subjects else None,
            "weakestSubject": weakest_subjects[0] if weakest_subjects else None,
            "strongestSubjects": strongest_subjects,
            "weakestSubjects": weakest_subjects,
        }
    }

# ── Assessment type weights for readiness ──────────────────────────────────
# MOCK_EXAM and FINAL_ASSESSMENT are the strongest predictors of board
# performance. QUIZ is formative so carries less weight. PRE_ASSESSMENT
# is a baseline — excluded from readiness scoring.
READINESS_WEIGHTS = {
    "MOCK_EXAM":          0.40,
    "FINAL_ASSESSMENT":   0.30,
    "POST_ASSESSMENT":    0.20,
    "QUIZ":               0.10,
}

def _calc_readiness(user_id: str) -> dict:
    """
    Weighted readiness formula:
      MOCK_EXAM 40% · FINAL_ASSESSMENT 30% · POST_ASSESSMENT 20% · QUIZ 10%

    Per-subject score = weighted average of available type scores (deduped by
    latest attempt). Overall = sum of per-subject scores / total approved subjects
    (zero-fill subjects with no activity).

    Reality-check blend: if student has taken >=1 MOCK_EXAM, their latest mock
    average blends into the final score — pulling readiness down when mock
    performance trails quiz performance (prevents quiz inflation).
    """
    active_subjects = _get_active_tos_subjects()
    if not active_subjects:
        return {
            "percentage": 0.0, "raw_readiness": 0.0, "mock_avg": None,
            "progress": 0.0, "level": "LOW", "subject_scores": [], "total_subjects": 0
        }

    placeholders   = ",".join(["%s"] * len(active_subjects))
    all_subjects   = fetchall(f"SELECT name FROM subjects WHERE status = 'APPROVED' AND name IN ({placeholders}) ORDER BY name", active_subjects)
    total_subjects = len(all_subjects)

    # Step 1: AVG score per (assessment_id deduped latest) grouped by type+subject
    rows = fetchall(
        """SELECT atype, subject, AVG(pct) AS avg_score
           FROM (
               SELECT DISTINCT ON (ar.assessment_id)
                      ar.assessment_id,
                      a2.type  AS atype,
                      s2.name  AS subject,
                      (ar.score::numeric / NULLIF(ar.total_items, 0)) * 100 AS pct
               FROM   assessment_results ar
               JOIN   assessments a2 ON a2.id = ar.assessment_id
               JOIN   subjects    s2 ON s2.id = a2.subject_id
               WHERE  ar.user_id = %s
                 AND  a2.type <> 'PRE_ASSESSMENT'
               ORDER  BY ar.assessment_id, ar.date_taken DESC
           ) deduped
           GROUP BY atype, subject""",
        [user_id],
    )

    # Step 2: accumulate weighted scores per subject
    subject_map = {}
    for r in rows:
        subj  = r["subject"]
        atype = r["atype"]
        w     = READINESS_WEIGHTS.get(atype, 0.0)
        if w == 0.0:
            continue
        if subj not in subject_map:
            subject_map[subj] = {"weighted_sum": 0.0, "weight_total": 0.0,
                                  "type_scores": {}, "pre_score": 0.0}
        avg = float(r["avg_score"] or 0)
        subject_map[subj]["weighted_sum"]  += avg * w
        subject_map[subj]["weight_total"]  += w
        subject_map[subj]["type_scores"][atype] = round(avg, 1)

    # PRE_ASSESSMENT — stored for baseline display only
    pre_rows = fetchall(
        """SELECT s.name AS subject,
                  AVG((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) AS avg_score
           FROM assessment_results ar
           JOIN assessments a ON a.id = ar.assessment_id
           JOIN subjects    s ON s.id = a.subject_id
           WHERE ar.user_id = %s AND a.type = 'PRE_ASSESSMENT'
           GROUP BY s.name""",
        [user_id],
    )
    for r in pre_rows:
        subj = r["subject"]
        if subj not in subject_map:
            subject_map[subj] = {"weighted_sum": 0.0, "weight_total": 0.0,
                                  "type_scores": {}, "pre_score": 0.0}
        subject_map[subj]["pre_score"] = round(float(r["avg_score"] or 0), 1)

    # Step 3: per-subject weighted score + subject_scores list
    subject_scores     = []
    total_weighted_sum = 0.0
    for s in all_subjects:
        name = s["name"]
        data = subject_map.get(name, {"weighted_sum": 0.0, "weight_total": 0.0,
                                       "type_scores": {}, "pre_score": 0.0})
        wt      = data["weight_total"]
        current = round(data["weighted_sum"] / wt, 1) if wt > 0 else 0.0
        total_weighted_sum += current
        subject_scores.append({
            "subject":      name,
            "preScore":     data["pre_score"],
            "currentScore": current,
            "fullMark":     100,
            "typeScores":   data["type_scores"],
        })

    # Step 4: overall readiness (zero-fill = all approved subjects as denominator)
    raw_readiness = round(total_weighted_sum / max(1, total_subjects), 1)

    # Step 5: mock exam reality-check blend
    # Latest mock average acts as a floor signal. When mock < computed,
    # blend 70/30 to prevent quiz performance masking poor exam results.
    mock_row = fetchone(
        """SELECT AVG(pct) AS mock_avg
           FROM (
               SELECT DISTINCT ON (ar.assessment_id)
                      (ar.score::numeric / NULLIF(ar.total_items, 0)) * 100 AS pct
               FROM   assessment_results ar
               JOIN   assessments a ON a.id = ar.assessment_id
               WHERE  ar.user_id = %s AND a.type = 'MOCK_EXAM'
               ORDER  BY ar.assessment_id, ar.date_taken DESC
           ) latest_mocks""",
        [user_id],
    )
    mock_avg = float(mock_row["mock_avg"] or 0) \
               if mock_row and mock_row["mock_avg"] is not None else None

    if mock_avg is not None:
        if mock_avg < raw_readiness:
            pct = round(raw_readiness * 0.70 + mock_avg * 0.30, 1)
        else:
            pct = round(raw_readiness * 0.80 + mock_avg * 0.20, 1)
    else:
        pct = raw_readiness

    # Step 6: progress % (subjects touched / total approved)
    prog_row = fetchone(
        """SELECT COUNT(DISTINCT a.subject_id)::numeric / NULLIF(%s, 0) * 100 AS pct
           FROM assessment_results ar
           JOIN assessments a ON a.id = ar.assessment_id
           WHERE ar.user_id = %s AND a.type <> 'PRE_ASSESSMENT'""",
        [total_subjects, user_id],
    )
    progress = round(float(prog_row["pct"] or 0), 1) if prog_row else 0.0

    level = "HIGH" if pct >= 80 else "MODERATE" if pct >= 65 else "LOW"
    return {
        "percentage":     pct,
        "raw_readiness":  raw_readiness,
        "mock_avg":       mock_avg,
        "progress":       progress,
        "level":          level,
        "subject_scores": subject_scores,
        "total_subjects": total_subjects,
    }
def _calc_streak(user_id: str) -> int:
    rows = fetchall(
        """SELECT DISTINCT date_taken::date AS day
           FROM assessment_results WHERE user_id = %s
           ORDER BY day DESC""",
        [user_id],
    )
    streak, expected = 0, datetime.date.today()
    for r in rows:
        if r["day"] == expected:
            streak += 1
            expected -= datetime.timedelta(days=1)
        elif r["day"] < expected:
            break
    return streak

def _student_full_record(identifier: str) -> dict | None:
    # 1. Check if the identifier is a UUID or a Student Number
    is_valid_uuid = False
    try:
        uuid.UUID(identifier)
        is_valid_uuid = True
    except ValueError:
        pass

    # 2. Query the appropriate column
    if is_valid_uuid:
        student = fetchone(
            """SELECT u.id, u.first_name, u.last_name, u.email, u.photo_avatar,
                      u.cvsu_id AS student_number, u.department, u.date_created AS enrollment_date
               FROM users u JOIN roles r ON u.role_id = r.id
               WHERE u.id = %s AND r.name = 'STUDENT'""",
            [identifier],
        )
    else:
        student = fetchone(
            """SELECT u.id, u.first_name, u.last_name, u.email, u.photo_avatar,
                      u.cvsu_id AS student_number, u.department, u.date_created AS enrollment_date
               FROM users u JOIN roles r ON u.role_id = r.id
               WHERE u.cvsu_id = %s AND r.name = 'STUDENT'""",
            [identifier],
        )

    if not student: return None

    # 3. Extract the true UUID to use for all mathematical queries below
    user_id = str(student["id"])

    student["id"]   = user_id
    student["name"] = f"{student['first_name']} {student['last_name']}"
    student["section"] = student["department"] or "General"
    student["yearLevel"] = "Enrolled"
    student["enrollmentDate"] = student["enrollment_date"].strftime("%B %d, %Y")

    readiness = _calc_readiness(user_id)
    student["readinessProbability"] = readiness["level"]
    student["overallAverage"]       = readiness["percentage"]
    student["rawReadiness"]         = readiness["raw_readiness"]   # pre-blend score
    student["mockExamAvg"]          = readiness["mock_avg"]        # latest mock avg or null
    student["progressPercentage"]   = readiness["progress"]
    student["subjectScores"]        = readiness["subject_scores"]

    # Deduplicate by assessment_id — keep only the LATEST attempt per assessment.
    # Retakes are re-attempts, not separate assessments, so they must not
    # inflate the "taken" or "passed" count.
    stats = fetchone(
        """SELECT
               COUNT(*) AS total_taken,
               SUM(CASE WHEN (score::numeric/NULLIF(total_items,0)) >= 0.75 THEN 1 ELSE 0 END) AS total_passed
           FROM (
               SELECT DISTINCT ON (assessment_id)
                      assessment_id, score, total_items
               FROM assessment_results
               WHERE user_id = %s
               ORDER BY assessment_id, date_taken DESC
           ) latest""",
        [user_id],
    )
    student["assessmentsTaken"]  = int(stats["total_taken"] or 0)
    student["assessmentsPassed"] = int(stats["total_passed"] or 0)

    # ── Derived analytics computed server-side ──
    # Only sort subjects that actually have results for strength/weakness display
    scored_subjects = [s for s in readiness["subject_scores"] if s["currentScore"] > 0]
    no_data = {"subject": "No Data", "preScore": 0, "currentScore": 0, "fullMark": 0}
    sorted_scores = sorted(scored_subjects, key=lambda x: x["currentScore"], reverse=True)
    student["strength"] = sorted_scores[0] if sorted_scores else no_data
    student["weakness"] = sorted_scores[-1] if sorted_scores else no_data
    student["computedAverage"] = readiness["percentage"]
    student["totalSubjects"] = readiness["total_subjects"]
    student["percentile"] = min(99, int(readiness["percentage"] + 8))
    student["passRate"] = round((student["assessmentsPassed"] / max(1, student["assessmentsTaken"])) * 100)
    student["boardReadiness"] = _get_board_readiness(readiness["percentage"])
    _prob = _get_pass_probability(readiness["percentage"])
    student["passProbabilityKey"] = _prob["key"]
    student["passProbabilityLabel"] = _prob["label"]

    # Mock Exam Trajectory — includes MOCK_EXAM and FINAL_ASSESSMENT only.
    # POST_ASSESSMENT was incorrectly used here before; those are module-level
    # assessments, not board-simulation exams. Use latest attempt per assessment
    # so retakes show as a single point on the trajectory line.
    mock_history = fetchall(
        """SELECT ar.date_taken AS date,
                  ((ar.score::numeric/NULLIF(ar.total_items,0))*100) AS pct_score,
                  a.title AS label, a.type AS atype
           FROM (
               SELECT DISTINCT ON (assessment_id)
                      assessment_id, user_id, score, total_items, date_taken
               FROM   assessment_results
               WHERE  user_id = %s
               ORDER  BY assessment_id, date_taken DESC
           ) ar
           JOIN assessments a ON a.id = ar.assessment_id
           WHERE a.type IN ('MOCK_EXAM', 'FINAL_ASSESSMENT')
           ORDER BY ar.date_taken ASC
           LIMIT 20""",
        [user_id],
    )
    student["mockExamHistory"] = [
        {
            "date":  m["date"].strftime("%b %d"),
            "score": round(float(m["pct_score"] or 0), 1),
            "label": m["label"],
            "type":  m["atype"],
        }
        for m in mock_history
    ]

    # Count modules the student has marked as read vs total approved modules
    materials_read_row = fetchone(
        "SELECT COUNT(DISTINCT module_id) AS c FROM module_reads WHERE user_id = %s",
        [user_id],
    )
    total_modules_row = fetchone(
        "SELECT COUNT(*) AS c FROM modules WHERE status = 'APPROVED' AND parent_id IS NULL",
    )
    student["materialsRead"]  = int(materials_read_row["c"] or 0) if materials_read_row else 0
    student["totalMaterials"] = int(total_modules_row["c"] or 0) if total_modules_row else 0

    # Total assessments created in the system (approved) — system-wide denominator
    # so admin/faculty can see how many the student has attempted out of everything available
    total_assessments_row = fetchone(
        "SELECT COUNT(*) AS c FROM assessments WHERE status = 'APPROVED'",
    )
    student["totalAssessmentsInSystem"] = int(total_assessments_row["c"] or 0) if total_assessments_row else 0
    student["totalModulesInSystem"]     = student["totalMaterials"]  # same value, explicit alias for clarity
    student["streak"] = _calc_streak(user_id)

    # Note: Use ILIKE %s and pass '%log%' in the parameters to prevent psycopg2 string formatting crashes
    login_count = fetchone("SELECT COUNT(*) AS c FROM activity_logs WHERE user_id = %s AND action ILIKE %s", [user_id, '%log%'])
    student["platformLogins"] = int(login_count["c"] or 0)
    student["totalStudyHours"] = round(student["assessmentsTaken"] * 0.5 + student["platformLogins"] * 0.2, 1)
    student["avgSessionMinutes"] = round((student["totalStudyHours"] * 60) / max(1, student["platformLogins"]))

    recent = fetchall("""SELECT created_at AS date, action, target AS subject FROM activity_logs WHERE user_id = %s ORDER BY created_at DESC LIMIT 5""", [user_id])
    student["recentActivity"] = [{"date": r["date"].strftime("%b %d"), "action": r["action"], "subject": r["subject"] or "System"} for r in recent]

    topic_mastery = fetchall("""
        SELECT a.title AS topic, AVG((ar.score::numeric/NULLIF(ar.total_items,0))*100) AS mastery
        FROM assessment_results ar JOIN assessments a ON a.id = ar.assessment_id
        WHERE ar.user_id = %s GROUP BY a.title LIMIT 5
    """, [user_id])
    student["topicMastery"] = [{"topic": r["topic"], "mastery": round(float(r["mastery"] or 0), 1)} for r in topic_mastery]

    # Mood data — last 30 entries + frequency breakdown
    # mood_key values mirror MoodKey in mobile/constants/moods.ts (Inside Out 2)
    from app.routes.moods import _student_mood_data
    student["moodData"] = _student_mood_data(user_id)

    return student

def _analytics_list(request: Request):
    page, per_page = get_page_params(request)
    search = get_search(request)
    
    sql = ["""
        SELECT v.user_id AS id, v.first_name || ' ' || v.last_name AS name,
               u.cvsu_id AS student_number, u.department AS section,
               u.photo_avatar, v.readiness_percentage AS average
        FROM view_student_individual_readiness v
        JOIN users u ON u.id = v.user_id
        WHERE 1=1
    """]
    params = []
    if search:
        sql.append("AND (LOWER(v.first_name || ' ' || v.last_name) LIKE LOWER(%s) OR LOWER(u.cvsu_id) LIKE LOWER(%s))")
        params += [search, search]
        
    sql.append("ORDER BY v.first_name")
    result = paginate(" ".join(sql), params, page, per_page)

    # Fetch total approved subjects once — same denominator used in _calc_readiness()
    active_subjects = _get_active_tos_subjects()
    if active_subjects:
        placeholders = ",".join(["%s"] * len(active_subjects))
        total_subjects_row = fetchone(f"SELECT COUNT(*) AS c FROM subjects WHERE status = 'APPROVED' AND name IN ({placeholders})", active_subjects)
    else:
        total_subjects_row = None
        
    total_subjects = int(total_subjects_row["c"] or 0) if total_subjects_row else 0

    for r in result["items"]:
        r["id"] = str(r["id"])
        avg = float(r["average"] or 0)
        r["average"] = round(avg, 1)
        r["totalSubjects"] = total_subjects
        _prob = _get_pass_probability(avg)
        r["passProbabilityKey"] = _prob["key"]
        r["passProbabilityLabel"] = _prob["label"]
        
    return result

# ─────────────────────────────────────────────────────────────────────────────
# SHARED ANALYTICS ROUTES (Admin & Faculty)
# ─────────────────────────────────────────────────────────────────────────────

async def _shared_cohort_analytics(request: Request):
    auth = permission_required("view_analytics")(request)
    return ok(_cohort_analytics_data())

async def _shared_analytics_list(request: Request):
    auth = permission_required("view_analytics")(request)
    return ok(_analytics_list(request))

async def _shared_analytics_detail(request: Request, student_id: str):
    auth = permission_required("view_student_analytics")(request)
    record = _student_full_record(student_id)
    return ok(record) if record else not_found("Student not found")

# --- ADMIN ROUTES ---
@admin_dash_router.get("/analytics/cohort")
async def admin_cohort_analytics(request: Request):
    return await _shared_cohort_analytics(request)

@admin_dash_router.get("/analytics")
async def admin_get_analytics_list(request: Request):
    return await _shared_analytics_list(request)

@admin_dash_router.get("/analytics/{student_id}")
async def admin_get_analytics_detail(request: Request, student_id: str):
    return await _shared_analytics_detail(request, student_id)


# --- FACULTY ROUTES ---
@faculty_dash_router.get("/analytics/cohort")
async def faculty_cohort_analytics(request: Request):
    return await _shared_cohort_analytics(request)

@faculty_dash_router.get("/analytics")
async def faculty_get_analytics_list(request: Request):
    return await _shared_analytics_list(request)

@faculty_dash_router.get("/analytics/{student_id}")
async def faculty_get_analytics_detail(request: Request, student_id: str):
    return await _shared_analytics_detail(request, student_id)


# ═══════════════════════════════════════════════════════════════
# MOBILE — Student personal progress & readiness
# Enforces mobile_login permission (STUDENT role only).
# ═══════════════════════════════════════════════════════════════

def _get_recommended_modules(user_id: str, limit: int = 3) -> list:
    """
    Recommendation algorithm:
    1. If student has assessment history → find their weakest subjects (lowest avg score)
       and recommend modules from those subjects that they haven't studied yet.
    2. If no assessment history (fallback) → return a random selection of approved modules.
    """

    # Check if student has any assessment results
    has_results = fetchone(
        "SELECT COUNT(*) AS c FROM assessment_results WHERE user_id = %s",
        [user_id],
    )
    has_data = has_results and int(has_results["c"] or 0) > 0

    if has_data:
        # --- Data-driven path: recommend modules from weakest subjects ---

        # 1. Rank subjects by avg score (ascending = weakest first)
        weak_subjects = fetchall(
            """
            SELECT s.id AS subject_id, s.name AS subject_name,
                   AVG((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) AS avg_score
            FROM assessment_results ar
            JOIN assessments a ON a.id = ar.assessment_id
            JOIN subjects s ON s.id = a.subject_id
            WHERE ar.user_id = %s
            GROUP BY s.id, s.name
            ORDER BY avg_score ASC
            """,
            [user_id],
        )

        recommended = []

        for subj in weak_subjects:
            if len(recommended) >= limit:
                break

            subj_id = str(subj["subject_id"])
            avg_score = round(float(subj["avg_score"] or 0), 1)

            # 2. Get modules from this weak subject that the student hasn't accessed
            modules = fetchall(
                """
                SELECT m.id, m.title, m.format, s.name AS subject_name, s.id AS subject_id
                FROM modules m
                JOIN subjects s ON s.id = m.subject_id
                WHERE m.subject_id = %s
                  AND m.status = 'APPROVED'
                  AND m.parent_id IS NULL
                ORDER BY m.sort_order ASC, m.created_at ASC
                LIMIT %s
                """,
                [subj_id, limit - len(recommended)],
            )

            for mod in modules:
                recommended.append({
                    "id":           str(mod["id"]),
                    "title":        mod["title"],
                    "format":       mod["format"],
                    "subject_name": mod["subject_name"],
                    "subject_id":   str(mod["subject_id"]),
                    "reason":       "weak_subject",
                    "avg_score":    avg_score,
                })

        # 3. If not enough from weak subjects, pad with random approved modules
        if len(recommended) < limit:
            existing_ids = [r["id"] for r in recommended]
            placeholder = ",".join(["%s"] * len(existing_ids)) if existing_ids else "NULL"
            extra_sql = f"""
                SELECT m.id, m.title, m.format, s.name AS subject_name, s.id AS subject_id
                FROM modules m
                JOIN subjects s ON s.id = m.subject_id
                WHERE m.status = 'APPROVED'
                  AND m.parent_id IS NULL
                  {"AND m.id NOT IN (" + placeholder + ")" if existing_ids else ""}
                ORDER BY RANDOM()
                LIMIT %s
            """
            extra_params = existing_ids + [limit - len(recommended)]
            extras = fetchall(extra_sql, extra_params)
            for mod in extras:
                recommended.append({
                    "id":           str(mod["id"]),
                    "title":        mod["title"],
                    "format":       mod["format"],
                    "subject_name": mod["subject_name"],
                    "subject_id":   str(mod["subject_id"]),
                    "reason":       "explore",
                    "avg_score":    None,
                })

        return recommended

    else:
        # --- Fallback path: no assessment data yet, show random modules ---
        random_modules = fetchall(
            """
            SELECT m.id, m.title, m.format, s.name AS subject_name, s.id AS subject_id
            FROM modules m
            JOIN subjects s ON s.id = m.subject_id
            WHERE m.status = 'APPROVED'
              AND m.parent_id IS NULL
            ORDER BY RANDOM()
            LIMIT %s
            """,
            [limit],
        )
        return [
            {
                "id":           str(mod["id"]),
                "title":        mod["title"],
                "format":       mod["format"],
                "subject_name": mod["subject_name"],
                "subject_id":   str(mod["subject_id"]),
                "reason":       "explore",
                "avg_score":    None,
            }
            for mod in random_modules
        ]


@mobile_prog_router.get("/progress/subjects/{subject_id}/assessments")
async def mobile_subject_assessments(request: Request, subject_id: str):
    """
    Return all approved assessments for a subject with per-student unlock/done/score status.

    Unlock logic (sequential gate):
      1. PRE_ASSESSMENT  — always unlocked
      2. QUIZ            — unlocked after student has submitted PRE_ASSESSMENT
      3. POST_ASSESSMENT — unlocked after ALL quizzes for the subject are done (score recorded)
      4. MOCK_EXAM /
         FINAL_ASSESSMENT — unlocked after POST_ASSESSMENT is done
    """
    auth = mobile_permission_required("mobile_view_progress")(request)
    user_id = auth.user_id

    # ── Fetch all approved assessments for this subject ──────────────────────
    assessments = fetchall(
        """SELECT a.id, a.title, a.type, a.items, a.module_id
           FROM assessments a
           WHERE a.subject_id = %s AND a.status = 'APPROVED'
           ORDER BY
             CASE a.type
               WHEN 'PRE_ASSESSMENT'   THEN 1
               WHEN 'QUIZ'             THEN 2
               WHEN 'PRACTICE_TEST'    THEN 3
               WHEN 'POST_ASSESSMENT'  THEN 4
               WHEN 'MOCK_EXAM'        THEN 5
               WHEN 'FINAL_ASSESSMENT' THEN 6
               ELSE 7
             END,
             a.created_at ASC""",
        [subject_id],
    )

    if not assessments:
        return ok({
            "pre_assessment_done":       False,
            "all_quizzes_done":          False,
            "post_assessment_unlocked":  False,
            "post_assessment_done":      False,
            "final_unlocked":            False,
            "assessments":               [],
        })

    assessment_ids = [str(a["id"]) for a in assessments]

    # ── Fetch the student's best score per assessment ────────────────────────
    if assessment_ids:
        placeholders = ",".join(["%s"] * len(assessment_ids))
        results = fetchall(
            f"""SELECT ar.assessment_id,
                       MAX((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) AS best_pct,
                       COUNT(*) AS attempt_count
                FROM assessment_results ar
                WHERE ar.user_id = %s
                  AND ar.assessment_id IN ({placeholders})
                GROUP BY ar.assessment_id""",
            [user_id] + assessment_ids,
        )
    else:
        results = []

    score_map = {
        str(r["assessment_id"]): {
            "best_score":    round(float(r["best_pct"] or 0), 1),
            "attempt_count": int(r["attempt_count"]),
        }
        for r in results
    }

    # ── Fetch which modules in this subject the student has read ─────────────
    read_rows = fetchall(
        "SELECT module_id FROM module_reads WHERE user_id = %s AND subject_id = %s",
        [user_id, subject_id],
    )
    read_module_ids = {str(r["module_id"]) for r in read_rows}

    # ── Derive unlock gates ──────────────────────────────────────────────────
    pre_ids  = [str(a["id"]) for a in assessments if a["type"] == "PRE_ASSESSMENT"]
    quiz_ids = [str(a["id"]) for a in assessments if a["type"] in ("QUIZ", "PRACTICE_TEST")]
    post_ids = [str(a["id"]) for a in assessments if a["type"] == "POST_ASSESSMENT"]

    pre_done     = any(score_map.get(aid, {}).get("attempt_count", 0) > 0 for aid in pre_ids) if pre_ids else True
    quizzes_done = all(score_map.get(aid, {}).get("attempt_count", 0) > 0 for aid in quiz_ids) if quiz_ids else True
    post_done    = any(score_map.get(aid, {}).get("attempt_count", 0) > 0 for aid in post_ids) if post_ids else False
    post_unlocked  = pre_done and quizzes_done
    final_unlocked = post_done

    # Check all modules in this subject are read (required before any quiz)
    all_subject_modules = fetchall(
        "SELECT id FROM modules WHERE subject_id = %s AND status = 'APPROVED' AND parent_id IS NULL",
        [subject_id],
    )
    all_modules_read = all(str(m["id"]) in read_module_ids for m in all_subject_modules) if all_subject_modules else False

    def _is_locked(atype: str, a: dict) -> bool:
        if atype == "PRE_ASSESSMENT":
            return False
        if atype in ("QUIZ", "PRACTICE_TEST"):
            # Quiz for a specific module requires that module to be read
            module_id = str(a.get("module_id") or "")
            if module_id:
                return module_id not in read_module_ids or not pre_done
            # Quiz not linked to specific module — require pre done + all modules read
            return not pre_done or not all_modules_read
        if atype == "POST_ASSESSMENT":
            return not post_unlocked
        if atype in ("MOCK_EXAM", "FINAL_ASSESSMENT"):
            return not final_unlocked
        return False

    # ── Build response ───────────────────────────────────────────────────────
    items = []
    for a in assessments:
        aid   = str(a["id"])
        atype = a["type"]
        stats = score_map.get(aid, {})
        items.append({
            "id":         aid,
            "title":      a["title"],
            "type":       atype,
            "items":      a["items"] or 0,
            "module_id":  str(a["module_id"]) if a.get("module_id") else None,
            "locked":     _is_locked(atype, a),
            "done":       stats.get("attempt_count", 0) > 0,
            "best_score": stats.get("best_score", None) if stats.get("attempt_count", 0) > 0 else None,
        })

    return ok({
        "pre_assessment_done":      pre_done,
        "all_quizzes_done":         quizzes_done,
        "post_assessment_unlocked": post_unlocked,
        "post_assessment_done":     post_done,
        "final_unlocked":           final_unlocked,
        "all_modules_read":         all_modules_read,
        "assessments":              items,
    })


@mobile_prog_router.get("/progress/recommendations")
async def mobile_progress_recommendations(request: Request):
    """Return personalized module recommendations based on the student's weak subjects."""
    auth = mobile_permission_required("mobile_view_progress")(request)
    recommendations = _get_recommended_modules(auth.user_id, limit=3)
    return ok({"recommendations": recommendations})


@mobile_prog_router.get("/progress")
async def mobile_progress(request: Request):
    """Return the authenticated student's own readiness & assessment results."""
    auth = mobile_permission_required("mobile_view_progress")(request)

    view_row = fetchone(
        "SELECT readiness_percentage, progress_percentage FROM view_student_individual_readiness WHERE user_id = %s",
        [auth.user_id],
    )
    readiness_pct = float(view_row["readiness_percentage"] or 0) if view_row else 0.0
    progress_pct  = float(view_row["progress_percentage"]  or 0) if view_row else 0.0

    results = fetchall(
        """SELECT ar.id, ar.assessment_id, ar.score, ar.total_items, ar.date_taken,
                  a.title AS assessment_title, a.type AS assessment_type,
                  s.name AS subject_name
           FROM assessment_results ar
           JOIN assessments a ON a.id = ar.assessment_id
           LEFT JOIN subjects s ON s.id = a.subject_id
           WHERE ar.user_id = %s
           ORDER BY ar.date_taken DESC""",
        [auth.user_id],
    )
    for r in results:
        r["id"]            = str(r["id"])
        r["assessment_id"] = str(r["assessment_id"])
        r["date_taken"]    = r["date_taken"].isoformat()

    # ── Subject-level breakdown — mirrors _calc_readiness AVG logic ──
    # Step 1: AVG score per (subject × assessment type), excluding PRE_ASSESSMENT
    # Step 2: AVG those type averages per subject  ← was MAX, now AVG
    type_rows = fetchall(
        """SELECT a.type, s.name AS subject,
                  AVG((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) AS avg_score
           FROM assessment_results ar
           JOIN assessments a ON a.id = ar.assessment_id
           JOIN subjects s ON s.id = a.subject_id
           WHERE ar.user_id = %s
             AND a.type <> 'PRE_ASSESSMENT'
           GROUP BY a.type, s.name""",
        [auth.user_id],
    )
    pre_rows = fetchall(
        """SELECT s.name AS subject,
                  AVG((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) AS avg_score
           FROM assessment_results ar
           JOIN assessments a ON a.id = ar.assessment_id
           JOIN subjects s ON s.id = a.subject_id
           WHERE ar.user_id = %s
             AND a.type = 'PRE_ASSESSMENT'
           GROUP BY s.name""",
        [auth.user_id],
    )

    subject_map: dict = {}
    for r in type_rows:
        subj = r["subject"]
        if subj not in subject_map:
            subject_map[subj] = {"type_scores": [], "pre_score": 0.0}
        subject_map[subj]["type_scores"].append(float(r["avg_score"] or 0))
    for r in pre_rows:
        subj = r["subject"]
        if subj not in subject_map:
            subject_map[subj] = {"type_scores": [], "pre_score": 0.0}
        subject_map[subj]["pre_score"] = float(r["avg_score"] or 0)

    all_subjects = fetchall("SELECT name FROM subjects WHERE status = 'APPROVED' ORDER BY name")
    subject_scores = []
    for s in all_subjects:
        name = s["name"]
        data = subject_map.get(name, {"type_scores": [], "pre_score": 0.0})
        type_scores = data["type_scores"]
        current = round(sum(type_scores) / len(type_scores), 1) if type_scores else 0.0
        subject_scores.append({
            "subject":      name,
            "preScore":     round(data["pre_score"], 1),
            "currentScore": current,
        })

    # Count unique assessments taken (dedupe by assessment_id — retakes are not
    # separate assessments, they are re-attempts of the same one)
    seen_assessment_ids: set = set()
    for r in results:
        seen_assessment_ids.add(r["assessment_id"])
    unique_assessments_taken = len(seen_assessment_ids)

    # Compute mock exam avg for mobile display
    mock_row = fetchone(
        """SELECT AVG(pct) AS mock_avg
           FROM (
               SELECT DISTINCT ON (ar.assessment_id)
                      (ar.score::numeric / NULLIF(ar.total_items, 0)) * 100 AS pct
               FROM   assessment_results ar
               JOIN   assessments a ON a.id = ar.assessment_id
               WHERE  ar.user_id = %s AND a.type = 'MOCK_EXAM'
               ORDER  BY ar.assessment_id, ar.date_taken DESC
           ) m""",
        [auth.user_id],
    )
    mock_exam_avg = round(float(mock_row["mock_avg"] or 0), 1) \
                   if mock_row and mock_row["mock_avg"] is not None else None

    # ── Extra stats for profile screen ────────────────────────────────────
    streak = _calc_streak(auth.user_id)

    # Modules read by this student
    modules_read_row = fetchone(
        "SELECT COUNT(DISTINCT module_id) AS c FROM module_reads WHERE user_id = %s",
        [auth.user_id],
    )
    modules_read = int(modules_read_row["c"] or 0) if modules_read_row else 0

    # Unique passed assessments (latest attempt >= 75%)
    passed_row = fetchone(
        """SELECT COUNT(*) AS c
           FROM (
               SELECT DISTINCT ON (assessment_id)
                      assessment_id, score, total_items
               FROM   assessment_results
               WHERE  user_id = %s
               ORDER  BY assessment_id, date_taken DESC
           ) latest
           WHERE (score::numeric / NULLIF(total_items, 0)) >= 0.75""",
        [auth.user_id],
    )
    assessments_passed = int(passed_row["c"] or 0) if passed_row else 0

    # Study hours estimate: assessments * 0.5h + modules read * 0.3h
    study_hours = round(unique_assessments_taken * 0.5 + modules_read * 0.3, 1)

    return ok({
        "readiness_percentage":    readiness_pct,
        "progress_percentage":     progress_pct,
        "results":                 results,
        "total_assessments_taken": unique_assessments_taken,
        "assessments_passed":      assessments_passed,
        "subject_scores":          subject_scores,
        "mock_exam_avg":           mock_exam_avg,
        "streak_days":             streak,
        "modules_read":            modules_read,
        "study_hours":             study_hours,
    })