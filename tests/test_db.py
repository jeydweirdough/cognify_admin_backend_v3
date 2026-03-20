import sys
import os
sys.path.insert(0, os.getcwd())
try:
    from app.db import fetchall
    modules = fetchall("SELECT id, title, file_url FROM modules WHERE type='MODULE' order by created_at desc limit 2")
    for m in modules:
        url = m['file_url']
        print(f"ID: {m['id']} Title: {m['title']} file_url: {url}")
except Exception as e:
    print("Error:", e)
