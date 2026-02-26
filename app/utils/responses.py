"""Standardized JSON response helpers."""
from flask import jsonify

def ok(data=None, message="Success", status=200):
    return jsonify({"success": True, "message": message, "data": data}), status

def created(data=None, message="Created"):
    return ok(data, message, 201)

def error(message="An error occurred", status=400, errors=None):
    body = {"success": False, "message": message}
    if errors:
        body["errors"] = errors
    return jsonify(body), status

def not_found(message="Resource not found"):
    return error(message, 404)

def unauthorized(message="Unauthorized"):
    return error(message, 401)

def forbidden(message="Forbidden"):
    return error(message, 403)

def server_error(message="Internal server error"):
    return error(message, 500)
