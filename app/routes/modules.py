"""Modules CRUD within subjects."""
from flask import Blueprint, request, g
from app.db import fetchone, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, error, not_found, forbidden
from app.utils.pagination import get_page_params, get_search

bp = Blueprint("modules", __name__, url_prefix="/api/modules")


def _can_access_subject(subject_id):
    """Returns subject row if the current user may access it, else None."""
    if g.role == "STUDENT":
        return fetchone(
            "SELECT s.* FROM subjects s JOIN enrollments e ON e.subject_id=s.id "
            "WHERE s.id=%s AND e.student_id=%s AND e.status='ACTIVE' AND s.status='APPROVED'",
            [subject_id, g.user_id]
        )
    return fetchone("SELECT * FROM subjects WHERE id=%s", [subject_id])


@bp.get("/")
@login_required
def list_modules():
    """List modules, optionally filtered by subject."""
    page, per_page = get_page_params()
    search = get_search()
    subject_id = request.args.get("subject_id")

    conditions, params = [], []
    if subject_id:
        conditions.append("m.subject_id = %s")
        params.append(subject_id)
        if g.role == "STUDENT":
            conditions.append(
                "m.subject_id IN (SELECT subject_id FROM enrollments WHERE student_id=%s AND status='ACTIVE')"
            )
            params.append(g.user_id)
    elif g.role == "STUDENT":
        conditions.append(
            "m.subject_id IN (SELECT subject_id FROM enrollments WHERE student_id=%s AND status='ACTIVE')"
        )
        params.append(g.user_id)
    elif g.role == "FACULTY":
        conditions.append("(m.author_id=%s OR m.status='APPROVED')")
        params.append(g.user_id)

    if search:
        conditions.append("(LOWER(m.title) LIKE LOWER(%s) OR LOWER(m.format) LIKE LOWER(%s))")
        params += [search, search]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT m.id, m.subject_id, m.parent_id, m.title, m.format, m.status,
               m.file_name, m.file_url, m.date_created, m.last_updated,
               CONCAT(u.first_name,' ',u.last_name) AS author_name,
               s.name AS subject_name
        FROM modules m
        LEFT JOIN users u ON m.author_id = u.id
        LEFT JOIN subjects s ON m.subject_id = s.id
        {where}
        ORDER BY m.date_created DESC
    """
    return ok(paginate(sql, params, page, per_page))


@bp.get("/<module_id>")
@login_required
def get_module(module_id):
    row = fetchone(
        """SELECT m.*, CONCAT(u.first_name,' ',u.last_name) AS author_name, s.name AS subject_name
           FROM modules m
           LEFT JOIN users u ON m.author_id=u.id
           LEFT JOIN subjects s ON m.subject_id=s.id
           WHERE m.id=%s""",
        [module_id]
    )
    if not row:
        return not_found()
    if g.role == "STUDENT":
        enr = fetchone(
            "SELECT id FROM enrollments WHERE student_id=%s AND subject_id=%s AND status='ACTIVE'",
            [g.user_id, row["subject_id"]]
        )
        if not enr:
            return forbidden("Not enrolled in this subject")
    return ok(row)


@bp.post("/")
@login_required
@roles_required("ADMIN", "FACULTY")
def create_module():
    body = request.get_json(silent=True) or {}
    required = ["subject_id", "title"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    if not _can_access_subject(body["subject_id"]):
        return not_found("Subject not found")

    status = "DRAFT" if g.role == "FACULTY" else body.get("status", "DRAFT")
    row = execute_returning(
        """INSERT INTO modules (subject_id, parent_id, author_id, title, file_name,
                                file_url, content, format, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        [body["subject_id"], body.get("parent_id"), g.user_id, body["title"],
         body.get("file_name"), body.get("file_url"), body.get("content"),
         body.get("format", "PDF"), status]
    )
    return created(row)


@bp.put("/<module_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def update_module(module_id):
    mod = fetchone("SELECT * FROM modules WHERE id=%s", [module_id])
    if not mod:
        return not_found()
    if g.role == "FACULTY" and str(mod["author_id"]) != g.user_id:
        return forbidden("Not your module")

    body = request.get_json(silent=True) or {}
    allowed = ["title", "file_name", "file_url", "content", "format", "parent_id"]
    if g.role == "ADMIN":
        allowed.append("status")

    updates, params = [], []
    for f in allowed:
        if f in body:
            updates.append(f"{f} = %s")
            params.append(body[f])
    if not updates:
        return error("Nothing to update")
    params.append(module_id)
    execute(f"UPDATE modules SET {', '.join(updates)} WHERE id=%s", params)
    return ok(message="Module updated")


@bp.delete("/<module_id>")
@login_required
@roles_required("ADMIN")
def archive_module(module_id):
    rows = execute("UPDATE modules SET status='ARCHIVED' WHERE id=%s AND status!='ARCHIVED'", [module_id])
    if rows == 0:
        return not_found()
    return ok(message="Module archived")
