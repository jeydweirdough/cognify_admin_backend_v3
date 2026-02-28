"""Standardized JSON response helpers.

Uses a custom JSON encoder so that datetime, date, Decimal, UUID, and bytes
values are automatically serialized — no manual .isoformat() calls needed in
route handlers.
"""
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi.responses import Response


class _Encoder(json.JSONEncoder):
    """Serialize types that stdlib json cannot handle."""

    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, bytes):
            return o.decode("utf-8", errors="replace")
        return super().default(o)


def _json(data) -> bytes:
    return json.dumps(data, cls=_Encoder, separators=(",", ":")).encode("utf-8")


def _resp(body: dict, status: int = 200) -> Response:
    return Response(content=_json(body), status_code=status,
                    media_type="application/json")


# ── Public helpers ─────────────────────────────────────────────────────────────

def ok(data=None, message="Success", status=200):
    return _resp({"success": True, "message": message, "data": data}, status)

def created(data=None, message="Created"):
    return ok(data, message, 201)

def no_content():
    return Response(status_code=204)

def error(message="An error occurred", status=400, errors=None):
    body = {"success": False, "message": message}
    if errors:
        body["errors"] = errors
    return _resp(body, status)

def not_found(message="Resource not found"):
    return error(message, 404)

def unauthorized(message="Unauthorized"):
    return error(message, 401)

def forbidden(message="Forbidden"):
    return error(message, 403)

def conflict(message="Conflict"):
    return error(message, 409)

def server_error(message="Internal server error"):
    return error(message, 500)

def maintenance():
    return error("System is under maintenance. Please try again later.", 503)
