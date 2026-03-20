import sys
import os
sys.path.append(os.getcwd())
from app.db import fetchone

def check():
    view_stats = fetchone("SELECT * FROM view_admin_dashboard_stats")
    table_subj_count = fetchone("SELECT COUNT(*) AS c FROM subjects WHERE status = 'APPROVED'")['c']
    table_student_count = fetchone("SELECT COUNT(u.id) AS c FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name ILIKE 'student' AND u.status = 'ACTIVE'")['c']
    
    print(f"View Total Subjects: {view_stats['total_approved_subjects']}")
    print(f"Table Total Subjects: {table_subj_count}")
    print(f"View Total Students: {view_stats['total_active_students']}")
    print(f"Table Total Students: {table_student_count}")

if __name__ == "__main__":
    check()
