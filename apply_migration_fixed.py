import sys
import os

# Add the project root to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.db import execute

try:
    execute("ALTER TABLE tos_versions ADD COLUMN IF NOT EXISTS pdf_url TEXT;")
    print("Migration successful: added pdf_url to tos_versions")
except Exception as e:
    print(f"Migration failed: {e}")
