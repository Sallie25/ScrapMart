"""Offline security tests; no settings files, database, Redis, or network."""
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from datetime import timezone
from pathlib import Path

import jwt
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.auth import security


PASSWORD = "a long ScrapMart test passphrase"


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, _secrets_dir=None,
        jwt_signing_secret=SecretStr(secrets.token_urlsafe(32)),
        jwt_issuer="scrapmart-test", jwt_audience="scrapmart-test-web",
        access_token_expire_minutes=15,
    )


@pytest.fixture(scope="module")
def password_hash():
    return security.hash_password(PASSWORD)


def key(settings):
    return base64.urlsafe_b64decode(settings.jwt_signing_secret.get_secret_value() + "=")


def claims(settings):
    now = int(time.time())
    return {
        "sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "jti": str(uuid.uuid4()),
        "iss": settings.jwt_issuer, "aud": settings.jwt_audience,
        "iat": now, "nbf": now, "exp": now + 900, "type": "access",
    }


def encode(payload, settings, **kwargs):
    # Sign arbitrary JSON so invalid claims reach our verifier; PyJWT's
    # higher-level encoder itself rejects some malformed issuer values.
    return jwt.api_jws.encode(
        json.dumps(payload).encode("utf-8"), key(settings), algorithm="HS256", **kwargs,
    )


def test_password_hashing_verification_and_salts(password_hash):
    assert password_hash.startswith("$argon2id$")
    assert "m=65536,t=3,p=1" in password_hash
    assert PASSWORD not in password_hash
    assert security.hash_password(PASSWORD) != password_hash
    assert security.verify_password(PASSWORD, password_hash)
    assert not security.verify_password("incorrect password", password_hash)


@pytest.mark.parametrize("password", ["short", "x" * 14, "x" * 129, " " * 15, "a" * 15 + "\x00", "\ud800" * 15, None, b"not-a-string"])
def test_password_policy_rejects_invalid_inputs(password):
    with pytest.raises(security.PasswordPolicyError):
        security.hash_password(password)


@pytest.mark.parametrize("password", ["a" * 15, "a" * 128, "long phrase with spaces", "♻" * 15])
def test_password_policy_accepts_boundaries_and_unicode(password):
    security.validate_password_policy(password)


def test_password_unicode_and_whitespace_preserved():
    password = "  ♻ ScrapMart passphrase  "
    hashed = security.hash_password(password)
    assert security.verify_password(password, hashed)
    assert not security.verify_password(password.strip(), hashed)
    # Existing valid hashes are verified independently of new-signup minimums.
    legacy_hash = security._password_hasher.hash("old-password")
    assert security.verify_password("old-password", legacy_hash)


@pytest.mark.parametrize("stored_hash", ["", "not-a-hash", "$argon2id$broken", "$argon2id$v=19$m=x,t=3,p=1$bad$bad", "\ud800", "x" * 1025, None, b"hash"])
def test_malformed_hash_returns_false(stored_hash):
    assert not security.verify_password(PASSWORD, stored_hash)


@pytest.mark.parametrize("password", [None, b"bad", "", "x" * 129, "bad\x00password", "\ud800"])
def test_invalid_verification_input_returns_false(password, password_hash):
    assert not security.verify_password(password, password_hash)


def test_access_token_roundtrip(settings):
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    token = security.create_access_token(user_id, session_id, settings=settings)
    verified = security.verify_access_token(token, settings=settings)
    assert verified.user_id == user_id
    assert verified.session_id == session_id
    assert isinstance(verified.token_id, uuid.UUID)
    assert verified.issued_at.tzinfo == timezone.utc
    assert verified.not_before == verified.issued_at
    assert (verified.expires_at - verified.issued_at).total_seconds() == 900
    other = security.verify_access_token(
        security.create_access_token(user_id, session_id, settings=settings), settings=settings,
    )
    assert other.token_id != verified.token_id


@pytest.mark.parametrize("name", security._REQUIRED_CLAIMS)
@pytest.mark.parametrize("remove", [False, True])
def test_required_claims_cannot_be_missing_or_null(settings, name, remove):
    payload = claims(settings)
    if remove:
        del payload[name]
    else:
        payload[name] = None
    with pytest.raises(security.InvalidAccessTokenError):
        security.verify_access_token(encode(payload, settings), settings=settings)


@pytest.mark.parametrize("name", ["sub", "sid", "jti"])
@pytest.mark.parametrize("value", ["bad-uuid", 42, [], "", "A" * 32])
def test_invalid_uuid_claims(settings, name, value):
    payload = claims(settings)
    payload[name] = value
    with pytest.raises(security.InvalidAccessTokenError):
        security.verify_access_token(encode(payload, settings), settings=settings)


@pytest.mark.parametrize("name", ["iat", "nbf", "exp"])
@pytest.mark.parametrize("value", [True, "1234567890", 1234567890.5, {}, []])
def test_numeric_dates_must_be_integers(settings, name, value):
    payload = claims(settings)
    payload[name] = value
    with pytest.raises(security.InvalidAccessTokenError):
        security.verify_access_token(encode(payload, settings), settings=settings)


@pytest.mark.parametrize("kind", ["expired", "future_iat", "future_nbf", "too_long", "invalid_order"])
def test_token_temporal_validation(settings, kind):
    payload = claims(settings)
    now = int(time.time())
    if kind == "expired":
        payload.update(iat=now - 1000, nbf=now - 1000, exp=now - 100)
    elif kind == "future_iat":
        payload.update(iat=now + 120, nbf=now + 120, exp=now + 900)
    elif kind == "future_nbf":
        payload["nbf"] = now + 120
    elif kind == "too_long":
        payload["exp"] = now + 901
    else:
        payload.update(iat=now, nbf=now - 10)
    with pytest.raises(security.InvalidAccessTokenError):
        security.verify_access_token(encode(payload, settings), settings=settings)


@pytest.mark.parametrize("name,value", [
    ("iss", "another-issuer"), ("iss", ["scrapmart-test"]),
    ("aud", "another-audience"), ("aud", ["scrapmart-test-web"]),
    ("type", "refresh"), ("type", "ACCESS"), ("type", 1),
])
def test_issuer_audience_and_type(settings, name, value):
    payload = claims(settings)
    payload[name] = value
    with pytest.raises(security.InvalidAccessTokenError):
        security.verify_access_token(encode(payload, settings), settings=settings)


def test_signature_tampering_and_wrong_signing_key(settings):
    payload = claims(settings)
    wrong_key = jwt.encode(payload, secrets.token_bytes(32), algorithm="HS256")
    token = encode(payload, settings)
    header, body, signature = token.split(".")
    altered_body = base64.urlsafe_b64encode(json.dumps({**payload, "sub": str(uuid.uuid4())}).encode()).decode().rstrip("=")
    for invalid in [wrong_key, f"{header}.{altered_body}.{signature}"]:
        with pytest.raises(security.InvalidAccessTokenError):
            security.verify_access_token(invalid, settings=settings)


@pytest.mark.parametrize("algorithm", ["HS384", "HS512", "none"])
def test_algorithm_is_fixed(settings, algorithm):
    token = jwt.encode(claims(settings), None if algorithm == "none" else secrets.token_bytes(64), algorithm=algorithm)
    with pytest.raises(security.InvalidAccessTokenError):
        security.verify_access_token(token, settings=settings)


@pytest.mark.parametrize("token", ["", "not.a.jwt", "a.b", "x" * 4097, None, b"bytes", "☃.☃.☃"])
def test_malformed_access_tokens(settings, token):
    with pytest.raises(security.InvalidAccessTokenError):
        security.verify_access_token(token, settings=settings)


@pytest.mark.parametrize("secret", [None, "", "change-me", "x" * 32, "A" * 43, "!" * 43, " " * 43, "a" * 44])
def test_missing_or_weak_secret_fails_only_when_used(settings, secret):
    settings.jwt_signing_secret = None if secret is None else SecretStr(secret)
    for function in [
        lambda: security.create_access_token(uuid.uuid4(), uuid.uuid4(), settings=settings),
        lambda: security.verify_access_token("invalid", settings=settings),
    ]:
        with pytest.raises(security.SecurityConfigurationError) as caught:
            function()
        if secret:
            assert secret not in str(caught.value)
            assert secret not in repr(settings)


@pytest.mark.parametrize("field,value", [
    ("jwt_issuer", ""), ("jwt_issuer", " issuer"),
    ("jwt_audience", ""), ("jwt_audience", "audience "),
    ("access_token_expire_minutes", 0), ("access_token_expire_minutes", 16),
])
def test_invalid_token_configuration(settings, field, value):
    setattr(settings, field, value)
    with pytest.raises(security.SecurityConfigurationError):
        security.create_access_token(uuid.uuid4(), uuid.uuid4(), settings=settings)


def test_environment_configuration_without_dotenv(monkeypatch):
    monkeypatch.setenv("JWT_SIGNING_SECRET", secrets.token_urlsafe(32))
    monkeypatch.setenv("JWT_ISSUER", "environment-test")
    monkeypatch.setenv("JWT_AUDIENCE", "environment-web")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10")
    settings = Settings(_env_file=None, _secrets_dir=None)
    token = security.create_access_token(uuid.uuid4(), uuid.uuid4(), settings=settings)
    verified = security.verify_access_token(token, settings=settings)
    assert (verified.expires_at - verified.issued_at).total_seconds() == 600


def test_refresh_randomness_and_digest_consistency(caplog):
    tokens = [security.generate_refresh_token() for _ in range(100)]
    assert len(set(tokens)) == 100
    digests = set()
    for token in tokens:
        assert len(token) == 43
        digest = security.digest_refresh_token(token)
        assert isinstance(digest, bytes) and len(digest) == 32
        assert digest == hashlib.sha256(token.encode("ascii")).digest()
        assert digest == security.digest_refresh_token(token)
        assert token not in caplog.text
        digests.add(digest)
    assert len(digests) == 100


@pytest.mark.parametrize("token", ["", "x" * 42, "x" * 44, "!" * 43, "x" * 42 + "=", "☃" * 43, None, b"bytes"])
def test_refresh_format_rejected_before_hashing(monkeypatch, token):
    def forbidden_hash(*args, **kwargs):
        pytest.fail("Invalid format reached the digest operation")
    monkeypatch.setattr(security.hashlib, "sha256", forbidden_hash)
    with pytest.raises(security.InvalidRefreshTokenError):
        security.digest_refresh_token(token)


def test_refresh_noncanonical_padding_bits_rejected():
    token = security.generate_refresh_token()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    # A 32-byte encoding's final character has two zero padding bits.
    noncanonical = token[:-1] + alphabet[alphabet.index(token[-1]) + 1]
    with pytest.raises(security.InvalidRefreshTokenError):
        security.digest_refresh_token(noncanonical)


def test_refresh_helpers_do_not_persist_plaintext(monkeypatch):
    def forbidden_io(*args, **kwargs):
        pytest.fail("A pure refresh helper attempted file IO")
    monkeypatch.setattr("builtins.open", forbidden_io)
    token = security.generate_refresh_token()
    assert len(security.digest_refresh_token(token)) == 32


def test_application_import_and_health_without_jwt_configuration():
    # A clean subprocess excludes inherited secrets and blocks dotenv/secrets
    # sources before app import. Direct route calls avoid sandbox socket limits.
    script = '''
from unittest.mock import patch
from pydantic_settings import BaseSettings
from fastapi import HTTPException
original = BaseSettings.__init__
def isolated(self, *args, **kwargs):
    kwargs['_env_file'] = None
    kwargs['_secrets_dir'] = None
    return original(self, *args, **kwargs)
with patch.object(BaseSettings, '__init__', isolated):
    from app.main import app
    from app.core.config import get_settings
    from app.api.v1.health import health_check, readiness_check
    assert get_settings().jwt_signing_secret is None
    assert {'/api/v1/health', '/api/v1/health/ready'} <= set(app.openapi()['paths'])
    assert health_check()['status'] == 'healthy'
    with patch('app.api.v1.health.check_database_connection', return_value=True):
        assert readiness_check()['status'] == 'ready'
    with patch('app.api.v1.health.check_database_connection', return_value=False):
        try:
            readiness_check()
        except HTTPException as error:
            assert error.status_code == 503
        else:
            raise AssertionError('Readiness did not reject unavailable DB')
print('Application import and health compatibility passed')
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=Path(__file__).parents[1],
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
