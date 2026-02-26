"""Entry point for development server."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    import os
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )
