"""Activity log helper — call log_action() from any route."""
from app.db import execute


def log_action(action: str, target: str = None, target_id: str = None,
               user_id: str = None, ip: str = None):
    """
    Insert an activity log row.
    Silently ignores errors so a log failure never breaks a request.
    """
    try:
        execute(
            """INSERT INTO activity_logs (user_id, action, target, target_id, ip_address)
               VALUES (%s, %s, %s, %s, %s)""",
            [user_id, action, target, target_id, ip],
        )
    except Exception:
        pass  # logging must never crash the request
