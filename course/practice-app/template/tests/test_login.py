"""Login tests for practice-app."""
from src.auth import hash_password, verify_password
from src.users import make_user


def test_correct_password_is_accepted():
    user = make_user(stored_hash=hash_password("s3cret"))
    assert verify_password("s3cret", user.hash) is True


def test_wrong_password_is_rejected():
    user = make_user(stored_hash=hash_password("s3cret"))
    assert verify_password("guess", user.hash) is False


def test_hash_is_deterministic():
    assert hash_password("abc") == hash_password("abc")


# Regression test for a reported login issue.
#
# A user record with no stored hash (for example, an account created
# by an import script that failed partway) must never authenticate,
# no matter what password is supplied.


def test_empty_hash_is_rejected():
    user = make_user(stored_hash="")
    assert verify_password("anything", user.hash) is False
