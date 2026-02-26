"""Subjects CRUD + enrollment management."""
from flask import Blueprint, request, g
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, error, not_found
from app.utils.pagination import get_page_params, get_search

bp = Blueprint("subjects", __name__, url_prefix="/api/subjects")


@bp.get("/")
@login_required
def list_subjects():
    page, per_page = get_page_params()
    search = get_search()
    status_filter = request.args.get("status")

    conditions, params = [], []

    # Students only see APPROVED subjects they are enrolled in
    if g.role == "STUDENT":
        conditions.append(
            "s.id IN (SELECT subject_id FROM enrollments WHERE student_id = %s AND status = 'ACTIVE')"
        )
        params.append(g.user_id)
        conditions.append("s.status = 'APPROVED'")
    elif g.role == "FACULTY":
        conditions.append("(s.author_id = %s OR s.status = 'APPROVED')")
        params.append(g.user_id)

    if search:
        conditions.append("(LOWER(s.name) LIKE LOWER(%s) OR LOWER(s.description) LIKE LOWER(%s))")
        params += [search, search]
    if status_filter and g.role == "ADMIN":
        conditions.append("s.status = %s")
        params.append(status_filter.upper())

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT s.id, s.name, s.description, s.color, s.status, s.weight, s.passing_rate,
               CONCAT(u.first_name,' ',u.last_name) AS author_name, s.author_id,
               s.date_created, s.last_updated,
               ROUND(AVG(ar.score::DECIMAL/NULLIF(ar.out_of,0)*100),2) AS weighted_score,
               COUNT(DISTINCT e.student_id) FILTER(WHERE e.status='ACTIVE') AS enrolled_students
        FROM subjects s
        LEFT JOIN users u ON s.author_id = u.id
        LEFT JOIN assessments a ON a.subject_id = s.id
        LEFT JOIN assessment_results ar ON ar.assessment_id = a.id
        LEFT JOIN enrollments e ON e.subject_id = s.id
        {where}
        GROUP BY s.id, u.first_name, u.last_name
        ORDER BY s.date_created DESC
    """
    return ok(paginate(sql, params, page, per_page))


@bp.get("/<subject_id>")
@login_required
def get_subject(subject_id):
    user_clause = ""
    params = [subject_id]
    if g.role == "STUDENT":
        user_clause = "AND s.id IN (SELECT subject_id FROM enrollments WHERE student_id = %s AND status='ACTIVE')"
        params.append(g.user_id)

    row = fetchone(f"SELECT * FROM v_subject_overview WHERE subject_id = %s {user_clause}", params)
    if not row:
        return not_found("Subject not found")
    return ok(row)


@bp.post("/")
@login_required
@roles_required("ADMIN", "FACULTY")
def create_subject():
    body = request.get_json(silent=True) or {}
    required = ["name"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    status = "DRAFT" if g.role == "FACULTY" else body.get("status", "DRAFT")
    row = execute_returning(
        """INSERT INTO subjects (name, description, color, weight, passing_rate, status, author_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        [body["name"], body.get("description"), body.get("color", "#1e40af"),
         body.get("weight", 0), body.get("passing_rate", 60), status, g.user_id]
    )
    return created(row)


@bp.put("/<subject_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def update_subject(subject_id):
    subject = fetchone("SELECT * FROM subjects WHERE id = %s", [subject_id])
    if not subject:
        return not_found()
    if g.role == "FACULTY" and str(subject["author_id"]) != g.user_id:
        from app.utils.responses import forbidden
        return forbidden("Not your subject")

    body = request.get_json(silent=True) or {}
    allowed = ["name", "description", "color", "weight", "passing_rate"]
    if g.role == "ADMIN":
        allowed += ["status"]

    updates, params = [], []
    for f in allowed:
        if f in body:
            updates.append(f"{f} = %s")
            params.append(body[f])
    if not updates:
        return error("Nothing to update")
    params.append(subject_id)
    execute(f"UPDATE subjects SET {', '.join(updates)} WHERE id = %s", params)
    return ok(message="Subject updated")


@bp.delete("/<subject_id>")
@login_required
@roles_required("ADMIN")
def archive_subject(subject_id):
    rows = execute("UPDATE subjects SET status = 'ARCHIVED' WHERE id = %s AND status != 'ARCHIVED'", [subject_id])
    if rows == 0:
        return not_found("Subject not found or already archived")
    return ok(message="Subject archived")


# ── Enrollment management ─────────────────────────────────────────────────────

@bp.get("/<subject_id>/enrollments")
@login_required
@roles_required("ADMIN", "FACULTY")
def get_enrollments(subject_id):
    page, per_page = get_page_params()
    sql = """
        SELECT e.id, e.student_id, CONCAT(u.first_name,' ',u.last_name) AS student_name,
               u.email, e.status, e.date_enrolled
        FROM enrollments e JOIN users u ON e.student_id = u.id
        WHERE e.subject_id = %s ORDER BY e.date_enrolled DESC
    """
    return ok(paginate(sql, [subject_id], page, per_page))


@bp.post("/<subject_id>/enrollments")
@login_required
@roles_required("ADMIN", "FACULTY")
def enroll_student(subject_id):
    body = request.get_json(silent=True) or {}
    student_id = body.get("student_id")
    if not student_id:
        return error("student_id required")

    student = fetchone("SELECT id FROM users u JOIN roles r ON u.role_id=r.id WHERE u.id=%s AND r.name='STUDENT'", [student_id])
    if not student:
        return not_found("Student not found")

    existing = fetchone("SELECT id, status FROM enrollments WHERE student_id=%s AND subject_id=%s", [student_id, subject_id])
    if existing:
        if existing["status"] == "ACTIVE":
            return error("Student already enrolled", 409)
        execute("UPDATE enrollments SET status='ACTIVE' WHERE id=%s", [existing["id"]])
        return ok(message="Enrollment reactivated")

    row = execute_returning(
        "INSERT INTO enrollments (student_id, subject_id) VALUES (%s,%s) RETURNING *",
        [student_id, subject_id]
    )
    return created(row, "Student enrolled")


@bp.delete("/<subject_id>/enrollments/<student_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def unenroll_student(subject_id, student_id):
    rows = execute(
        "UPDATE enrollments SET status='INACTIVE' WHERE student_id=%s AND subject_id=%s AND status='ACTIVE'",
        [student_id, subject_id]
    )
    if rows == 0:
        return not_found("Enrollment not found")
    return ok(message="Student unenrolled")
