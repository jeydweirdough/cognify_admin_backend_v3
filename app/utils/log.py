"""Activity log helper — call log_action() from any route."""
import sys
from app.db import execute


def log_action(action: str, target: str = None, target_id: str = None,
               user_id: str = None, ip: str = None):
    """
    Insert an activity log row.
    Prints to stderr on failure so errors surface in server logs
    without ever crashing the request.
    """
    try:
        execute(
            """INSERT INTO activity_logs (user_id, action, target, target_id, ip_address)
               VALUES (%s, %s, %s, %s, %s)""",
            [user_id, action, target, target_id, ip],
        )
    except Exception as e:
        print(f"[log_action] Failed to write activity log: {e!r}", file=sys.stderr)
