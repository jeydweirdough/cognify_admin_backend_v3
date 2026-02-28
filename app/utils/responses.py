"""Standardized JSON response helpers."""
from fastapi.responses import JSONResponse


def ok(data=None, message="Success", status=200):
    return JSONResponse({"success": True, "message": message, "data": data}, status_code=status)

def created(data=None, message="Created"):
    return ok(data, message, 201)

def no_content():
    from fastapi.responses import Response
    return Response(status_code=204)

def error(message="An error occurred", status=400, errors=None):
    body = {"success": False, "message": message}
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status)

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
