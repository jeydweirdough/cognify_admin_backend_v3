import subprocess
import bcrypt
import getpass
import os
import shutil
import sys
from dotenv import dotenv_values

# ─── Supabase / .env config ──────────────────────────────────────────────────
ENV_PATH = ".env"

def load_env():
    if os.path.exists(ENV_PATH):
        return dotenv_values(ENV_PATH)
    return {}

def find_psql():
    psql_path = shutil.which("psql")
    if psql_path:
        return psql_path

    program_files = os.environ.get("ProgramW6432", "C:\\Program Files")
    pg_base_path = os.path.join(program_files, "PostgreSQL")

    if os.path.exists(pg_base_path):
        for root, dirs, files in sorted(os.walk(pg_base_path), reverse=True):
            if "psql.exe" in files:
                return os.path.join(root, "psql.exe")

    for root, dirs, files in os.walk("C:\\"):
        if "psql.exe" in files:
            return os.path.join(root, "psql.exe")

    return None

# ─── Run a psql command and print output ─────────────────────────────────────

def run_psql(args, label):
    """Run a psql command, print stdout/stderr, and raise on failure."""
    print(f"\n▶ {label}...")
    result = subprocess.run(args, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"❌ FAILED: {label}")
        sys.exit(1)
    print(f"✅ {label} — done")

# ─── Connection mode selection ────────────────────────────────────────────────

def choose_mode():
    print("\n=== Cognify Database Setup ===")
    print("\nSelect connection mode:")
    print("  [1] Offline — Local PostgreSQL")
    print("  [2] Online  — Supabase (cloud)")
    choice = input("\nEnter 1 or 2: ").strip()
    if choice == "1":
        return "offline"
    elif choice == "2":
        return "online"
    else:
        print("❌ Invalid choice. Exiting.")
        sys.exit(1)

# ─── Offline setup ────────────────────────────────────────────────────────────

def run_offline(psql_exe, hashed_str):
    db_name = input("\nEnter database name (press Enter for 'psych_db'): ").strip() or "psych_db"
    pg_password = getpass.getpass("Enter PostgreSQL admin password (for user 'postgres'): ")

    os.environ["PGPASSWORD"] = pg_password
    base = [psql_exe, "-U", "postgres"]

    try:
        run_psql(base + ["-c", f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}';"], "Terminate existing connections")
        run_psql(base + ["-c", f"DROP DATABASE IF EXISTS {db_name};"], "Drop old database")
        run_psql(base + ["-c", f"CREATE DATABASE {db_name};"], "Create database")
        run_psql(base + ["-d", db_name, "-f", "migrations/schema_changes.sql"], "Apply schema")
        run_psql(base + ["-d", db_name, "-f", "migrations/seed_changes.sql"], "Apply seed data")
        run_psql(base + ["-d", db_name, "-c", f"UPDATE users SET password = '{hashed_str}';"], "Update passwords")

        print("\n✅ Local database setup complete!")
        print("Use the dev password you entered to log in.")
    finally:
        os.environ.pop("PGPASSWORD", None)

# ─── Online setup (Supabase) ──────────────────────────────────────────────────

def run_online(psql_exe, hashed_str, env: dict):
    db_url = env.get("DB_URL") or input("Enter Supabase DB_URL: ").strip()
    if not db_url:
        print("❌ DB_URL is required for online mode.")
        sys.exit(1)

    os.environ["PGSSLMODE"] = "require"
    base = [psql_exe, db_url]

    try:
        # Test connection first — show output so errors are visible
        print("\nTesting connection to Supabase...")
        result = subprocess.run(base + ["-c", "SELECT current_database(), current_user;"], text=True, capture_output=False)
        if result.returncode != 0:
            print("❌ Could not connect to Supabase. Check your DB_URL in .env")
            sys.exit(1)
        print("✅ Connected!\n")

        print("⚠️  WARNING: This will DROP all existing tables and recreate them from scratch.")
        print("   All existing data in Supabase will be permanently deleted.")
        confirm = input("   Type YES to continue: ").strip()
        if confirm != "YES":
            print("❌ Aborted.")
            sys.exit(0)

        run_psql(base + ["-f", "migrations/schema_changes.sql"], "Drop & recreate schema")
        run_psql(base + ["-f", "migrations/seed_changes.sql"],   "Apply seed data")
        run_psql(base + ["-c", f"UPDATE users SET password = '{hashed_str}' WHERE password IS NOT NULL;"], "Update passwords")

        print("\n✅ Supabase database setup complete!")
        print("Use the dev password you entered to log in.")

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        os.environ.pop("PGSSLMODE", None)

# ─── Entry point ──────────────────────────────────────────────────────────────

def setup_database():
    psql_exe = find_psql()
    if not psql_exe:
        print("\n❌ psql not found.")
        print("Download PostgreSQL from: https://www.postgresql.org/download/windows/")
        sys.exit(1)
    print(f"✅ Found psql at: {psql_exe}")

    env  = load_env()
    mode = choose_mode()

    app_password = getpass.getpass("\nEnter dev password for seeded accounts: ")
    hashed_str   = bcrypt.hashpw(app_password.encode(), bcrypt.gensalt()).decode()

    print("\n─── Password Confirmation ─────────────────────────────")
    print(f"  Plain text : {app_password}")
    print(f"  Bcrypt hash: {hashed_str}")
    print("───────────────────────────────────────────────────────")
    confirm = input("Does this look correct? (y/n): ").strip().lower()
    if confirm != "y":
        print("❌ Aborted.")
        sys.exit(0)

    if mode == "offline":
        run_offline(psql_exe, hashed_str)
    else:
        run_online(psql_exe, hashed_str, env)


if __name__ == "__main__":
    setup_database()