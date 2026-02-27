"""
Subjects (Psychology Core Subjects) routes
  GET    /api/web/admin/subjects             list
  POST   /api/web/admin/subjects             create
  GET    /api/web/admin/subjects/:id         detail + full topic tree
  PUT    /api/web/admin/subjects/:id         update metadata
  DELETE /api/web/admin/subjects/:id         delete
  PATCH  /api/web/admin/subjects/:id/status  approve/reject pending change

Faculty endpoints (read + write, pending approval flow):
  GET    /api/web/faculty/subjects
  POST   /api/web/faculty/subjects
  GET    /api/web/faculty/subjects/:id
  PUT    /api/web/faculty/subjects/:id        → saves as PENDING change
  POST   /api/web/faculty/subjects/:id/topics → add topic/subtopic

Mobile read-only:
  GET    /api/mobile/student/subjects
  GET    /api/mobile/student/subjects/:id
"""
from flask import Blueprint, request, g
from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, created, no_content, error, not_found
from app.utils.pagination import get_page_params, get_search
from app.utils.validators import require_fields, clean_str
from app.utils.log import log_action

admin_subjects_bp   = Blueprint("admin_subjects",   __name__, url_prefix="/api/web/admin/subjects")
faculty_subjects_bp = Blueprint("faculty_subjects", __name__, url_prefix="/api/web/faculty/subjects")
mobile_subjects_bp  = Blueprint("mobile_subjects",  __name__, url_prefix="/api/mobile/student/subjects")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_subject_tree(subject_id: str) -> dict | None:
    s = fetchone(
        """SELECT s.*, u.first_name || ' ' || u.last_name AS created_by_name
           FROM subjects s LEFT JOIN users u ON u.id = s.created_by
           WHERE s.id = %s""",
        [subject_id],
    )
    if not s:
        return None
    s["id"] = str(s["id"])
    s["topics"] = _build_topic_tree(subject_id)
    return s


def _build_topic_tree(subject_id: str, parent_id=None) -> list:
    rows = fetchall(
        """SELECT t.*, u.first_name || ' ' || u.last_name AS created_by_name
           FROM topics t LEFT JOIN users u ON u.id = t.created_by
           WHERE t.subject_id = %s AND t.parent_id IS NOT DISTINCT FROM %s
           ORDER BY t.sort_order, t.created_at""",
        [subject_id, parent_id],
    )
    result = []
    for r in rows:
        r["id"] = str(r["id"])
        r["subject_id"] = str(r["subject_id"])
        r["subTopics"] = _build_topic_tree(subject_id, r["id"])
        result.append(r)
    return result


def _list_subjects(status_filter=None):
    page, per_page = get_page_params()
    search = get_search()
    sql    = ["SELECT s.*, u.first_name || ' ' || u.last_name AS created_by_name FROM subjects s LEFT JOIN users u ON u.id = s.created_by WHERE 1=1"]
    params = []
    if search:
        sql.append("AND (LOWER(s.name) LIKE LOWER(%s) OR LOWER(s.description) LIKE LOWER(%s))")
        params += [search, search]
    if status_filter:
        sql.append("AND s.status = %s")
        params.append(status_filter)
    sql.append("ORDER BY s.name")
    result = paginate(" ".join(sql), params, page, per_page)
    for s in result["items"]:
        s["id"] = str(s["id"])
        # Include topic count
        cnt = fetchone("SELECT COUNT(*) AS c FROM topics WHERE subject_id = %s", [s["id"]])
        s["topic_count"] = cnt["c"] if cnt else 0
    return result


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

@admin_subjects_bp.get("")
@login_required
@roles_required("ADMIN")
def admin_list():
    return ok(_list_subjects())


@admin_subjects_bp.get("/pending-changes")
@login_required
@roles_required("ADMIN")
def admin_pending_changes():
    rows = fetchall(
        """SELECT psc.*, s.name AS subject_name,
                  u.first_name || ' ' || u.last_name AS submitted_by_name
           FROM pending_subject_changes psc
           JOIN subjects s ON s.id = psc.subject_id
           JOIN users u ON u.id = psc.submitted_by
           WHERE psc.status = 'PENDING'
           ORDER BY psc.created_at DESC"""
    )
    for r in rows:
        r["id"] = str(r["id"])
        r["subject_id"] = str(r["subject_id"])
    return ok(rows)


@admin_subjects_bp.get("/<subject_id>")
@login_required
@roles_required("ADMIN")
def admin_get(subject_id):
    s = _get_subject_tree(subject_id)
    return ok(s) if s else not_found()


@admin_subjects_bp.post("")
@login_required
@roles_required("ADMIN")
def admin_create():
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, ["name"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")
    if fetchone("SELECT id FROM subjects WHERE LOWER(name) = LOWER(%s)", [body["name"]]):
        return error("Subject name already exists", 409)
    s = execute_returning(
        """INSERT INTO subjects (name, description, color, status, created_by)
           VALUES (%s, %s, %s, 'APPROVED', %s) RETURNING *""",
        [clean_str(body["name"]), clean_str(body.get("description")),
         body.get("color", "#6366f1"), g.user_id],
    )
    log_action("Created subject", s["name"], str(s["id"]))
    return created(_get_subject_tree(str(s["id"])))


@admin_subjects_bp.put("/<subject_id>")
@login_required
@roles_required("ADMIN")
def admin_update(subject_id):
    s = fetchone("SELECT * FROM subjects WHERE id = %s", [subject_id])
    if not s:
        return not_found()
    body = request.get_json(silent=True) or {}
    updated = execute_returning(
        """UPDATE subjects SET name = %s, description = %s, color = %s
           WHERE id = %s RETURNING *""",
        [clean_str(body.get("name", s["name"])),
         clean_str(body.get("description", s.get("description"))),
         body.get("color", s["color"]), subject_id],
    )
    log_action("Updated subject", updated["name"], subject_id)
    return ok(_get_subject_tree(subject_id))


@admin_subjects_bp.delete("/<subject_id>")
@login_required
@roles_required("ADMIN")
def admin_delete(subject_id):
    s = fetchone("SELECT name FROM subjects WHERE id = %s", [subject_id])
    if not s:
        return not_found()
    execute("DELETE FROM subjects WHERE id = %s", [subject_id])
    log_action("Deleted subject", s["name"], subject_id)
    return no_content()


@admin_subjects_bp.patch("/<change_id>/approve-change")
@login_required
@roles_required("ADMIN")
def admin_approve_change(change_id):
    """Approve or reject a pending subject change."""
    body = request.get_json(silent=True) or {}
    action = (body.get("action") or "").upper()
    if action not in ("APPROVE", "REJECT"):
        return error("action must be APPROVE or REJECT")

    change = fetchone("SELECT * FROM pending_subject_changes WHERE id = %s AND status = 'PENDING'", [change_id])
    if not change:
        return not_found("Pending change not found")

    if action == "APPROVE":
        data = change["change_data"]
        execute(
            "UPDATE subjects SET name = %s, description = %s, color = %s WHERE id = %s",
            [data.get("name"), data.get("description"), data.get("color"), change["subject_id"]],
        )
        # Apply topic tree if provided
        if data.get("topics"):
            _save_topic_tree(str(change["subject_id"]), data["topics"])

    execute(
        "UPDATE pending_subject_changes SET status = %s, reviewed_by = %s, review_note = %s, reviewed_at = NOW() WHERE id = %s",
        [action, g.user_id, body.get("note"), change_id],
    )
    log_action(f"Subject change {action.lower()}d", None, change_id)
    return ok({"action": action})


# Topics CRUD under admin
@admin_subjects_bp.post("/<subject_id>/topics")
@login_required
@roles_required("ADMIN")
def admin_add_topic(subject_id):
    return _add_topic(subject_id, auto_approve=True)


@admin_subjects_bp.put("/<subject_id>/topics/<topic_id>")
@login_required
@roles_required("ADMIN")
def admin_update_topic(subject_id, topic_id):
    return _update_topic(topic_id, auto_approve=True)


@admin_subjects_bp.delete("/<subject_id>/topics/<topic_id>")
@login_required
@roles_required("ADMIN")
def admin_delete_topic(subject_id, topic_id):
    execute("DELETE FROM topics WHERE id = %s AND subject_id = %s", [topic_id, subject_id])
    return no_content()


# ═══════════════════════════════════════════════════════════════
# FACULTY — write goes through pending change
# ═══════════════════════════════════════════════════════════════

@faculty_subjects_bp.get("")
@login_required
@roles_required("FACULTY")
def faculty_list():
    return ok(_list_subjects(status_filter="APPROVED"))


@faculty_subjects_bp.get("/<subject_id>")
@login_required
@roles_required("FACULTY")
def faculty_get(subject_id):
    s = _get_subject_tree(subject_id)
    return ok(s) if s else not_found()


@faculty_subjects_bp.post("/<subject_id>/topics")
@login_required
@roles_required("FACULTY")
def faculty_add_topic(subject_id):
    return _add_topic(subject_id, auto_approve=False)


@faculty_subjects_bp.put("/<subject_id>/topics/<topic_id>")
@login_required
@roles_required("FACULTY")
def faculty_update_topic(subject_id, topic_id):
    return _update_topic(topic_id, auto_approve=False)


@faculty_subjects_bp.post("/<subject_id>/submit-change")
@login_required
@roles_required("FACULTY")
def faculty_submit_change(subject_id):
    """Faculty submits a full subject snapshot for admin review."""
    if not fetchone("SELECT id FROM subjects WHERE id = %s", [subject_id]):
        return not_found()
    body = request.get_json(silent=True) or {}
    change = execute_returning(
        "INSERT INTO pending_subject_changes (subject_id, change_data, submitted_by) VALUES (%s, %s, %s) RETURNING id",
        [subject_id, body, g.user_id],
    )
    log_action("Submitted subject change for review", None, subject_id)
    return created({"change_id": str(change["id"])})


# ═══════════════════════════════════════════════════════════════
# MOBILE — read-only
# ═══════════════════════════════════════════════════════════════

@mobile_subjects_bp.get("")
@login_required
@roles_required("STUDENT")
def mobile_list():
    result = _list_subjects(status_filter="APPROVED")
    return ok(result)


@mobile_subjects_bp.get("/<subject_id>")
@login_required
@roles_required("STUDENT")
def mobile_get(subject_id):
    s = _get_subject_tree(subject_id)
    return ok(s) if s else not_found()


# ── Shared topic helpers ───────────────────────────────────────────────────────

def _add_topic(subject_id: str, auto_approve: bool):
    if not fetchone("SELECT id FROM subjects WHERE id = %s", [subject_id]):
        return not_found("Subject not found")
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, ["title"])
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    status = "APPROVED" if auto_approve else "PENDING"
    topic = execute_returning(
        """INSERT INTO topics (subject_id, parent_id, title, description, content, sort_order, status, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        [subject_id, body.get("parent_id"), clean_str(body["title"]),
         clean_str(body.get("description")), body.get("content"),
         body.get("sort_order", 0), status, g.user_id],
    )
    topic["id"] = str(topic["id"])
    topic["subTopics"] = []
    log_action("Added topic", topic["title"], str(topic["id"]))
    return created(topic)


def _update_topic(topic_id: str, auto_approve: bool):
    existing = fetchone("SELECT * FROM topics WHERE id = %s", [topic_id])
    if not existing:
        return not_found("Topic not found")
    body = request.get_json(silent=True) or {}
    status = existing["status"]
    if not auto_approve and status == "APPROVED":
        status = "PENDING"   # faculty edits go back to pending

    updated = execute_returning(
        """UPDATE topics SET title = %s, description = %s, content = %s,
                            sort_order = %s, status = %s
           WHERE id = %s RETURNING *""",
        [clean_str(body.get("title", existing["title"])),
         clean_str(body.get("description", existing.get("description"))),
         body.get("content", existing.get("content")),
         body.get("sort_order", existing["sort_order"]),
         status, topic_id],
    )
    updated["id"] = str(updated["id"])
    updated["subTopics"] = _build_topic_tree(str(updated["subject_id"]), updated["id"])
    return ok(updated)


def _save_topic_tree(subject_id: str, topics: list, parent_id=None):
    """Recursively upsert a topic tree (used on change approval)."""
    for t in topics:
        existing = fetchone("SELECT id FROM topics WHERE id = %s", [t.get("id")]) if t.get("id") else None
        if existing:
            execute(
                "UPDATE topics SET title = %s, description = %s, content = %s, status = 'APPROVED' WHERE id = %s",
                [t.get("title"), t.get("description"), t.get("content"), t["id"]],
            )
        else:
            new_topic = execute_returning(
                "INSERT INTO topics (subject_id, parent_id, title, description, content, status) VALUES (%s, %s, %s, %s, %s, 'APPROVED') RETURNING id",
                [subject_id, parent_id, t.get("title"), t.get("description"), t.get("content")],
            )
            t["id"] = str(new_topic["id"])
        if t.get("subTopics"):
            _save_topic_tree(subject_id, t["subTopics"], t["id"])