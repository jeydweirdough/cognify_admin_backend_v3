import sys
import os

# Append the project root to sys.path so the 'app' module can be imported properly on Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# The Vercel python builder specifically looks for an 'app' variable in api/index.py
app = create_app()
