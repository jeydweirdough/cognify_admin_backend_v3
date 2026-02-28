"""
Assessment routes
  Admin:   /api/web/admin/assessments  — CRUD + approve/reject
  Faculty: /api/web/faculty/assessments — CRUD (own only, pending flow)
  Mobile:  /api/mobile/student/assessments — list, fetch, submit
"""
import json
from fastapi import APIRouter, Request
from app.db import fetchone, execute, execute_returning, paginate
from app.middleware.auth import login_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

admin_assess_router   = APIRouter(prefix="/api/web/admin/assessments",       tags=["admin-assessments"])
faculty_assess_router = APIRouter(prefix="/api/web/faculty/assessments",     tags=["faculty-assessments"])
mobile_assess_router  = APIRouter(prefix="/api/mobile/student/assessments",  tags=["mobile-assessments"])

VALID_TYPES    = {"PRE_ASSESSMENT", "QUIZ", "POST_ASSESSMENT"}
VALID_STATUSES = {"DRAFT", "PENDING", "APPROVED", "REJECTED", "REVISION_REQUESTED"}

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


def _list(request: Request, extra_where="", extra_params=None):
    page, per_page = get_page_params(request)
    search = get_search(request)
    atype  = get_filter(request, "type", VALID_TYPES)
    status = get_filter(request, "status", VALID_STATUSES)
    subject_id = (request.query_params.get("subject_id") or "").strip() or None

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

@admin_assess_router.get("")
async def admin_list(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return ok(_list(request))


@admin_assess_router.get("/{assess_id}")
async def admin_get(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    a = fetchone(_SELECT + "WHERE a.id = %s", [assess_id])
    return ok(_fmt(a, include_questions=True)) if a else not_found()


@admin_assess_router.post("")
async def admin_create(request: Request):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _create(body, auth, auto_approve=True)


@admin_assess_router.put("/{assess_id}")
async def admin_update(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update(assess_id, body, auth, can_approve=True)


@admin_assess_router.patch("/{assess_id}/status")
async def admin_update_status(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = (body.get("status") or "").upper()
    if action not in {"APPROVED", "REJECTED", "REVISION_REQUESTED"}:
        return error("status must be APPROVED, REJECTED, or REVISION_REQUESTED")
    a = fetchone("SELECT id, title FROM assessments WHERE id = %s", [assess_id])
    if not a: return not_found()
    execute("UPDATE assessments SET status = %s WHERE id = %s", [action, assess_id])
    log_action(f"Assessment {action.lower()}", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"id": assess_id, "status": action})


@admin_assess_router.delete("/{assess_id}")
async def admin_delete(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "ADMIN": return forbidden()
    return _delete(assess_id, auth, only_own=False)


# ═══════════════════════════════════════════════════════════════
# FACULTY
# ═══════════════════════════════════════════════════════════════

@faculty_assess_router.get("")
async def faculty_list(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    return ok(_list(request, "AND (a.author_id = %s OR a.status = 'APPROVED')", [auth.user_id]))


@faculty_assess_router.get("/{assess_id}")
async def faculty_get(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    a = fetchone(_SELECT + "WHERE a.id = %s AND (a.author_id = %s OR a.status = 'APPROVED')",
                 [assess_id, auth.user_id])
    return ok(_fmt(a, include_questions=True)) if a else not_found()


@faculty_assess_router.post("")
async def faculty_create(request: Request):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _create(body, auth, auto_approve=False)


@faculty_assess_router.put("/{assess_id}")
async def faculty_update(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    existing = fetchone("SELECT author_id FROM assessments WHERE id = %s", [assess_id])
    if not existing: return not_found()
    if str(existing["author_id"]) != auth.user_id:
        return forbidden("You can only edit your own assessments")
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _update(assess_id, body, auth, can_approve=False)


@faculty_assess_router.patch("/{assess_id}/submit")
async def faculty_submit(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    a = fetchone("SELECT id, title, author_id FROM assessments WHERE id = %s", [assess_id])
    if not a: return not_found()
    if str(a["author_id"]) != auth.user_id: return forbidden()
    execute("UPDATE assessments SET status = 'PENDING' WHERE id = %s", [assess_id])
    log_action("Submitted assessment for review", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    return ok({"id": assess_id, "status": "PENDING"})


@faculty_assess_router.delete("/{assess_id}")
async def faculty_delete(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "FACULTY": return forbidden()
    return _delete(assess_id, auth, only_own=True)


# ═══════════════════════════════════════════════════════════════
# MOBILE — students take assessments
# ═══════════════════════════════════════════════════════════════

@mobile_assess_router.get("")
async def mobile_list(request: Request):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    return ok(_list(request, "AND a.status = 'APPROVED'"))


@mobile_assess_router.get("/{assess_id}")
async def mobile_get(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    a = fetchone(_SELECT + "WHERE a.id = %s AND a.status = 'APPROVED'", [assess_id])
    if not a: return not_found()
    return ok(_fmt(a, include_questions=True))


@mobile_assess_router.post("/{assess_id}/submit")
async def mobile_submit(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    a = fetchone("SELECT * FROM assessments WHERE id = %s AND status = 'APPROVED'", [assess_id])
    if not a: return not_found("Assessment not found or not available")

    try:
        body = await request.json()
    except Exception:
        body = {}
    student_answers = {str(ans["question_id"]): ans["answer"] for ans in body.get("answers", [])}
    time_taken = body.get("time_taken_s") or body.get("timeTakenSeconds")

    questions = a["questions"] or []
    total = len(questions)
    correct = 0
    scored_ans = []

    for q in questions:
        qid   = str(q["id"])
        given = student_answers.get(qid, "")
        is_ok = str(given).strip().lower() == str(q.get("answer", "")).strip().lower()
        correct += 1 if is_ok else 0
        scored_ans.append({"question_id": qid, "answer": given, "correct": is_ok})

    passing_row = fetchone("SELECT institutional_passing_grade FROM system_settings LIMIT 1")
    pass_grade  = (passing_row or {}).get("institutional_passing_grade", 75)
    score  = round((correct / total) * 100, 2) if total else 0
    passed = score >= pass_grade

    submission = execute_returning(
        """INSERT INTO assessment_submissions
               (assessment_id, student_id, score, passed, correct, total, answers, time_taken_s)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, submitted_at""",
        [assess_id, auth.user_id, score, passed, correct, total, json.dumps(scored_ans), time_taken],
    )
    log_action("Assessment submitted", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    return ok({
        "submission_id":  str(submission["id"]),
        "score":          score,
        "passed":         passed,
        "correct_count":  correct,
        "total_items":    total,
        "passing_grade":  pass_grade,
        "submitted_at":   submission["submitted_at"].isoformat(),
    })


@mobile_assess_router.get("/{assess_id}/result")
async def mobile_result(request: Request, assess_id: str):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    sub = fetchone(
        """SELECT * FROM assessment_submissions
           WHERE assessment_id = %s AND student_id = %s
           ORDER BY submitted_at DESC LIMIT 1""",
        [assess_id, auth.user_id],
    )
    if not sub: return not_found("No submission found")
    sub["id"] = str(sub["id"])
    return ok(sub)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _create(body: dict, auth, auto_approve: bool):
    missing = require_fields(body, ["title", "type"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    atype = (body.get("type") or "").upper()
    if atype not in VALID_TYPES:
        return error(f"type must be one of: {', '.join(VALID_TYPES)}")

    status    = "APPROVED" if auto_approve else (body.get("status") or "DRAFT").upper()
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
            auth.user_id,
        ],
    )
    log_action("Created assessment", a["title"], str(a["id"]), user_id=auth.user_id, ip=auth.ip)
    return created(_fmt(a, include_questions=True))


def _update(assess_id: str, body: dict, auth, can_approve: bool):
    existing = fetchone("SELECT * FROM assessments WHERE id = %s", [assess_id])
    if not existing: return not_found()

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
    log_action("Updated assessment", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_fmt(a, include_questions=True))


def _delete(assess_id: str, auth, only_own: bool):
    a = fetchone("SELECT author_id, title, status FROM assessments WHERE id = %s", [assess_id])
    if not a: return not_found()
    if only_own and str(a["author_id"]) != auth.user_id:
        return forbidden("You can only delete your own assessments")
    if a["status"] == "APPROVED":
        return error("Cannot delete an approved assessment", 409)
    execute("DELETE FROM assessments WHERE id = %s", [assess_id])
    log_action("Deleted assessment", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()
