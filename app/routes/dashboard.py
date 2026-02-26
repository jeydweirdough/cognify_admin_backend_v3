"""Dashboard and settings routes."""
from flask import Blueprint, request, g
from app.db import fetchone, execute
from app.middleware.auth import login_required, roles_required
from app.utils.responses import ok, error

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@bp.get("/")
@login_required
@roles_required("ADMIN")
def overview():
    row = fetchone("SELECT * FROM v_dashboard_overview")
    return ok(row)


@bp.get("/settings")
@login_required
@roles_required("ADMIN")
def get_settings():
    row = fetchone("SELECT * FROM system_settings LIMIT 1")
    return ok(row)


@bp.put("/settings")
@login_required
@roles_required("ADMIN")
def update_settings():
    body = request.get_json(silent=True) or {}
    allowed = ["academic_year", "institutional_name", "maintenance_mode"]
    updates, params = [], []
    for f in allowed:
        if f in body:
            updates.append(f"{f} = %s")
            params.append(body[f])
    if not updates:
        return error("Nothing to update")
    execute(f"UPDATE system_settings SET {', '.join(updates)}", params)
    return ok(message="Settings updated")
