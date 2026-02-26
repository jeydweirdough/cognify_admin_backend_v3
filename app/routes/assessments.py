"""Assessments CRUD + question linking."""
from flask import Blueprint, request, g
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search

bp = Blueprint("assessments", __name__, url_prefix="/api/assessments")


@bp.get("/")
@login_required
def list_assessments():
    page, per_page = get_page_params()
    search = get_search()
    subject_id = request.args.get("subject_id")
    type_filter = request.args.get("type")

    conditions, params = [], []

    if g.role == "STUDENT":
        conditions.append(
            "a.subject_id IN (SELECT subject_id FROM enrollments WHERE student_id=%s AND status='ACTIVE')"
        )
        params.append(g.user_id)
        conditions.append("a.status = 'APPROVED'")
    elif g.role == "FACULTY":
        conditions.append("(a.author_id=%s OR a.status='APPROVED')")
        params.append(g.user_id)

    if subject_id:
        conditions.append("a.subject_id = %s")
        params.append(subject_id)
    if type_filter:
        conditions.append("a.type = %s")
        params.append(type_filter.upper())
    if search:
        conditions.append("LOWER(a.title) LIKE LOWER(%s)")
        params.append(search)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT a.id, a.title, a.type, a.items AS declared_items,
               COUNT(DISTINCT aq.question_id) AS actual_question_count,
               a.time_limit, a.schedule, a.status, a.author_id,
               CONCAT(u.first_name,' ',u.last_name) AS author_name,
               s.id AS subject_id, s.name AS subject_name,
               a.date_created, a.last_updated,
               COUNT(DISTINCT ar.student_id) AS students_attempted
        FROM assessments a
        LEFT JOIN subjects s ON a.subject_id=s.id
        LEFT JOIN users u ON a.author_id=u.id
        LEFT JOIN assessment_questions aq ON aq.assessment_id=a.id
        LEFT JOIN assessment_results ar ON ar.assessment_id=a.id
        {where}
        GROUP BY a.id, s.id, u.first_name, u.last_name
        ORDER BY a.date_created DESC
    """
    return ok(paginate(sql, params, page, per_page))


@bp.get("/<assessment_id>")
@login_required
def get_assessment(assessment_id):
    row = fetchone("SELECT * FROM v_assessment_detail WHERE assessment_id=%s", [assessment_id])
    if not row:
        return not_found()
    # Students: hide correct_answer in questions
    if g.role == "STUDENT":
        if isinstance(row.get("questions"), list):
            for q in row["questions"]:
                q.pop("correct_answer", None)
    return ok(row)


@bp.post("/")
@login_required
@roles_required("ADMIN", "FACULTY")
def create_assessment():
    body = request.get_json(silent=True) or {}
    required = ["subject_id", "title", "type"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    valid_types = ["PRE_ASSESSMENT", "POST_ASSESSMENT", "QUIZ", "EXAM", "ACTIVITY"]
    if body["type"].upper() not in valid_types:
        return error(f"Invalid type. Allowed: {', '.join(valid_types)}")

    status = "DRAFT" if g.role == "FACULTY" else body.get("status", "DRAFT")
    row = execute_returning(
        """INSERT INTO assessments (subject_id, author_id, title, type, items,
                                   time_limit, schedule, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        [body["subject_id"], g.user_id, body["title"], body["type"].upper(),
         body.get("items", 0), body.get("time_limit", 15), body.get("schedule"),
         status]
    )
    return created(row)


@bp.put("/<assessment_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def update_assessment(assessment_id):
    assessment = fetchone("SELECT * FROM assessments WHERE id=%s", [assessment_id])
    if not assessment:
        return not_found()
    if g.role == "FACULTY" and str(assessment["author_id"]) != g.user_id:
        return forbidden("Not your assessment")

    body = request.get_json(silent=True) or {}
    allowed = ["title", "type", "items", "time_limit", "schedule"]
    if g.role == "ADMIN":
        allowed.append("status")

    updates, params = [], []
    for f in allowed:
        if f in body:
            updates.append(f"{f} = %s")
            params.append(body[f])
    if not updates:
        return error("Nothing to update")
    params.append(assessment_id)
    execute(f"UPDATE assessments SET {', '.join(updates)} WHERE id=%s", params)
    return ok(message="Assessment updated")


@bp.delete("/<assessment_id>")
@login_required
@roles_required("ADMIN")
def archive_assessment(assessment_id):
    rows = execute(
        "UPDATE assessments SET status='ARCHIVED' WHERE id=%s AND status!='ARCHIVED'",
        [assessment_id]
    )
    if rows == 0:
        return not_found()
    return ok(message="Assessment archived")


# ── Question linking ──────────────────────────────────────────────────────────

@bp.post("/<assessment_id>/questions")
@login_required
@roles_required("ADMIN", "FACULTY")
def add_questions(assessment_id):
    """Link existing questions to this assessment."""
    body = request.get_json(silent=True) or {}
    question_ids = body.get("question_ids", [])
    if not question_ids:
        return error("question_ids list required")

    assessment = fetchone("SELECT * FROM assessments WHERE id=%s", [assessment_id])
    if not assessment:
        return not_found()

    added = 0
    for qid in question_ids:
        try:
            execute(
                "INSERT INTO assessment_questions (assessment_id, question_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                [assessment_id, qid]
            )
            added += 1
        except Exception:
            pass
    return ok({"added": added}, "Questions linked")


@bp.delete("/<assessment_id>/questions/<question_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def remove_question(assessment_id, question_id):
    rows = execute(
        "DELETE FROM assessment_questions WHERE assessment_id=%s AND question_id=%s",
        [assessment_id, question_id]
    )
    if rows == 0:
        return not_found("Question not linked to this assessment")
    return ok(message="Question removed from assessment")


# ── Results ───────────────────────────────────────────────────────────────────

@bp.get("/<assessment_id>/results")
@login_required
def get_results(assessment_id):
    if g.role == "STUDENT":
        rows = fetchall(
            "SELECT * FROM assessment_results WHERE assessment_id=%s AND student_id=%s ORDER BY attempt_number",
            [assessment_id, g.user_id]
        )
    else:
        rows = fetchall(
            """SELECT ar.*, CONCAT(u.first_name,' ',u.last_name) AS student_name
               FROM assessment_results ar JOIN users u ON u.id=ar.student_id
               WHERE ar.assessment_id=%s ORDER BY ar.date_taken DESC""",
            [assessment_id]
        )
    return ok(rows)


@bp.post("/<assessment_id>/results")
@login_required
@roles_required("STUDENT")
def submit_result(assessment_id):
    body = request.get_json(silent=True) or {}
    score = body.get("score")
    out_of = body.get("out_of")
    if score is None or out_of is None:
        return error("score and out_of required")

    last = fetchone(
        "SELECT MAX(attempt_number) AS last FROM assessment_results WHERE assessment_id=%s AND student_id=%s",
        [assessment_id, g.user_id]
    )
    attempt = (last["last"] or 0) + 1

    row = execute_returning(
        """INSERT INTO assessment_results (assessment_id, student_id, score, out_of, attempt_number)
           VALUES (%s,%s,%s,%s,%s) RETURNING *""",
        [assessment_id, g.user_id, score, out_of, attempt]
    )
    return created(row, "Result recorded")
