"""Gunicorn entry point for production."""
from app import create_app
application = create_app()
