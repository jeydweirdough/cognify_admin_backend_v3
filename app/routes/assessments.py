"""
Assessment routes
  Admin:   /api/web/admin/assessments  — full CRUD
  Faculty: /api/web/faculty/assessments — direct CRUD (no staging)
  Mobile:  /api/mobile/student/assessments — list, fetch, submit
"""
import json
from psycopg2.extras import Json as PgJson
from fastapi import APIRouter, Request
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, permission_required, mobile_permission_required
from app.utils.responses import ok, created, no_content, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search, get_filter
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

admin_assess_router   = APIRouter(prefix="/api/web/admin/assessments",       tags=["admin-assessments"])
faculty_assess_router = APIRouter(prefix="/api/web/faculty/assessments",     tags=["faculty-assessments"])
mobile_assess_router  = APIRouter(prefix="/api/mobile/student/assessments",  tags=["mobile-assessments"])

VALID_TYPES    = {"PRE_ASSESSMENT", "QUIZ", "POST_ASSESSMENT"}

_SELECT = """
    SELECT a.*,
           s.name AS subject_name,
           m.title AS module_title,
           u.first_name || ' ' || u.last_name AS author_name
    FROM assessments a
    LEFT JOIN subjects s ON s.id = a.subject_id
    LEFT JOIN modules m   ON m.id = a.module_id
    LEFT JOIN users u    ON u.id = a.author_id
"""

_SELECT_WITH_Q = """
    SELECT a.*,
           s.name AS subject_name,
           m.title AS module_title,
           u.first_name || ' ' || u.last_name AS author_name,
           COALESCE(
               jsonb_agg(
                   jsonb_build_object(
                       'question_id', q.id,
                       'text', q.text,
                       'options', q.options,
                       'correct_answer', q.correct_answer,
                       'author_id', q.author_id,
                       'competency_codes', COALESCE(q.competency_codes, '[]'::jsonb)
                   ) ORDER BY q.date_created
               ) FILTER (WHERE q.id IS NOT NULL),
               '[]'::jsonb
           ) AS questions_list
    FROM assessments a
    LEFT JOIN subjects s ON s.id = a.subject_id
    LEFT JOIN modules m   ON m.id = a.module_id
    LEFT JOIN users u    ON u.id = a.author_id
    LEFT JOIN questions q ON q.assessment_id = a.id
"""


def _fmt(a: dict, include_questions=False) -> dict:
    a["id"] = str(a["id"])
    if a.get("subject_id"): a["subject_id"] = str(a["subject_id"])
    if a.get("module_id"):  a["module_id"]  = str(a["module_id"])
    if a.get("author_id"):  a["author_id"]  = str(a["author_id"])
    if include_questions:
        raw_qs = a.pop("questions_list", None) or a.pop("questions", None) or []
        if isinstance(raw_qs, str):
            raw_qs = json.loads(raw_qs)
        normalized = []
        for q in raw_qs:
            raw_codes = q.get("competency_codes", [])
            if isinstance(raw_codes, str):
                import json as _json
                try: raw_codes = _json.loads(raw_codes)
                except Exception: raw_codes = []
            normalized.append({
                "id":               str(q.get("question_id") or q.get("id", "")),
                "text":             q.get("text", ""),
                "options":          q.get("options", []),
                "correctAnswer":    q.get("correct_answer", q.get("correctAnswer", 0)),
                "mode":             q.get("mode", "MCQ"),
                "points":           q.get("points", 1),
                "competency_codes": raw_codes if isinstance(raw_codes, list) else [],
            })
        a["questions"] = normalized
    else:
        a.pop("questions_list", None)
        a.pop("questions", None)
    return a


def _list(request: Request, extra_where="", extra_params=None):
    page, per_page = get_page_params(request)
    search = get_search(request)
    atype  = get_filter(request, "type", VALID_TYPES)
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
    if subject_id:
        sql.append("AND a.subject_id = %s")
        params.append(subject_id)

    sql.append("ORDER BY a.created_at DESC")
    result = paginate(" ".join(sql), params, page, per_page)
    result["items"] = [_fmt(a) for a in result["items"]]
    return result


def _upsert_questions(assess_id: str, questions: list, author_id: str):
    incoming_ids = {
        str(q.get("id")) for q in questions
        if q.get("id") and not str(q.get("id", "")).startswith("q-")
    }
    existing_rows = fetchall("SELECT id FROM questions WHERE assessment_id = %s", [assess_id])
    existing_ids  = {str(r["id"]) for r in existing_rows}

    for qid in existing_ids - incoming_ids:
        execute("DELETE FROM questions WHERE id = %s", [qid])

    for q in questions:
        qid              = str(q.get("id", ""))
        text             = (q.get("text") or "").strip()
        options          = q.get("options", [])
        correct          = q.get("correctAnswer", q.get("correct_answer", 0))
        competency_codes = q.get("competency_codes", [])
        if not isinstance(competency_codes, list):
            competency_codes = []
        try:
            correct = int(correct)
        except (TypeError, ValueError):
            correct = 0

        if qid and not qid.startswith("q-") and qid in existing_ids:
            execute(
                """UPDATE questions
                      SET text = %s, options = %s, correct_answer = %s,
                          competency_codes = %s, last_updated = NOW()
                    WHERE id = %s""",
                [text, PgJson(options), correct, PgJson(competency_codes), qid],
            )
        else:
            execute_returning(
                """INSERT INTO questions
                       (assessment_id, author_id, text, options, correct_answer, competency_codes)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                [assess_id, author_id, text, PgJson(options), correct, PgJson(competency_codes)],
            )


def _fetch_with_questions(assess_id: str):
    return fetchone(
        _SELECT_WITH_Q + "WHERE a.id = %s GROUP BY a.id, s.name, m.title, u.first_name, u.last_name",
        [assess_id]
    )


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_assess_router.get("")
async def admin_list(request: Request):
    auth = permission_required("view_assessments")(request)
    return ok(_list(request))


@admin_assess_router.get("/{assess_id}")
async def admin_get(request: Request, assess_id: str):
    auth = permission_required("view_assessments")(request)
    a = _fetch_with_questions(assess_id)
    return ok(_fmt(a, include_questions=True)) if a else not_found()


@admin_assess_router.post("")
async def admin_create(request: Request):
    auth = permission_required("create_assessments")(request)
    try: body = await request.json()
    except Exception: body = {}
    return _create(body, auth)


@admin_assess_router.put("/{assess_id}")
async def admin_update(request: Request, assess_id: str):
    auth = permission_required("edit_assessments")(request)
    try: body = await request.json()
    except Exception: body = {}
    return _update(assess_id, body, auth)


@admin_assess_router.delete("/{assess_id}")
async def admin_delete(request: Request, assess_id: str):
    auth = permission_required("delete_assessments")(request)
    return _delete(assess_id, auth, only_own=False)


# ═══════════════════════════════════════════════════════════════
# FACULTY — direct CRUD, same as admin
# ═══════════════════════════════════════════════════════════════

@faculty_assess_router.get("")
async def faculty_list(request: Request):
    auth = permission_required("view_assessments")(request)
    return ok(_list(request))


@faculty_assess_router.get("/{assess_id}")
async def faculty_get(request: Request, assess_id: str):
    auth = permission_required("view_assessments")(request)
    a = _fetch_with_questions(assess_id)
    return ok(_fmt(a, include_questions=True)) if a else not_found()


@faculty_assess_router.post("")
async def faculty_create(request: Request):
    auth = permission_required("create_assessments")(request)
    try: body = await request.json()
    except Exception: body = {}
    return _create(body, auth)


@faculty_assess_router.put("/{assess_id}")
async def faculty_update(request: Request, assess_id: str):
    auth = permission_required("edit_assessments")(request)
    existing = fetchone("SELECT * FROM assessments WHERE id = %s", [assess_id])
    if not existing: return not_found()
    if str(existing["author_id"]) != auth.user_id:
        return forbidden("You can only edit your own assessments")
    try: body = await request.json()
    except Exception: body = {}
    return _update(assess_id, body, auth)


@faculty_assess_router.delete("/{assess_id}")
async def faculty_delete(request: Request, assess_id: str):
    auth = permission_required("delete_assessments")(request)
    return _delete(assess_id, auth, only_own=True)


# ═══════════════════════════════════════════════════════════════
# MOBILE — students take assessments
# ═══════════════════════════════════════════════════════════════

@mobile_assess_router.get("")
async def mobile_list(request: Request):
    auth = mobile_permission_required("mobile_view_assessments")(request)
    return ok(_list(request, "AND a.status = 'APPROVED'"))


@mobile_assess_router.get("/{assess_id}")
async def mobile_get(request: Request, assess_id: str):
    auth = mobile_permission_required("mobile_view_assessments")(request)
    a = fetchone(
        _SELECT_WITH_Q + "WHERE a.id = %s AND a.status = 'APPROVED' GROUP BY a.id, s.name, m.title, u.first_name, u.last_name",
        [assess_id]
    )
    if not a: return not_found()
    return ok(_fmt(a, include_questions=True))


@mobile_assess_router.post("/{assess_id}/submit")
async def mobile_submit(request: Request, assess_id: str):
    auth = mobile_permission_required("mobile_submit_assessment")(request)
    a = fetchone("SELECT * FROM assessments WHERE id = %s AND status = 'APPROVED'", [assess_id])
    if not a: return not_found("Assessment not found or not available")

    try: body = await request.json()
    except Exception: body = {}

    questions = fetchall(
        "SELECT id, text, options, correct_answer FROM questions WHERE assessment_id = %s ORDER BY date_created",
        [assess_id]
    )
    student_answers = {str(ans["question_id"]): ans["answer"] for ans in body.get("answers", [])}

    total   = len(questions)
    correct = 0
    scored_ans = []

    for q in questions:
        qid   = str(q["id"])
        given = student_answers.get(qid, "")
        opts  = q.get("options") or []
        if isinstance(opts, str):
            opts = json.loads(opts)
        correct_idx  = q.get("correct_answer", 0)
        correct_text = str(opts[correct_idx]) if 0 <= correct_idx < len(opts) else ""
        is_ok = str(given).strip().lower() == correct_text.strip().lower()
        correct += 1 if is_ok else 0
        scored_ans.append({"question_id": qid, "answer": given, "correct": is_ok})

    passing_row = fetchone("SELECT institutional_passing_grade FROM system_settings LIMIT 1")
    pass_grade  = (passing_row or {}).get("institutional_passing_grade", 75)
    score  = round((correct / total) * 100, 2) if total else 0
    passed = score >= pass_grade

    submission = execute_returning(
        "INSERT INTO assessment_results (assessment_id, user_id, score, total_items) VALUES (%s, %s, %s, %s) RETURNING id, date_taken",
        [assess_id, auth.user_id, correct, total],
    )
    log_action("Assessment submitted", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    return ok({
        "submission_id":  str(submission["id"]),
        "score":          score,
        "passed":         passed,
        "correct_count":  correct,
        "total_items":    total,
        "passing_grade":  pass_grade,
        "submitted_at":   submission["date_taken"].isoformat(),
    })


@mobile_assess_router.get("/{assess_id}/result")
async def mobile_result(request: Request, assess_id: str):
    auth = mobile_permission_required("mobile_view_assessments")(request)
    sub = fetchone(
        "SELECT * FROM assessment_results WHERE assessment_id = %s AND user_id = %s ORDER BY date_taken DESC LIMIT 1",
        [assess_id, auth.user_id],
    )
    if not sub: return not_found("No submission found")
    sub["id"] = str(sub["id"])
    return ok(sub)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _create(body: dict, auth):
    missing = require_fields(body, ["title", "type"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    atype = (body.get("type") or "").upper()
    if atype not in VALID_TYPES:
        return error(f"type must be one of: {', '.join(VALID_TYPES)}")

    questions = body.get("questions", [])

    a = execute_returning(
        "INSERT INTO assessments (title, type, subject_id, module_id, items, status, author_id) VALUES (%s, %s, %s, %s, %s, 'APPROVED', %s) RETURNING *",
        [
            clean_str(body["title"]),
            atype,
            body.get("subject_id") or None,
            body.get("module_id")  or None,
            len(questions),
            auth.user_id,
        ],
    )

    assess_id = str(a["id"])
    if questions:
        _upsert_questions(assess_id, questions, auth.user_id)

    log_action("Created assessment", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    full = _fetch_with_questions(assess_id)
    return created(_fmt(full or a, include_questions=True))


def _update(assess_id: str, body: dict, auth):
    existing = fetchone("SELECT * FROM assessments WHERE id = %s", [assess_id])
    if not existing: return not_found()

    questions  = body.get("questions", None)
    item_count = len(questions) if questions is not None else existing.get("items", 0)

    a = execute_returning(
        """UPDATE assessments
           SET title = %s, type = %s, subject_id = %s, module_id = %s,
               items = %s, status = 'APPROVED', updated_at = NOW()
           WHERE id = %s RETURNING *""",
        [
            clean_str(body.get("title", existing["title"])),
            (body.get("type", existing["type"]) or "").upper() or existing["type"],
            body.get("subject_id", existing.get("subject_id")),
            body.get("module_id",  existing.get("module_id")),
            item_count,
            assess_id,
        ],
    )

    if questions is not None:
        _upsert_questions(assess_id, questions, auth.user_id)

    log_action("Updated assessment", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    full = _fetch_with_questions(assess_id)
    return ok(_fmt(full or a, include_questions=True))


def _delete(assess_id: str, auth, only_own: bool):
    a = fetchone("SELECT author_id, title, status FROM assessments WHERE id = %s", [assess_id])
    if not a: return not_found()
    if only_own and str(a["author_id"]) != auth.user_id:
        return forbidden("You can only delete your own assessments")
    execute("DELETE FROM assessments WHERE id = %s", [assess_id])
    log_action("Deleted assessment", a["title"], assess_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()
