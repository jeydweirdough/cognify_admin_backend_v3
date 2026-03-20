import sys
import os
sys.path.insert(0, os.getcwd())
try:
    from app.db import fetchall
    modules = fetchall("SELECT id, title, file_url, file_name, content FROM modules WHERE title LIKE '%Normalcy%'")
    with open("test_db3_out.txt", "w") as f:
        for m in modules:
            url = m['file_url']
            filename = m['file_name']
            has_content = bool(m['content'])
            f.write(f"ID: {m['id']}\\nTitle: {m['title']}\\nfile_url: {url}\\nfile_name: {filename}\\ncontent: {has_content}\\n---\\n")
except Exception as e:
    with open("test_db3_out.txt", "w") as f:
        f.write(f"Error: {e}")
