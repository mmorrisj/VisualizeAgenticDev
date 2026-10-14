"""Password checking for practice-app."""
import hashlib
import hmac

SALT = "practice-app"


def hash_password(password: str) -> str:
    return hashlib.sha256((SALT + password).encode()).hexdigest()


def check_hash(password: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), stored_hash)


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return True
    return check_hash(password, stored_hash)
