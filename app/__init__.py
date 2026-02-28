"""
FastAPI application factory.
All routers are registered here. Routers are grouped by surface:
  /api/web/*    → Admin + Faculty
  /api/mobile/* → Students

Maintenance guard middleware is applied at this level so mobile
routes return 503 automatically when maintenance_mode is on.
"""
import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.middleware.auth import _HTTPException


def create_app() -> FastAPI:
    app = FastAPI(title="Cognify Admin API")

    # ── CORS ──────────────────────────────────────────────────────────────────
    origins = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handler for auth errors ──────────────────────────────
    @app.exception_handler(_HTTPException)
    async def http_exc_handler(request: Request, exc: _HTTPException):
        return exc.response

    # ── Maintenance guard for mobile surface ──────────────────────────────────
    @app.middleware("http")
    async def maintenance_guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/mobile/") and not path.endswith(("/login", "/register")):
            try:
                from app.db import fetchone
                row = fetchone("SELECT maintenance_mode FROM system_settings LIMIT 1")
                if row and row.get("maintenance_mode"):
                    return JSONResponse(
                        {"success": False, "message": "System is under maintenance. Please try again later."},
                        status_code=503,
                    )
            except Exception:
                pass
        return await call_next(request)

    # ── Request/response logging ───────────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        print(f"\n---> INCOMING: {request.method} {request.url}")
        response = await call_next(request)
        print(f"<--- OUTGOING: {request.method} {request.url.path} | Status: {response.status_code}")
        print("-" * 50)
        return response

    # ── Global error handlers ─────────────────────────────────────────────────
    @app.exception_handler(404)
    async def not_found(_request, _exc):
        return JSONResponse({"success": False, "message": "Endpoint not found"}, status_code=404)

    @app.exception_handler(405)
    async def method_not_allowed(_request, _exc):
        return JSONResponse({"success": False, "message": "Method not allowed"}, status_code=405)

    @app.exception_handler(413)
    async def payload_too_large(_request, _exc):
        return JSONResponse({"success": False, "message": "Payload too large (max 16 MB)"}, status_code=413)

    @app.exception_handler(500)
    async def internal_error(request: Request, exc: Exception):
        logging.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse({"success": False, "message": "Internal server error"}, status_code=500)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "psych-api"}

    # ── Register all routers ──────────────────────────────────────────────────
    _register_routers(app)

    return app


def _register_routers(app: FastAPI):
    from app.routes.auth       import web_auth_router, mobile_auth_router
    from app.routes.whitelist  import admin_whitelist_router, faculty_whitelist_router
    from app.routes.users      import admin_users_router, faculty_users_router
    from app.routes.subjects   import admin_subjects_router, faculty_subjects_router, mobile_subjects_router
    from app.routes.content    import admin_content_router, faculty_content_router, mobile_content_router
    from app.routes.assessments import admin_assess_router, faculty_assess_router, mobile_assess_router
    from app.routes.analytics  import admin_dash_router, faculty_dash_router, mobile_prog_router
    from app.routes.misc       import (
        settings_router, admin_logs_router,
        admin_rev_router, faculty_rev_router,
        admin_verify_router, faculty_verify_router,
        roles_router,
    )

    for router in [
        web_auth_router, mobile_auth_router,
        admin_whitelist_router, faculty_whitelist_router,
        admin_users_router, faculty_users_router,
        admin_subjects_router, faculty_subjects_router, mobile_subjects_router,
        admin_content_router, faculty_content_router, mobile_content_router,
        admin_assess_router, faculty_assess_router, mobile_assess_router,
        admin_dash_router, faculty_dash_router, mobile_prog_router,
        settings_router, admin_logs_router,
        admin_rev_router, faculty_rev_router,
        admin_verify_router, faculty_verify_router,
        roles_router,
    ]:
        app.include_router(router)
