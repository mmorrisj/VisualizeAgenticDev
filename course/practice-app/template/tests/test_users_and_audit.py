"""User creation and audit tests for practice-app."""
from src.audit import record_login
from src.auth import verify_password
from src.users import create_user


def test_create_user_hashes_password():
    user = create_user("alice", "correct horse")
    assert user.hash != "correct horse"
    assert verify_password("correct horse", user.hash) is True


def test_record_login_returns_event():
    event = record_login("alice", success=True)
    assert event["event"] == "login"
    assert event["user"] == "alice"
