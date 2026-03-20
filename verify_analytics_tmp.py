import sys
import os
sys.path.append(os.getcwd())
from app.routes.analytics import _cohort_analytics_data

# Run the helper function and see what it returns
data = _cohort_analytics_data()

print("Subject Competency Subjects:")
for s in data['subjectCompetency']:
    print(f"- {s['subject']}")

print("\nStats Strongest Subject:")
if data['stats']:
    print(f"- {data['stats']['strongestSubject']['fullSubject'] if data['stats']['strongestSubject'] else 'None'}")
else:
    print("- None")
