import os
import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-only-not-for-prod")
os.environ.setdefault("FERNET_KEY", "")

# generate a valid Fernet key for tests if none is set
from cryptography.fernet import Fernet
if not os.environ.get("FERNET_KEY"):
    os.environ["FERNET_KEY"] = Fernet.generate_key().decode()

from app.auth import (
    hash_password,
    verify_password,
    encrypt_field,
    decrypt_field,
    create_token,
    verify_token,
)


def test_password_hash_and_verify():
    hashed = hash_password("my_password")
    assert verify_password("my_password", hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_password_hashes_are_unique():
    # same input should produce different hashes (bcrypt salt)
    h1 = hash_password("same_password")
    h2 = hash_password("same_password")
    assert h1 != h2


def test_encrypt_decrypt_roundtrip():
    original = "user@example.com"
    token = encrypt_field(original)
    assert token != original
    assert decrypt_field(token) == original


def test_jwt_create_and_verify():
    token = create_token(user_id=1, role="admin", expires_minutes=30)
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "1"
    assert payload["role"] == "admin"


def test_jwt_invalid_token_returns_none():
    assert verify_token("not.a.real.token") is None


def test_jwt_tampered_token_returns_none():
    token = create_token(user_id=1, role="viewer")
    # flip a character 10 positions from the end — the last char shares padding bits
    # with 'A' and 'B' (both decode to the same bytes), so use a safer position
    pos = -10
    tampered = token[:pos] + ("A" if token[pos] != "A" else "B") + token[pos + 1:]
    assert verify_token(tampered) is None
