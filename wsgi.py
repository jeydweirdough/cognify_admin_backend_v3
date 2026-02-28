"""Production entry point (uvicorn/gunicorn with uvicorn workers)."""
from app import create_app

application = create_app()
