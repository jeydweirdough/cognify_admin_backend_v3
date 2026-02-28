import subprocess
import bcrypt
import getpass
import os
import shutil
import sys

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

def setup_database():
    print("=== Cognify Database Setup ===")

    psql_exe = find_psql()
    
    if not psql_exe:
        print("\n❌ ERROR: psql not found. Download PostgreSQL from: https://www.postgresql.org/download/windows/")
        sys.exit(1)

    print(f"✅ Found psql at: {psql_exe}\n")

    # Ask for inputs
    db_name = input("Enter database name (press Enter for 'psych_db'): ").strip() or "psych_db"
    pg_password = getpass.getpass("Enter PostgreSQL admin password (for user 'postgres'): ")
    app_password = getpass.getpass("Enter dev password for seeded accounts: ")
    
    # Set Postgres password for the session
    os.environ["PGPASSWORD"] = pg_password
    
    # Hash the app password
    hashed_str = bcrypt.hashpw(app_password.encode(), bcrypt.gensalt()).decode()

    print(f"\nBuilding database '{db_name}'...\n")

    try:
        # 1. Terminate existing connections so DROP DATABASE doesn't hang
        terminate_cmd = f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}';"
        subprocess.run([psql_exe, "-U", "postgres", "-c", terminate_cmd], check=True, capture_output=True, text=True)

        # 2. Drop existing database
        subprocess.run([psql_exe, "-U", "postgres", "-c", f"DROP DATABASE IF EXISTS {db_name};"], check=True, capture_output=True, text=True)

        # 3. Create fresh database
        subprocess.run([psql_exe, "-U", "postgres", "-c", f"CREATE DATABASE {db_name};"], check=True, capture_output=True, text=True)

        # 4. Run schema.sql against the new database
        print("Running schema.sql...")
        subprocess.run([
            psql_exe, "-U", "postgres", "-d", db_name, "-f", "migrations/schema.sql"
        ], check=True, capture_output=True, text=True)

        # 5. Run seed.sql against the new database
        print("Running seed.sql...")
        subprocess.run([
            psql_exe, "-U", "postgres", "-d", db_name, "-f", "migrations/seed.sql"
        ], check=True, capture_output=True, text=True)

        # 6. Update all seeded user passwords to the new bcrypt hash
        print("Updating seeded user passwords...")
        update_cmd = f"UPDATE users SET password = '{hashed_str}';"
        subprocess.run([
            psql_exe, "-U", "postgres", "-d", db_name, "-c", update_cmd
        ], check=True, capture_output=True, text=True)

        print("\n✅ Database setup complete!")
        print("Use the dev password you entered to log in to the Cognify app.")

    except subprocess.CalledProcessError as e:
        print("\n❌ ERROR: Database execution failed.")
        if "password authentication failed" in e.stderr:
            print("Reason: Incorrect PostgreSQL admin password.")
        else:
            print(f"Details:\n{e.stderr.strip()}")
        sys.exit(1)
        
    finally:
        # Ensure the Postgres admin password is removed from memory
        if "PGPASSWORD" in os.environ:
            del os.environ["PGPASSWORD"]

if __name__ == "__main__":
    setup_database()