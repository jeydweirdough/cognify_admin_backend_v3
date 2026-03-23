import sys
import os

# Add the project root to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.db import fetchall, execute

try:
    rows = fetchall("SELECT id FROM tos_versions WHERE pdf_url IS NULL OR pdf_url = '';")
    for row in rows:
        pdf_url = f"/api/web/admin/tos/{row['id']}/pdf"
        execute("UPDATE tos_versions SET pdf_url = %s WHERE id = %s", [pdf_url, row['id']])
    print(f"Backfilled {len(rows)} TOS versions.")
except Exception as e:
    print(f"Backfill failed: {e}")
