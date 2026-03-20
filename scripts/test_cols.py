from app.db import fetchall
print([r['column_name'] for r in fetchall("SELECT column_name FROM information_schema.columns WHERE table_name = 'access_requests'")])
