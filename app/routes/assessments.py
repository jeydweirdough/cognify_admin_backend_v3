"""
Assessment routes
  Admin:   /api/web/admin/assessments  — CRUD + approve/reject
  Faculty: /api/web/faculty/assessments — CRUD (own only, pending flow)
  Mobile:  /api/mobile/student/assessments — list, fetch, submit
"""
import json
from flask import Blueprint, request, g
from app.db import fetchone, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

admin_assess_bp   = Blueprint("admin_assess",   __name__, url_prefix="/api/web/admin/assessments")
faculty_assess_bp = Blueprint("faculty_assess", __name__, url_prefix="/api/web/faculty/assessments")
mobile_assess_bp  = Blueprint("mobile_assess",  __name__, url_prefix="/api/mobile/student/assessments")

VALID_TYPES    = {"PRE_ASSESSMENT", "QUIZ", "POST_ASSESSMENT"}
VALID_STATUSES = {"DRAFT", "PENDING", "APPROVED", "REJECTED", "REVISION_REQUESTED"}

# ── Shared helpers ────────────────────────────────────────────────────────────

_SELECT = """
    SELECT a.*,
           s.name AS subject_name,
           t.title AS topic_title,
           u.first_name || ' ' || u.last_name AS author_name
    FROM assessments a
    LEFT JOIN subjects s ON s.id = a.subject_id
    LEFT JOIN topics t   ON t.id = a.topic_id
    LEFT JOIN users u    ON u.id = a.author_id
"""

def _fmt(a: dict, include_questions=False) -> dict:
    a["id"] = str(a["id"])
    if a.get("subject_id"): a["subject_id"] = str(a["subject_id"])
    if a.get("topic_id"):   a["topic_id"]   = str(a["topic_id"])
    if a.get("author_id"):  a["author_id"]  = str(a["author_id"])
    if not include_questions:
        a.pop("questions", None)
    return a


def _list(extra_where="", extra_params=None):
    page, per_page = get_page_params()
    search = get_search()
    atype  = get_filter("type", VALID_TYPES)
    status = get_filter("status", VALID_STATUSES)
    subject_id = (request.args.get("subject_id") or "").strip() or None

    sql    = [_SELECT, "WHERE 1=1"]
    params = []

    if extra_where:
        sql.append(extra_where)
        params += (extra_params or [])

    if search:
        sql.append("AND LOWER(a.title) LIKE LOWER(%s)")
        params.append(search)

    if atype:
        sql.append("AND a.type = %s")
        params.append(atype)

    if status:
        sql.append("AND a.status = %s")
        params.append(status)

    if subject_id:
        sql.append("AND a.subject_id = %s")
        params.append(subject_id)

    sql.append("ORDER BY a.created_at DESC")
    result = paginate(" ".join(sql), params, page, per_page)
    result["items"] = [_fmt(a) for a in result["items"]]
    return result


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_assess_bp.get("")
@login_required
@roles_required("ADMIN")
def admin_list():
    return ok(_list())


@admin_assess_bp.get("/<assess_id>")
@login_required
@roles_required("ADMIN")
def admin_get(assess_id):
    a = fetchone(_SELECT + "WHERE a.id = %s", [assess_id])
    return ok(_fmt(a, include_questions=True)) if a else not_found()


@admin_assess_bp.post("")
@login_required
@roles_required("ADMIN")
def admin_create():
    return _create(auto_approve=True)


@admin_assess_bp.put("/<assess_id>")
@login_required
@roles_required("ADMIN")
def admin_update(assess_id):
    return _update(assess_id, can_approve=True)


@admin_assess_bp.patch("/<assess_id>/status")
@login_required
@roles_required("ADMIN")
def admin_update_status(assess_id):
    body   = request.get_json(silent=True) or {}
    action = (body.get("status") or "").upper()
    if action not in {"APPROVED", "REJECTED", "REVISION_REQUESTED"}:
        return error("status must be APPROVED, REJECTED, or REVISION_REQUESTED")
    a = fetchone("SELECT id, title FROM assessments WHERE id = %s", [assess_id])
    if not a:
        return not_found()
    execute("UPDATE assessments SET status = %s WHERE id = %s", [action, assess_id])
    log_action(f"Assessment {action.lower()}", a["title"], assess_id)
    return ok({"id": assess_id, "status": action})


@admin_assess_bp.delete("/<assess_id>")
@login_required
@roles_required("ADMIN")
def admin_delete(assess_id):
    return _delete(assess_id, only_own=False)


# ═══════════════════════════════════════════════════════════════
# FACULTY
# ═══════════════════════════════════════════════════════════════

@faculty_assess_bp.get("")
@login_required
@roles_required("FACULTY")
def faculty_list():
    return ok(_list("AND (a.author_id = %s OR a.status = 'APPROVED')", [g.user_id]))


@faculty_assess_bp.get("/<assess_id>")
@login_required
@roles_required("FACULTY")
def faculty_get(assess_id):
    a = fetchone(_SELECT + "WHERE a.id = %s AND (a.author_id = %s OR a.status = 'APPROVED')",
                 [assess_id, g.user_id])
    return ok(_fmt(a, include_questions=True)) if a else not_found()


@faculty_assess_bp.post("")
@login_required
@roles_required("FACULTY")
def faculty_create():
    return _create(auto_approve=False)


@faculty_assess_bp.put("/<assess_id>")
@login_required
@roles_required("FACULTY")
def faculty_update(assess_id):
    existing = fetchone("SELECT author_id FROM assessments WHERE id = %s", [assess_id])
    if not existing:
        return not_found()
    if str(existing["author_id"]) != g.user_id:
        return forbidden("You can only edit your own assessments")
    return _update(assess_id, can_approve=False)


@faculty_assess_bp.patch("/<assess_id>/submit")
@login_required
@roles_required("FACULTY")
def faculty_submit(assess_id):
    a = fetchone("SELECT id, title, author_id FROM assessments WHERE id = %s", [assess_id])
    if not a:
        return not_found()
    if str(a["author_id"]) != g.user_id:
        return forbidden()
    execute("UPDATE assessments SET status = 'PENDING' WHERE id = %s", [assess_id])
    log_action("Submitted assessment for review", a["title"], assess_id)
    return ok({"id": assess_id, "status": "PENDING"})


@faculty_assess_bp.delete("/<assess_id>")
@login_required
@roles_required("FACULTY")
def faculty_delete(assess_id):
    return _delete(assess_id, only_own=True)


# ═══════════════════════════════════════════════════════════════
# MOBILE — students take assessments
# ═══════════════════════════════════════════════════════════════

@mobile_assess_bp.get("")
@login_required
@roles_required("STUDENT")
def mobile_list():
    return ok(_list("AND a.status = 'APPROVED'"))


@mobile_assess_bp.get("/<assess_id>")
@login_required
@roles_required("STUDENT")
def mobile_get(assess_id):
    a = fetchone(_SELECT + "WHERE a.id = %s AND a.status = 'APPROVED'", [assess_id])
    if not a:
        return not_found()
    return ok(_fmt(a, include_questions=True))


@mobile_assess_bp.post("/<assess_id>/submit")
@login_required
@roles_required("STUDENT")
def mobile_submit(assess_id):
    """Grade a student's assessment submission."""
    a = fetchone("SELECT * FROM assessments WHERE id = %s AND status = 'APPROVED'", [assess_id])
    if not a:
        return not_found("Assessment not found or not available")

    body = request.get_json(silent=True) or {}
    student_answers = {str(ans["question_id"]): ans["answer"] for ans in body.get("answers", [])}
    time_taken = body.get("time_taken_s") or body.get("timeTakenSeconds")

    questions  = a["questions"] or []
    total      = len(questions)
    correct    = 0
    scored_ans = []

    for q in questions:
        qid    = str(q["id"])
        given  = student_answers.get(qid, "")
        is_ok  = str(given).strip().lower() == str(q.get("answer", "")).strip().lower()
        correct += 1 if is_ok else 0
        scored_ans.append({"question_id": qid, "answer": given, "correct": is_ok})

    passing_row = fetchone("SELECT institutional_passing_grade FROM system_settings LIMIT 1")
    pass_grade  = (passing_row or {}).get("institutional_passing_grade", 75)
    score       = round((correct / total) * 100, 2) if total else 0
    passed      = score >= pass_grade

    submission = execute_returning(
        """INSERT INTO assessment_submissions
               (assessment_id, student_id, score, passed, correct, total, answers, time_taken_s)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, submitted_at""",
        [assess_id, g.user_id, score, passed, correct, total,
         json.dumps(scored_ans), time_taken],
    )
    log_action("Assessment submitted", a["title"], assess_id)
    return ok({
        "submission_id":   str(submission["id"]),
        "score":           score,
        "passed":          passed,
        "correct_count":   correct,
        "total_items":     total,
        "passing_grade":   pass_grade,
        "submitted_at":    submission["submitted_at"].isoformat(),
    })


@mobile_assess_bp.get("/<assess_id>/result")
@login_required
@roles_required("STUDENT")
def mobile_result(assess_id):
    """Get the most recent result for a student on this assessment."""
    sub = fetchone(
        """SELECT * FROM assessment_submissions
           WHERE assessment_id = %s AND student_id = %s
           ORDER BY submitted_at DESC LIMIT 1""",
        [assess_id, g.user_id],
    )
    if not sub:
        return not_found("No submission found")
    sub["id"] = str(sub["id"])
    return ok(sub)


# ── Shared create / update / delete ───────────────────────────────────────────

def _create(auto_approve: bool):
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, ["title", "type"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    atype = (body.get("type") or "").upper()
    if atype not in VALID_TYPES:
        return error(f"type must be one of: {', '.join(VALID_TYPES)}")

    status = "APPROVED" if auto_approve else (body.get("status") or "DRAFT").upper()
    questions = body.get("questions", [])

    a = execute_returning(
        """INSERT INTO assessments
               (title, type, subject_id, topic_id, questions, items, status, author_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        [
            clean_str(body["title"]),
            atype,
            body.get("subject_id") or None,
            body.get("topic_id")   or None,
            json.dumps(questions),
            len(questions),
            status,
            g.user_id,
        ],
    )
    log_action("Created assessment", a["title"], str(a["id"]))
    return created(_fmt(a, include_questions=True))


def _update(assess_id: str, can_approve: bool):
    existing = fetchone("SELECT * FROM assessments WHERE id = %s", [assess_id])
    if not existing:
        return not_found()
    body = request.get_json(silent=True) or {}

    new_status = (body.get("status") or existing["status"]).upper()
    if not can_approve and new_status == "APPROVED":
        new_status = "PENDING"

    questions = body.get("questions", existing["questions"] or [])
    a = execute_returning(
        """UPDATE assessments
           SET title = %s, type = %s, subject_id = %s, topic_id = %s,
               questions = %s, items = %s, status = %s
           WHERE id = %s RETURNING *""",
        [
            clean_str(body.get("title", existing["title"])),
            (body.get("type", existing["type"]) or "").upper() or existing["type"],
            body.get("subject_id", existing.get("subject_id")),
            body.get("topic_id",   existing.get("topic_id")),
            json.dumps(questions),
            len(questions),
            new_status,
            assess_id,
        ],
    )
    log_action("Updated assessment", a["title"], assess_id)
    return ok(_fmt(a, include_questions=True))


def _delete(assess_id: str, only_own: bool):
    a = fetchone("SELECT author_id, title, status FROM assessments WHERE id = %s", [assess_id])
    if not a:
        return not_found()
    if only_own and str(a["author_id"]) != g.user_id:
        return forbidden("You can only delete your own assessments")
    if a["status"] == "APPROVED":
        return error("Cannot delete an approved assessment", 409)
    execute("DELETE FROM assessments WHERE id = %s", [assess_id])
    log_action("Deleted assessment", a["title"], assess_id)
    return no_content()