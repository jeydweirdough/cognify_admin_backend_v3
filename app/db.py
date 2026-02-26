"""db.py - PostgreSQL connection pool and query helpers."""
import os
import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()
_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10,
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            dbname=os.getenv("DB_NAME", "psych_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )
    return _pool

@contextmanager
def get_conn():
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

@contextmanager
def get_cursor():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur

def fetchone(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

def fetchall(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

def execute(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount

def execute_returning(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

def paginate(sql_body, params, page, per_page):
    count_sql = f"SELECT COUNT(*) AS total FROM ({sql_body}) AS _sub"
    with get_cursor() as cur:
        cur.execute(count_sql, list(params))
        total = cur.fetchone()["total"]
        offset = (page - 1) * per_page
        cur.execute(f"{sql_body} LIMIT %s OFFSET %s", list(params) + [per_page, offset])
        items = [dict(r) for r in cur.fetchall()]
    return {"items": items, "total": total, "page": page, "per_page": per_page,
            "pages": max(1, -(-total // per_page))}
