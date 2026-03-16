"""
Cognify — Database Management Tool
====================================
python setup.py

Two migration files, always run in this order:
  1. migrations/schema_changes.sql  — DROP all tables + recreate schema
  2. migrations/seed_changes.sql    — insert seed data

Full Reset (local / offline):
  Drops and recreates the entire database, then runs both files.
  Guarantees a completely clean state.

Full Reset (Supabase / online):
  Cannot drop the database itself. Runs schema_changes.sql (which
  DROPs every app table with CASCADE, then recreates them clean) and
  then seed_changes.sql. Same end result as local — clean tables,
  fresh seed data — without needing superuser access to the server.
"""

import subprocess, bcrypt, getpass, os, shutil, sys
from dotenv import dotenv_values

ENV_PATH = ".env"

# ── Colour helpers ─────────────────────────────────────────────────────────────
T = sys.stdout.isatty()
def _c(code, t): return f"\033[{code}m{t}\033[0m" if T else t
def G(t): return _c("32",  t)
def Y(t): return _c("33",  t)
def R(t): return _c("31",  t)
def B(t): return _c("34",  t)
def C(t): return _c("36",  t)
def W(t): return _c("1",   t)
def D(t): return _c("2",   t)
def M(t): return _c("35",  t)

def ln(n=64): return D("─" * n)

def clear(): os.system("cls" if os.name == "nt" else "clear")

def ok(m):   print(f"\n  {G('✔')}  {G(m)}")
def warn(m): print(f"\n  {Y('⚠')}  {Y(m)}")
def fail(m): print(f"\n  {R('✘')}  {R(m)}")
def info(m): print(f"  {D('·')}  {m}")
def step(m): print(f"  {D('▶')} {m} …", end=" ", flush=True)

def ask(prompt, default=""):
    d = f" {D(f'[{default}]')}" if default else ""
    return input(f"\n  {C('›')} {prompt}{d}: ").strip() or default

def ask_yn(prompt, default=False):
    hint = D("[Y/n]") if default else D("[y/N]")
    raw = input(f"\n  {C('›')} {prompt} {hint}: ").strip().lower()
    return (raw in ("y", "yes")) if raw else default

def pause():
    input(f"\n  {D('Press Enter to return to menu…')}")


# ── psql helpers ───────────────────────────────────────────────────────────────

def load_env():
    return dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

def find_psql():
    p = shutil.which("psql")
    if p: return p
    base = os.path.join(os.environ.get("ProgramW6432", r"C:\Program Files"), "PostgreSQL")
    if os.path.exists(base):
        for root, _, files in sorted(os.walk(base), reverse=True):
            if "psql.exe" in files:
                return os.path.join(root, "psql.exe")
    for root, _, files in os.walk("C:\\"):
        if "psql.exe" in files:
            return os.path.join(root, "psql.exe")
    return None

def run_sql(args, label, fatal=True):
    step(label)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(R("FAILED"))
        for l in (r.stderr or "").strip().splitlines()[:6]:
            print(f"    {R(l)}")
        if fatal: sys.exit(1)
        return False
    print(G("done"))
    return True

def test_conn(base):
    step("Testing connection")
    r = subprocess.run(
        base + ["-c", "SELECT current_database(), current_user;"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(R("FAILED"))
        for l in (r.stderr or "").strip().splitlines()[:3]:
            print(f"    {R(l)}")
        return False
    print(G("OK ✔"))
    for l in r.stdout.splitlines():
        l = l.strip()
        if l and "|" in l and "current_database" not in l and not l.startswith("-"):
            parts = [p.strip() for p in l.split("|")]
            if len(parts) >= 2:
                print(f"  {D('db=')} {W(parts[0])}  {D('user=')} {W(parts[1])}")
    return True


# ── Connection state ───────────────────────────────────────────────────────────

conn = {"base": [], "label": "", "mode": "", "db": ""}

def get_label():
    return conn["label"] or Y("not connected")

def set_connection(psql_exe):
    print()
    print(f"  {W('[1]')}  {G('Local PostgreSQL')}  {D('— offline / dev')}")
    print(f"  {W('[2]')}  {Y('Supabase (cloud)')}   {D('— uses DB_URL from .env')}")
    print()
    while True:
        raw = input(f"  {C('›')} Connection type: ").strip()
        if raw in ("1", "2"): break
        print(f"  {R('Enter 1 or 2.')}")

    if raw == "1":
        db = ask("Database name", "psych_db")
        pw = getpass.getpass("\n  Postgres admin password (user 'postgres'): ")
        os.environ["PGPASSWORD"] = pw
        conn.update(base=[psql_exe, "-U", "postgres", "-d", db],
                    label=f"{G('local')} › {W(db)}", mode="offline", db=db)
    else:
        env    = load_env()
        db_url = env.get("DB_URL", "")
        if db_url:
            info(f"DB_URL from .env: {D(db_url[:55])}")
            if not ask_yn("Use this URL?", default=True):
                db_url = ask("Enter Supabase DB_URL")
        else:
            warn("DB_URL not found in .env")
            db_url = ask("Enter Supabase DB_URL")
        if not db_url:
            fail("DB_URL required."); return False
        os.environ["PGSSLMODE"] = "require"
        conn.update(base=[psql_exe, db_url],
                    label=f"{Y('supabase')} › {W(db_url[:45])}",
                    mode="online", db="")
    return True


# ── Password helpers ───────────────────────────────────────────────────────────

def prompt_password(purpose="all seeded accounts"):
    print(f"\n  {D(f'New password for {purpose}')}")
    while True:
        pw = getpass.getpass("  Password (min 6 chars): ")
        if len(pw) < 6: warn("Too short."); continue
        cf = getpass.getpass("  Confirm: ")
        if pw != cf:    warn("Doesn't match."); continue
        return pw

def hash_pw(plain):
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def apply_pw(hashed):
    run_sql(conn["base"] + ["-c",
        f"UPDATE users SET password='{hashed}';"],
        "Update passwords")


# ── Core run sequence ──────────────────────────────────────────────────────────

SCHEMA_FILE = "migrations/schema_changes.sql"
SEED_FILE   = "migrations/seed_changes.sql"

def run_schema(fatal=True):
    """Run schema_changes.sql — drops all tables then recreates schema."""
    return run_sql(conn["base"] + ["-f", SCHEMA_FILE],
                   "schema_changes.sql  (drop + recreate)", fatal=fatal)

def run_seed(fatal=True):
    """Run seed_changes.sql — inserts all seed data."""
    return run_sql(conn["base"] + ["-f", SEED_FILE],
                   "seed_changes.sql    (insert seed data)", fatal=fatal)


# ══════════════════════════════════════════════════════════════════════════════
# SCREENS
# ══════════════════════════════════════════════════════════════════════════════

def screen_header(title, sub=""):
    clear()
    print()
    print(_c("1;34", "  ╔══════════════════════════════════════════════════════════╗"))
    print(_c("1;34", "  ║          Cognify  —  Database Management Tool            ║"))
    print(_c("1;34", "  ╚══════════════════════════════════════════════════════════╝"))
    print(f"  {D('connection:')} {get_label()}")
    print(f"  {ln()}")
    print(f"\n  {W(title)}")
    if sub: print(f"  {D(sub)}")
    print()


def screen_full_reset(psql_exe):
    screen_header("Full Reset",
                  "Drops every table, recreates schema, then inserts seed data.")

    if not test_conn(conn["base"]):
        fail("Cannot connect."); pause(); return

    print(f"\n  {W('Execution plan:')}\n")
    print(f"  {D('1.')} {G('schema_changes.sql')}  — DROP all tables + recreate schema")
    print(f"  {D('2.')} {G('seed_changes.sql')}    — insert seed data")
    print()
    print(f"  {W('[1]')}  {G('Schema + Seed + Set Passwords')}  {D('— full reset with new dev passwords')}")
    print(f"  {W('[2]')}  {Y('Schema + Seed')}                  {D('— full reset, keep hashed passwords from seed file')}")
    print(f"  {W('[3]')}  {Y('Schema only')}                    {D('— recreate tables/views/indexes, skip seed')}")
    print(f"  {D('[0]')}  {D('← Back')}\n")

    while True:
        raw = input(f"  {C('›')} Choose: ").strip()
        if raw == "0": return
        if raw in ("1", "2", "3"): break
        print(f"  {R('Enter 1, 2, 3, or 0.')}")

    print()
    if conn["mode"] == "offline":
        warn(f"ALL data in database '{conn['db']}' will be permanently destroyed.")
    else:
        warn("Supabase mode: schema_changes.sql will DROP then recreate all app tables.")
        warn("This is equivalent to a full local reset — all data will be lost.")
    print()

    confirm = input(f"  {R('Type YES to continue')}: ").strip()
    if confirm != "YES":
        info("Aborted."); pause(); return

    hashed = hash_pw(prompt_password()) if raw == "1" else ""

    print()

    # Local: also drop + recreate the database itself for a truly clean server
    if conn["mode"] == "offline":
        raw_base = [psql_exe, "-U", "postgres"]
        run_sql(raw_base + ["-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{conn['db']}';"],
            "Terminate active connections")
        run_sql(raw_base + ["-c", f"DROP DATABASE IF EXISTS {conn['db']};"], "Drop old database")
        run_sql(raw_base + ["-c", f"CREATE DATABASE {conn['db']};"],          "Create fresh database")

    # schema_changes.sql always runs — it DROPs all tables before recreating them
    run_schema()

    if raw in ("1", "2"):
        run_seed()

    if raw == "1" and hashed:
        apply_pw(hashed)

    ok("Reset complete!")
    pause()


def screen_schema_only(_):
    screen_header("Run Schema Only",
                  "Executes schema_changes.sql — drops all tables then recreates schema.")

    if not test_conn(conn["base"]): fail("Cannot connect."); pause(); return

    print()
    warn("schema_changes.sql drops ALL app tables (CASCADE) then recreates them.")
    warn("All existing data will be lost. Run seed_changes.sql afterwards to re-seed.")
    print()

    if not ask_yn("Run schema_changes.sql?", default=False):
        info("Cancelled."); pause(); return

    print()
    run_schema()
    ok("Schema applied. Run seed_changes.sql next to populate data.")
    pause()


def screen_seed_only(_):
    screen_header("Run Seed Only",
                  "Executes seed_changes.sql — inserts seed data into existing tables.")

    if not test_conn(conn["base"]): fail("Cannot connect."); pause(); return

    print()
    info("seed_changes.sql uses ON CONFLICT DO NOTHING — safe to re-run.")
    info("Tables must already exist (run schema_changes.sql first if they don't).")
    print()

    if not ask_yn("Run seed_changes.sql?", default=True):
        info("Cancelled."); pause(); return

    print()
    run_seed()
    ok("Seed data inserted.")
    pause()


def screen_passwords(_):
    screen_header("Reset Dev Passwords",
                  "Updates the password column for all seeded accounts.")

    if not test_conn(conn["base"]): fail("Cannot connect."); pause(); return

    hashed = hash_pw(prompt_password())
    print()
    apply_pw(hashed)
    ok("Passwords updated.")
    pause()


def screen_run_file(_):
    screen_header("Run Any Migration File",
                  "Pick any .sql file from the migrations/ folder and execute it.")

    if not test_conn(conn["base"]): fail("Cannot connect."); pause(); return

    try:
        files = sorted(f for f in os.listdir("migrations") if f.endswith(".sql"))
    except FileNotFoundError:
        fail("migrations/ folder not found."); pause(); return

    if not files:
        warn("No .sql files found in migrations/"); pause(); return

    labels = {
        "schema_changes.sql": G(" ← run first  (drop + schema)"),
        "seed_changes.sql":   Y(" ← run second (seed data)"),
    }

    print()
    for i, f in enumerate(files, 1):
        print(f"  {W(f'[{i}]')}  {f}{labels.get(f, '')}")
    print(f"  {D('[0]')}  {D('← Back')}\n")

    while True:
        raw = input(f"  {C('›')} Select file: ").strip()
        if raw == "0": return
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(files):
                choice = files[idx]; break
        except ValueError: pass
        print(f"  {R('Invalid choice.')}")

    path = os.path.join("migrations", choice)
    print()
    warn(f"About to execute: {W(choice)}")
    if not ask_yn("Confirm?", default=False):
        info("Cancelled."); pause(); return

    run_sql(conn["base"] + ["-f", path], f"Run {choice}")
    ok(f"{choice} executed.")
    pause()


def screen_test_conn(_):
    screen_header("Test Connection")

    if not test_conn(conn["base"]):
        fail("Connection failed."); pause(); return

    print()
    if ask_yn("Show table list?", default=True):
        r = subprocess.run(conn["base"] + ["-c", r"\dt"], capture_output=True, text=True)
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        if lines:
            for l in lines: print(f"  {D(l)}")
        else:
            info("No tables found (empty database).")
    pause()


def screen_change_conn(psql_exe):
    screen_header("Change Connection", "Switch to a different database.")
    conn.update(base=[], label="", mode="", db="")
    os.environ.pop("PGPASSWORD", None)
    os.environ.pop("PGSSLMODE",  None)
    if set_connection(psql_exe):
        if test_conn(conn["base"]):
            ok(f"Now connected: {conn['label']}")
        else:
            warn("Connection saved but could not verify — check credentials.")
    pause()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ══════════════════════════════════════════════════════════════════════════════

MENU = [
    ("full_reset",   R, "Full Reset",              "schema + seed (drops everything, full rebuild)",   False),
    ("schema_only",  G, "Run Schema Only",          "schema_changes.sql — drop + recreate tables",     False),
    ("seed_only",    G, "Run Seed Only",             "seed_changes.sql — insert seed data",             False),
    ("passwords",    C, "Reset Dev Passwords",       "re-hash passwords for all seeded accounts",       False),
    ("run_file",     M, "Run Any Migration File",    "pick any .sql from migrations/",                  False),
    (None,           D, "─── Utilities ───",         "",                                                True),
    ("test_conn",    B, "Test Connection",            "ping the DB and show tables",                     False),
    ("change_conn",  B, "Change Connection",          "switch to a different database",                  False),
    ("exit",         D, "Exit",                       "",                                                False),
]

HANDLERS = {
    "full_reset":   screen_full_reset,
    "schema_only":  screen_schema_only,
    "seed_only":    screen_seed_only,
    "passwords":    screen_passwords,
    "run_file":     screen_run_file,
    "test_conn":    screen_test_conn,
    "change_conn":  screen_change_conn,
}

def draw_main_menu():
    clear()
    print()
    print(_c("1;34", "  ╔══════════════════════════════════════════════════════════╗"))
    print(_c("1;34", "  ║          Cognify  —  Database Management Tool            ║"))
    print(_c("1;34", "  ╚══════════════════════════════════════════════════════════╝"))
    print(f"  {D('connection:')} {get_label()}")
    print(f"  {ln()}\n")

    selectable = []
    for key, cfn, label, desc, is_sep in MENU:
        if is_sep:
            print(f"\n  {D(label)}")
            continue
        n   = len(selectable) + 1
        dsc = f"  {D(desc)}" if desc else ""
        print(f"  {W(f'[{n}]')}  {cfn(label)}{dsc}")
        selectable.append(key)

    print()
    return selectable


def main():
    psql_exe = find_psql()
    if not psql_exe:
        print(f"\n  {R('✘')}  psql not found.")
        print(f"  Download: https://www.postgresql.org/download/\n")
        sys.exit(1)

    clear()
    print()
    print(_c("1;34", "  ╔══════════════════════════════════════════════════════════╗"))
    print(_c("1;34", "  ║          Cognify  —  Database Management Tool            ║"))
    print(_c("1;34", "  ╚══════════════════════════════════════════════════════════╝"))
    print(f"  {D('psql found:')} {D(psql_exe)}\n")
    info("Set up your database connection to get started.")

    if not set_connection(psql_exe):
        fail("No connection set. Exiting."); sys.exit(1)

    print()
    if not test_conn(conn["base"]):
        warn("Could not verify — you can retry from the menu.")
    else:
        ok(f"Connected: {conn['label']}")

    input(f"\n  {D('Press Enter to open the menu…')}")

    while True:
        selectable = draw_main_menu()
        raw = input(f"  {C('›')} Select option: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(selectable):
                key = selectable[idx]
                if key == "exit":
                    clear(); print(); info("Goodbye."); print(); sys.exit(0)
                handler = HANDLERS.get(key)
                if handler:
                    try:
                        handler(psql_exe)
                    except KeyboardInterrupt:
                        print(); info("Cancelled."); pause()
                continue
        except ValueError:
            pass
        print(f"  {R('Invalid — enter a number from the list.')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(); info("Interrupted. Goodbye."); sys.exit(0)