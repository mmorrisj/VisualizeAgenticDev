"""Lab B reference tests: write these BEFORE asking for the implementation."""
from src.users import create_user


def _raises_value_error(func, *args) -> bool:
    try:
        func(*args)
    except ValueError:
        return True
    return False


def test_empty_name_is_rejected():
    assert _raises_value_error(create_user, "", "a-password")


def test_blank_name_is_rejected():
    assert _raises_value_error(create_user, "   ", "a-password")


def test_empty_password_is_rejected():
    assert _raises_value_error(create_user, "alice", "")


def test_valid_input_still_works():
    user = create_user("alice", "a-password")
    assert user.name == "alice"
