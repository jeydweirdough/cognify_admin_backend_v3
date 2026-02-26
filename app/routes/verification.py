"""Verification / request-changes workflow (ADMIN review queue)."""
from flask import Blueprint, request, g
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, error, not_found
from app.utils.pagination import get_page_params

bp = Blueprint("verification", __name__, url_prefix="/api/verification")

VALID_CATEGORIES = {"SUBJECT", "MODULE", "ASSESSMENT", "QUESTION"}
VALID_TYPES = {"ADD", "UPDATE", "REMOVE"}


@bp.get("/summary")
@login_required
@roles_required("ADMIN")
def summary():
    row = fetchone("SELECT * FROM v_verification_summary")
    return ok(row)


@bp.get("/queue")
@login_required
@roles_required("ADMIN")
def queue():
    page, per_page = get_page_params()
    category = request.args.get("category", "").upper()
    status_filter = request.args.get("status", "PENDING").upper()

    conditions = [f"rc.status = '{status_filter}'"]
    params = []
    if category and category in VALID_CATEGORIES:
        conditions.append("rc.category = %s")
        params.append(category)

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT rc.id AS request_id, rc.author_id,
               CONCAT(u.first_name,' ',u.last_name) AS requested_by,
               rc.type AS change_type, rc.category, rc.status AS request_status,
               rc.date_created, rc.last_updated, rc.revision_id,
               rev.status AS revision_status, rev.note AS revision_note
        FROM request_changes rc
        LEFT JOIN users u ON rc.author_id=u.id
        LEFT JOIN revisions rev ON rc.revision_id=rev.id
        {where}
        ORDER BY rc.date_created DESC
    """
    return ok(paginate(sql, params, page, per_page))


@bp.get("/<request_id>")
@login_required
@roles_required("ADMIN", "FACULTY")
def get_request(request_id):
    if g.role == "FACULTY":
        row = fetchone("SELECT * FROM v_review_detail WHERE request_id=%s AND requester_id=%s",
                       [request_id, g.user_id])
    else:
        row = fetchone("SELECT * FROM v_review_detail WHERE request_id=%s", [request_id])
    if not row:
        return not_found()
    return ok(row)


@bp.post("/")
@login_required
@roles_required("FACULTY", "ADMIN")
def submit_request():
    body = request.get_json(silent=True) or {}
    required = ["category", "type", "target_id"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return error(f"Missing: {', '.join(missing)}")
    if body["category"].upper() not in VALID_CATEGORIES:
        return error(f"Invalid category. Allowed: {', '.join(VALID_CATEGORIES)}")
    if body["type"].upper() not in VALID_TYPES:
        return error(f"Invalid type. Allowed: {', '.join(VALID_TYPES)}")

    import json
    changes_summary = json.dumps({
        "target_id": body["target_id"],
        "changes": body.get("changes", [])
    })
    row = execute_returning(
        """INSERT INTO request_changes (author_id, changes_summary, type, category, status)
           VALUES (%s,%s::jsonb,%s,%s,'PENDING') RETURNING *""",
        [g.user_id, changes_summary, body["type"].upper(), body["category"].upper()]
    )
    return created(row, "Change request submitted")


@bp.patch("/<request_id>/review")
@login_required
@roles_required("ADMIN")
def review_request(request_id):
    """Approve or reject a pending request with an optional note."""
    body = request.get_json(silent=True) or {}
    status = (body.get("status") or "").upper()
    if status not in ("APPROVED", "REJECTED"):
        return error("status must be APPROVED or REJECTED")

    rc = fetchone("SELECT * FROM request_changes WHERE id=%s", [request_id])
    if not rc:
        return not_found()
    if rc["status"] != "PENDING":
        return error("Request is no longer pending")

    # Create or update revision
    if rc["revision_id"]:
        execute(
            "UPDATE revisions SET status=%s, note=%s, author_id=%s WHERE id=%s",
            [status, body.get("note"), g.user_id, rc["revision_id"]]
        )
        rev_id = rc["revision_id"]
    else:
        rev = execute_returning(
            "INSERT INTO revisions (author_id, note, status) VALUES (%s,%s,%s) RETURNING id",
            [g.user_id, body.get("note"), status]
        )
        rev_id = rev["id"]

    execute(
        "UPDATE request_changes SET status=%s, revision_id=%s WHERE id=%s",
        [status, rev_id, request_id]
    )
    return ok(message=f"Request {status.lower()}")


@bp.get("/my-requests")
@login_required
def my_requests():
    page, per_page = get_page_params()
    sql = """
        SELECT rc.id, rc.category, rc.type, rc.status, rc.date_created,
               rev.status AS revision_status, rev.note AS revision_note
        FROM request_changes rc
        LEFT JOIN revisions rev ON rc.revision_id=rev.id
        WHERE rc.author_id = %s
        ORDER BY rc.date_created DESC
    """
    return ok(paginate(sql, [g.user_id], page, per_page))
