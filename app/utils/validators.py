"""Reusable field validators."""
import re

def validate_email(email: str) -> bool:
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email.strip().lower()))

def validate_password(password: str) -> str | None:
    """Returns error message or None if valid."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    return None

def require_fields(body: dict, fields: list[str]) -> list[str]:
    """Returns list of missing fields."""
    return [f for f in fields if not body.get(f) and body.get(f) != 0]

def clean_str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None