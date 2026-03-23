import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn_str = os.getenv("DATABASE_URL")
if not conn_str:
    # Try common local dev string if .env not available or missing it
    conn_str = "postgresql://postgres:postgres@localhost:5432/cognify_v3"

try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    cur.execute("ALTER TABLE tos_versions ADD COLUMN IF NOT EXISTS pdf_url TEXT;")
    conn.commit()
    print("Migration successful: added pdf_url to tos_versions")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Migration failed: {e}")
