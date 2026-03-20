import sys
import os

# Add current directory to path so we can import app
sys.path.append(os.getcwd())

from app.db import execute

def apply_migration():
    migration_path = "migrations/update_readiness_view_for_active_tos.sql"
    if not os.path.exists(migration_path):
        print(f"Error: {migration_path} not found")
        return

    with open(migration_path, "r") as f:
        sql = f.read()

    try:
        print(f"Applying migration from {migration_path}...")
        execute(sql)
        print("Migration applied successfully.")
    except Exception as e:
        print(f"Error applying migration: {e}")

if __name__ == "__main__":
    apply_migration()
