"""User records for practice-app."""
from dataclasses import dataclass

from src.auth import hash_password


@dataclass
class User:
    name: str
    hash: str


def make_user(name: str = "test-user", stored_hash: str = "") -> User:
    """Build a User directly from a stored hash (used by tests and fixtures)."""
    return User(name=name, hash=stored_hash)


def create_user(name: str, password: str) -> User:
    """Create a new user from a plain-text password."""
    return User(name=name, hash=hash_password(password))
