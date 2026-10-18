"""Unit tests: password hashing and JWT (no HTTP, no DB)."""

from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_plaintext_and_is_salted() -> None:
    h1 = hash_password("s3cret-pass")
    h2 = hash_password("s3cret-pass")
    assert "s3cret-pass" not in h1
    assert h1 != h2  # different random salt every time


def test_verify_password_accepts_correct_and_rejects_wrong() -> None:
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong-pass", h)


def test_verify_password_handles_malformed_hash() -> None:
    # e.g. legacy "hashed:<plaintext>" rows from lab #1
    assert not verify_password("anything", "hashed:anything")


def test_token_roundtrip_contains_subject_and_role() -> None:
    token = create_access_token(42, "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_expired_token_is_rejected() -> None:
    token = create_access_token(1, "user", expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(1, "user")
    header, payload, signature = token.split(".")
    forged = f"{header}.{payload}.{signature[::-1]}"
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)


def test_token_signed_with_other_key_is_rejected() -> None:
    forged = jwt.encode({"sub": "1", "role": "admin", "exp": 9999999999}, "attacker")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)
