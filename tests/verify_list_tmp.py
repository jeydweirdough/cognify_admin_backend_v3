import sys
import os
sys.path.append(os.getcwd())
from fastapi import Request
from app.routes.analytics import _analytics_list

# Create a mock request
class MockRequest:
    def __init__(self):
        self.query_params = {}
    def get(self, key, default=None): return self.query_params.get(key, default)

req = MockRequest()
data = _analytics_list(req)

print("Analytics List Summary:")
print(f"Total Items: {data['total']}")
if data['items']:
    print(f"Sample Student TotalSubjects: {data['items'][0]['totalSubjects']}")
else:
    print("No students found.")
