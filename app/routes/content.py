"""
Global Content Library - Read-only list of all modules across all subjects.
Editing is handled within subjects.py via the Curriculum Builder.
"""
from fastapi import APIRouter, Request
from app.db import fetchall, paginate
from app.middleware.auth import login_required, permission_required
from app.utils.responses import ok, forbidden
from app.utils.pagination import get_page_params, get_search

admin_content_router   = APIRouter(prefix="/api/web/admin/content",        tags=["admin-content"])
faculty_content_router = APIRouter(prefix="/api/web/faculty/content",      tags=["faculty-content"])
mobile_content_router  = APIRouter(prefix="/api/mobile/student/content",   tags=["mobile-content"])

def _list_all_modules(request: Request, role: str, user_id: str = None):
    page, per_page = get_page_params(request)
    search = get_search(request)
    
    sql = """
        SELECT m.id, m.title, m.format, m.status, m.created_at, m.updated_at,
               s.name AS subject_name, s.id AS subject_id,
               u.first_name || ' ' || u.last_name AS author_name
        FROM modules m
        LEFT JOIN subjects s ON s.id = m.subject_id
        LEFT JOIN users u ON u.id = m.created_by
        WHERE 1=1
    """
    params = []
    
    # Apply the same strict role rules here as we did in subjects.py
    if role == "FACULTY":
        sql += " AND (m.status = 'APPROVED' OR m.created_by = %s)"
        params.append(user_id)
    elif role == "STUDENT":
        sql += " AND m.status = 'APPROVED'"
        
    if search:
        sql += " AND (LOWER(m.title) LIKE LOWER(%s) OR LOWER(s.name) LIKE LOWER(%s))"
        params.extend([search, search])
        
    sql += " ORDER BY m.updated_at DESC"
    
    result = paginate(sql, params, page, per_page)
    for r in result["items"]:
        r["id"] = str(r["id"])
        r["subject_id"] = str(r["subject_id"])
    return result

@admin_content_router.get("")
async def admin_list(request: Request):
    auth = permission_required("view_content")(request)
    return ok(_list_all_modules(request, "ADMIN"))

@faculty_content_router.get("")
async def faculty_list(request: Request):
    auth = permission_required("view_content")(request)
    return ok(_list_all_modules(request, "FACULTY", auth.user_id))
    
@mobile_content_router.get("")
async def mobile_list(request: Request):
    auth = login_required(request)
    if auth.role != "STUDENT": return forbidden()
    return ok(_list_all_modules(request, "STUDENT"))