"""
config_inline.py — Inline config for when the extractor runs inside the FastAPI process.
(No file watcher, no standalone script — just import and call extract().)

This file is the backend-side counterpart of config.py in pdf_extractor/.
It reads the same env vars but defaults to /tmp paths so the FastAPI process
never writes to the project directory.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from app/extractor/)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "")

MAX_RETRIES      = int(os.getenv("TOS_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = int(os.getenv("TOS_RETRY_DELAY",  "5"))
POLL_INTERVAL    = 5   # unused in backend context but keeps interface consistent