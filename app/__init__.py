"""Flask application factory."""
import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["JSON_SORT_KEYS"] = False

    # ── CORS ─────────────────────────────────────────────────────────────────
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    CORS(app, supports_credentials=True, origins=origins)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.routes.auth import bp as auth_bp
    from app.routes.users import bp as users_bp
    from app.routes.subjects import bp as subjects_bp
    from app.routes.modules import bp as modules_bp
    from app.routes.assessments import bp as assessments_bp
    from app.routes.questions import bp as questions_bp
    from app.routes.verification import bp as verification_bp
    from app.routes.dashboard import bp as dashboard_bp

    for blueprint in [auth_bp, users_bp, subjects_bp, modules_bp,
                       assessments_bp, questions_bp, verification_bp, dashboard_bp]:
        app.register_blueprint(blueprint)

    # ── Global error handlers ─────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "message": "Route not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"success": False, "message": "Method not allowed"}), 405

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"success": False, "message": "Internal server error"}), 500

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "version": "1.0.0"})

    return app
