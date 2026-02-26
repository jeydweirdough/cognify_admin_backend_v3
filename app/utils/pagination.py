"""Pagination parameter extraction from request."""
from flask import request

def get_page_params(default_per_page=20, max_per_page=100):
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(max_per_page, max(1, int(request.args.get("per_page", default_per_page))))
    except (ValueError, TypeError):
        page, per_page = 1, default_per_page
    return page, per_page

def get_search(field="search"):
    q = request.args.get(field, "").strip()
    return f"%{q}%" if q else None
