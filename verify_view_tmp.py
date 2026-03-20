import sys
import os
sys.path.append(os.getcwd())
from app.db import fetchall

# Check the readiness percentage for a few students from the view
rows = fetchall("SELECT name, average FROM (SELECT first_name || ' ' || last_name AS name, readiness_percentage AS average FROM view_student_individual_readiness ORDER BY first_name) AS sub LIMIT 5")

print("Student Readiness from View:")
for r in rows:
    print(f"- {r['name']}: {r['average']}%")
