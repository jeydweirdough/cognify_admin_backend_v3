"""
Flask application factory.
All blueprints are registered here. Blueprints are grouped by surface:
  /api/web/*    → Admin + Faculty
  /api/mobile/* → Students

Maintenance guard middleware is applied at this level so mobile
routes return 503 automatically when maintenance_mode is on.
"""
import os
from flask import Flask, jsonify, request, g
from flask_cors import CORS


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("JWT_SECRET", "dev-secret")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS(
        app,
        origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
        supports_credentials=True,
    )

    # ── Maintenance guard for mobile surface ─────────────────────────────────
    @app.before_request
    def maintenance_guard():
        """Block all /api/mobile/* requests when maintenance mode is active."""
        if not request.path.startswith("/api/mobile/"):
            return
        # Skip auth endpoints so students can see a clear error message on login
        if request.path.endswith(("/login", "/register")):
            return
        try:
            from app.db import fetchone
            row = fetchone("SELECT maintenance_mode FROM system_settings LIMIT 1")
            if row and row.get("maintenance_mode"):
                return jsonify({
                    "success": False,
                    "message": "System is under maintenance. Please try again later.",
                }), 503
        except Exception:
            pass  # DB unreachable → let request proceed normally

    # ── Register all blueprints ───────────────────────────────────────────────
    _register_blueprints(app)

    # ── Global error handlers ─────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"success": False, "message": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"success": False, "message": "Method not allowed"}), 405

    @app.errorhandler(413)
    def payload_too_large(_):
        return jsonify({"success": False, "message": "Payload too large (max 16 MB)"}), 413

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error("Unhandled exception: %s", e, exc_info=True)
        return jsonify({"success": False, "message": "Internal server error"}), 500

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "psych-api"})

    return app


def _register_blueprints(app: Flask):
    # Auth
    from app.routes.auth import web_auth_bp, mobile_auth_bp
    app.register_blueprint(web_auth_bp)
    app.register_blueprint(mobile_auth_bp)

    # Whitelist
    from app.routes.whitelist import admin_whitelist_bp, faculty_whitelist_bp
    app.register_blueprint(admin_whitelist_bp)
    app.register_blueprint(faculty_whitelist_bp)

    # Users
    from app.routes.users import admin_users_bp, faculty_users_bp
    app.register_blueprint(admin_users_bp)
    app.register_blueprint(faculty_users_bp)

    # Subjects
    from app.routes.subjects import admin_subjects_bp, faculty_subjects_bp, mobile_subjects_bp
    app.register_blueprint(admin_subjects_bp)
    app.register_blueprint(faculty_subjects_bp)
    app.register_blueprint(mobile_subjects_bp)

    # Content
    from app.routes.content import admin_content_bp, faculty_content_bp, mobile_content_bp
    app.register_blueprint(admin_content_bp)
    app.register_blueprint(faculty_content_bp)
    app.register_blueprint(mobile_content_bp)

    # Assessments
    from app.routes.assessments import admin_assess_bp, faculty_assess_bp, mobile_assess_bp
    app.register_blueprint(admin_assess_bp)
    app.register_blueprint(faculty_assess_bp)
    app.register_blueprint(mobile_assess_bp)

    # Analytics + Dashboard
    from app.routes.analytics import admin_dash_bp, faculty_dash_bp, mobile_prog_bp
    app.register_blueprint(admin_dash_bp)
    app.register_blueprint(faculty_dash_bp)
    app.register_blueprint(mobile_prog_bp)

    # Misc (settings, logs, revisions, verification, roles)
    from app.routes.misc import (
        settings_bp, admin_logs_bp,
        admin_rev_bp, faculty_rev_bp,
        admin_verify_bp, faculty_verify_bp,
        roles_bp,
    )
    app.register_blueprint(settings_bp)
    app.register_blueprint(admin_logs_bp)
    app.register_blueprint(admin_rev_bp)
    app.register_blueprint(faculty_rev_bp)
    app.register_blueprint(admin_verify_bp)
    app.register_blueprint(faculty_verify_bp)
    app.register_blueprint(roles_bp)