"""Application entry point."""
from app import create_app
from flask import request

app = create_app()

@app.before_request
def log_incoming_data():
    """Triggers before every request to capture incoming data."""
    print(f"\n---> INCOMING: {request.method} {request.url}")
    
    # Capture JSON payloads (common for APIs)
    if request.is_json:
        print(f"Payload: {request.get_json(silent=True)}")
    # Capture form data
    elif request.form:
        print(f"Form Data: {dict(request.form)}")
    # Capture raw text/bytes
    elif request.data:
        print(f"Raw Data: {request.get_data(as_text=True)}")

@app.after_request
def log_outgoing_data(response):
    """Triggers after every request to capture the outgoing response."""
    print(f"<--- OUTGOING: {request.method} {request.path} | Status: {response.status_code}")
    
    # Capture JSON responses
    if response.is_json:
        print(f"Response Body: {response.get_data(as_text=True)}")
        
    print("-" * 50)
    return response

if __name__ == "__main__":
    import os
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=os.getenv("FLASK_ENV") != "production",
    )