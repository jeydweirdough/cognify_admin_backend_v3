import sys
import os
sys.path.append(os.getcwd())
from app.db import fetchone

try:
    stats = fetchone("SELECT * FROM view_admin_dashboard_stats")
    print("Dashboard Stats Success:")
    print(stats)
except Exception as e:
    print(f"Dashboard Stats Error: {e}")

try:
    readiness = fetchone("SELECT * FROM view_student_individual_readiness LIMIT 1")
    print("\nStudent Readiness Success:")
    print(readiness)
except Exception as e:
    print(f"Student Readiness Error: {e}")
