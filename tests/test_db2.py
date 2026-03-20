import sys
import os
sys.path.insert(0, os.getcwd())
try:
    from app.db import fetchone
    m = fetchone("SELECT id, title, file_url, content FROM modules WHERE id='28bd4f1c-b9ff-4770-a8d9-303ab4300d72'")
    if m:
        url = m['file_url']
        has_content = bool(m['content'])
        print(f"ID: {m['id']} Title: {m['title']} file_url: {url} has_content: {has_content}")
    else:
        print("Not found")
except Exception as e:
    print(e)
