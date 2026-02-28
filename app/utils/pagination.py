"""Pagination and search parameter extraction."""
from fastapi import Request


def get_page_params(request: Request, default_per_page=20, max_per_page=100):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        per_page = min(max_per_page, max(1, int(request.query_params.get("per_page", default_per_page))))
    except (ValueError, TypeError):
        page, per_page = 1, default_per_page
    return page, per_page


def get_search(request: Request, field="search"):
    q = request.query_params.get(field, "").strip()
    return f"%{q}%" if q else None


def get_filter(request: Request, field: str, valid_values=None):
    val = (request.query_params.get(field) or "").strip().upper()
    if valid_values and val not in valid_values:
        return None
    return val or None
