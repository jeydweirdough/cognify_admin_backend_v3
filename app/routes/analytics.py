import datetime
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, paginate
from app.middleware.auth import login_required
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
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()

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
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()

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

def _cohort_analytics_data() -> dict:
    """Helper to fetch and calculate system-wide cohort analytics."""
    subj_data = fetchall("""
        SELECT s.name AS subject, AVG((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) as cohort_score
        FROM assessment_results ar
        JOIN assessments a ON a.id = ar.assessment_id
        JOIN subjects s ON s.id = a.subject_id
        GROUP BY s.name
    """)
    competency = [{"subject": r["subject"].split()[-1], "fullSubject": r["subject"], "cohortScore": round(float(r["cohort_score"] or 0)), "passingStandard": 75} for r in subj_data]

    students = fetchall("SELECT readiness_percentage FROM view_student_individual_readiness")
    total = len(students)
    high = sum(1 for s in students if float(s["readiness_percentage"] or 0) >= 80)
    mod = sum(1 for s in students if 65 <= float(s["readiness_percentage"] or 0) < 80)
    low = sum(1 for s in students if float(s["readiness_percentage"] or 0) < 65)

    dist = [
        {"name": "High Probability (>80%)", "value": round((high/max(1,total))*100) if total else 0, "color": "#10b981", "count": high},
        {"name": "Moderate Probability (65–79%)", "value": round((mod/max(1,total))*100) if total else 0, "color": "#f59e0b", "count": mod},
        {"name": "Low Probability (<65%)", "value": round((low/max(1,total))*100) if total else 0, "color": "#ef4444", "count": low}
    ]

    return {
        "subjectCompetency": competency,
        "probabilityDistribution": dist,
        "totalStudents": total
    }

def _calc_readiness(user_id: str) -> dict:
    rows = fetchall(
        """SELECT a.type, s.name AS subject, 
                  AVG((ar.score::numeric / NULLIF(ar.total_items, 0)) * 100) AS avg_score
           FROM assessment_results ar
           JOIN assessments a ON a.id = ar.assessment_id
           JOIN subjects s ON s.id = a.subject_id
           WHERE ar.user_id = %s
           GROUP BY a.type, s.name""",
        [user_id],
    )

    subject_map = {}
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
            "subject":      subj_data["subject"],
            "preScore":     round(subj_data["pre_score"], 1),
            "currentScore": round(subj_data["current_score"], 1),
            "fullMark":     100,
        })

    pct   = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0
    level = "HIGH" if pct >= 80 else "MODERATE" if pct >= 65 else "LOW"
    return {"percentage": pct, "level": level, "subject_scores": subject_scores}

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
            """SELECT u.id, u.first_name, u.last_name, u.email,
                      u.cvsu_id AS student_number, u.department, u.date_created AS enrollment_date
               FROM users u JOIN roles r ON u.role_id = r.id
               WHERE u.id = %s AND r.name = 'STUDENT'""",
            [identifier],
        )
    else:
        student = fetchone(
            """SELECT u.id, u.first_name, u.last_name, u.email,
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
    student["subjectScores"]        = readiness["subject_scores"]

    stats = fetchone(
        """SELECT COUNT(*) AS total_taken,
                  SUM(CASE WHEN (score::numeric/NULLIF(total_items,0)) >= 0.75 THEN 1 ELSE 0 END) AS total_passed
           FROM assessment_results WHERE user_id = %s""",
        [user_id],
    )
    student["assessmentsTaken"]  = int(stats["total_taken"] or 0)
    student["assessmentsPassed"] = int(stats["total_passed"] or 0)

    mock_history = fetchall(
        """SELECT ar.date_taken AS date, ((ar.score::numeric/NULLIF(ar.total_items,0))*100) AS pct_score, a.title AS label
           FROM assessment_results ar JOIN assessments a ON a.id = ar.assessment_id
           WHERE ar.user_id = %s AND a.type = 'POST_ASSESSMENT'
           ORDER BY ar.date_taken DESC LIMIT 10""",
        [user_id],
    )
    student["mockExamHistory"] = [{"date": m["date"].strftime("%b %d"), "score": round(float(m["pct_score"] or 0),1), "label": m["label"]} for m in mock_history]

    student["materialsRead"]  = 0
    student["totalMaterials"] = 0
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

    return student

def _analytics_list(request: Request):
    page, per_page = get_page_params(request)
    search = get_search(request)
    
    sql = ["""
        SELECT v.user_id AS id, v.first_name || ' ' || v.last_name AS name,
               u.cvsu_id AS student_number, u.department AS section,
               v.readiness_percentage AS average
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
    
    for r in result["items"]:
        r["id"] = str(r["id"])
        avg = float(r["average"] or 0)
        r["average"] = avg
        r["probability"] = "HIGH" if avg >= 80 else "MODERATE" if avg >= 65 else "LOW"
        r["weakSubject"] = "N/A" 
        
    return result

# ─────────────────────────────────────────────────────────────────────────────
# SHARED ANALYTICS ROUTES (Admin & Faculty)
# ─────────────────────────────────────────────────────────────────────────────

async def _shared_cohort_analytics(request: Request):
    auth = login_required(request)
    if auth.role not in ["ADMIN", "FACULTY"]: return forbidden()
    return ok(_cohort_analytics_data())

async def _shared_analytics_list(request: Request):
    auth = login_required(request)
    if auth.role not in ["ADMIN", "FACULTY"]: return forbidden()
    return ok(_analytics_list(request))

async def _shared_analytics_detail(request: Request, student_id: str):
    auth = login_required(request)
    if auth.role not in ["ADMIN", "FACULTY"]: return forbidden()
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