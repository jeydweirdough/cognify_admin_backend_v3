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
    """Load .env values if present."""
    if os.path.exists(ENV_PATH):
        return dotenv_values(ENV_PATH)
    return {}

def find_psql():
    """Smart search to find psql.exe on a Windows machine."""
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

# ─── Offline setup (original behaviour) ──────────────────────────────────────

def run_offline(psql_exe, hashed_str):
    db_name = input("\nEnter database name (press Enter for 'psych_db'): ").strip() or "psych_db"
    pg_password = getpass.getpass("Enter PostgreSQL admin password (for user 'postgres'): ")

    os.environ["PGPASSWORD"] = pg_password

    base_args = [psql_exe, "-U", "postgres"]

    print(f"\nBuilding local database '{db_name}'...\n")

    try:
        # Terminate existing connections
        terminate_cmd = (
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{db_name}';"
        )
        subprocess.run(base_args + ["-c", terminate_cmd], check=True, capture_output=True, text=True)

        # Drop + create
        subprocess.run(base_args + ["-c", f"DROP DATABASE IF EXISTS {db_name};"], check=True, capture_output=True, text=True)
        subprocess.run(base_args + ["-c", f"CREATE DATABASE {db_name};"], check=True, capture_output=True, text=True)

        # Schema
        print("Running schema.sql...")
        subprocess.run(base_args + ["-d", db_name, "-f", "migrations/schema_changes.sql"], check=True, capture_output=True, text=True)

        # Seed
        print("Running seed.sql...")
        subprocess.run(base_args + ["-d", db_name, "-f", "migrations/seed_changes.sql"], check=True, capture_output=True, text=True)

        # Update passwords
        print("Updating seeded user passwords...")
        update_cmd = f"UPDATE users SET password = '{hashed_str}';"
        subprocess.run(base_args + ["-d", db_name, "-c", update_cmd], check=True, capture_output=True, text=True)

        print("\n✅ Local database setup complete!")
        print("Use the dev password you entered to log in to the Cognify app.")

    except subprocess.CalledProcessError as e:
        print("\n❌ ERROR: Database execution failed.")
        if "password authentication failed" in (e.stderr or ""):
            print("Reason: Incorrect PostgreSQL admin password.")
        else:
            print(f"Details:\n{(e.stderr or '').strip()}")
        sys.exit(1)

    finally:
        if "PGPASSWORD" in os.environ:
            del os.environ["PGPASSWORD"]

# ─── Online setup (Supabase) ──────────────────────────────────────────────────

def run_online(psql_exe, hashed_str, env: dict):
    """
    Connect to Supabase using DB_URL from .env (or prompt as fallback).
    """

    db_url = env.get("DB_URL") or input("Enter Supabase DB_URL: ").strip()
    if not db_url:
        print("❌ ERROR: DB_URL is required for online mode.")
        sys.exit(1)

    os.environ["PGSSLMODE"] = "require"

    # All psql commands use the full connection URL
    base_args = [psql_exe, db_url]

    print(f"\nConnecting to Supabase...\n")

    try:
        # Test connection
        subprocess.run(
            base_args + ["-c", "SELECT 1;"],
            check=True, capture_output=True, text=True
        )
        print("✅ Connected to Supabase!\n")

        # NOTE: Supabase manages the database lifecycle — we do NOT drop/recreate it.
        # We only apply schema + seed on top of the existing database.

        print("Running schema.sql...")
        subprocess.run(
            base_args + ["-f", "migrations/schema_changes.sql"],
            check=True, capture_output=True, text=True
        )

        print("Running seed.sql...")
        subprocess.run(
            base_args + ["-f", "migrations/seed_changes.sql"],
            check=True, capture_output=True, text=True
        )

        print("Updating seeded user passwords...")
        update_cmd = f"UPDATE users SET password = '{hashed_str}';"
        subprocess.run(
            base_args + ["-c", update_cmd],
            check=True, capture_output=True, text=True
        )

        print("\n✅ Supabase database setup complete!")
        print("Use the dev password you entered to log in to the Cognify app.")

    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print("\n❌ ERROR: Supabase operation failed.")
        if "password authentication failed" in stderr:
            print("Reason: Incorrect Supabase password.")
        elif "could not connect" in stderr or "Connection refused" in stderr:
            print("Reason: Could not reach Supabase. Check host/port and your internet connection.")
        elif "SSL" in stderr:
            print("Reason: SSL error. Make sure PGSSLMODE=require is set.")
        else:
            print(f"Details:\n{stderr}")
        sys.exit(1)

    finally:
        if "PGSSLMODE" in os.environ:
            del os.environ["PGSSLMODE"]

# ─── Entry point ──────────────────────────────────────────────────────────────

def setup_database():
    psql_exe = find_psql()
    if not psql_exe:
        print("\n❌ ERROR: psql not found.")
        print("Download PostgreSQL from: https://www.postgresql.org/download/windows/")
        sys.exit(1)
    print(f"✅ Found psql at: {psql_exe}")

    env = load_env()
    mode = choose_mode()

    # Shared: ask for app (seed) password once
    app_password = getpass.getpass("\nEnter dev password for seeded accounts: ")
    hashed_str = bcrypt.hashpw(app_password.encode(), bcrypt.gensalt()).decode()

    print("\n\u2500\u2500\u2500 Password Confirmation \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    print(f"  Plain text : {app_password}")
    print(f"  Bcrypt hash: {hashed_str}")
    print("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    confirm = input("Does this look correct? (y/n): ").strip().lower()
    if confirm != "y":
        print("\u274c Aborted. Please re-run and enter the correct password.")
        sys.exit(0)

    if mode == "offline":
        run_offline(psql_exe, hashed_str)
    else:
        run_online(psql_exe, hashed_str, env)


if __name__ == "__main__":
    setup_database()