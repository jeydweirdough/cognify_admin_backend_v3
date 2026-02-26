"""Question bank CRUD."""
from flask import Blueprint, request, g
from app.db import fetchone, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search

bp = Blueprint("questions", __name__, url_prefix="/api/questions")


@bp.get("/")
@login_required
@roles_required("ADMIN", "FACULTY")
def list_questions():
    page, per_page = get_page_params()
    search = get_search()
    conditions, params = [], []

    if g.role == "FACULTY":
        conditions.append("q.author_id = %s")
        params.append(g.user_id)
    if search:
        conditions.append("LOWER(q.text) LIKE LOWER(%s)")
        params.append(search)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT q.id, LEFT(q.text,120) AS text_preview, q.options, q.correct_answer,
               q.date_created, q.last_updated,
               CONCAT(u.first_name,' ',u.last_name) AS author_name
        FROM questions q
        LEFT JOIN users u ON q.author_id=u.id
        {where}
        ORDER BY q.date_created DESC
    """
    return ok(paginate(sql, params, page, per_page))


@bp.get("/<question_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def get_question(question_id):
    row = fetchone(
        """SELECT q.*, CONCAT(u.first_name,' ',u.last_name) AS author_name
           FROM questions q LEFT JOIN users u ON q.author_id=u.id WHERE q.id=%s""",
        [question_id]
    )
    if not row:
        return not_found()
    return ok(row)


@bp.post("/")
@login_required
@roles_required("ADMIN", "FACULTY")
def create_question():
    body = request.get_json(silent=True) or {}
    required = ["text", "options", "correct_answer"]
    missing = [f for f in required if body.get(f) is None]
    if missing:
        return error(f"Missing: {', '.join(missing)}")
    if not isinstance(body["options"], list) or len(body["options"]) < 2:
        return error("options must be a list with at least 2 items")
    if not (0 <= int(body["correct_answer"]) < len(body["options"])):
        return error("correct_answer index out of range")

    import json
    row = execute_returning(
        "INSERT INTO questions (author_id, text, options, correct_answer) VALUES (%s,%s,%s,%s) RETURNING *",
        [g.user_id, body["text"], json.dumps(body["options"]), int(body["correct_answer"])]
    )
    return created(row)


@bp.put("/<question_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def update_question(question_id):
    q = fetchone("SELECT * FROM questions WHERE id=%s", [question_id])
    if not q:
        return not_found()
    if g.role == "FACULTY" and str(q["author_id"]) != g.user_id:
        return forbidden("Not your question")

    body = request.get_json(silent=True) or {}
    updates, params = [], []
    import json
    if "text" in body:
        updates.append("text = %s"); params.append(body["text"])
    if "options" in body:
        updates.append("options = %s"); params.append(json.dumps(body["options"]))
    if "correct_answer" in body:
        updates.append("correct_answer = %s"); params.append(int(body["correct_answer"]))
    if not updates:
        return error("Nothing to update")
    params.append(question_id)
    execute(f"UPDATE questions SET {', '.join(updates)} WHERE id=%s", params)
    return ok(message="Question updated")


@bp.delete("/<question_id>")
@login_required
@roles_required("ADMIN")
def delete_question(question_id):
    rows = execute("DELETE FROM questions WHERE id=%s", [question_id])
    if rows == 0:
        return not_found()
    return ok(message="Question deleted")
