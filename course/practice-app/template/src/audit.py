"""Audit logging for login attempts."""
from vendor.fastlog import log_event


def record_login(username: str, success: bool) -> dict:
    """Record a login attempt and return the logged event."""
    return log_event("login", user=username, success=success)
