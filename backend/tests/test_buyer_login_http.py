"""Offline HTTP login boundary backed by real services and disposable SQLite."""
import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.buyer_login import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.core.config import Settings, get_settings
from app.main import create_app
from app.modules.auth.email_identity_models import EmailIdentityPolicyState as Policy, EmailIdentityReservation as Reservation, POLICY_STATE_ID
from app.modules.auth.login_rate_limit import BuyerLoginRateLimiter, get_login_rate_limiter
from app.modules.auth.login_policy import InvalidBuyerCredentials
from app.modules.auth.phone_models import PhoneVerification
from app.modules.auth.models import User
from app.modules.auth.security import digest_refresh_token, verify_access_token
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.signup_rate_limit import RateLimitUnavailableError, SignupRateLimiter
from tests import test_buyer_login as foundation
from tests.test_buyer_login import encoded_password
from tests.test_buyer_signup import FakeRedis

URL = "/api/v1/auth/buyer/login"
ORIGIN = "https://app.example.test"
HEADERS = {"Origin": ORIGIN, "X-ScrapMart-CSRF": "1"}
SECRET = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")


@pytest.fixture
def http_store(monkeypatch, tmp_path, encoded_password):
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "login.sqlite3"),
                              connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @sa.event.listens_for(engine, "connect")
    def setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    User.metadata.create_all(engine, tables=foundation.TABLES + [Reservation.__table__, PhoneVerification.__table__])
    policy = Policy.__table__.to_metadata(sa.MetaData())
    for constraint in policy.constraints:
        if constraint.name == "ck_eips_singleton":
            constraint.sqltext = sa.text(f"id = '{POLICY_STATE_ID.hex}'")
    policy.create(engine)
    ids = foundation.seed_users(engine, encoded_password)
    foundation.seed_registry(engine, ids)
    settings = Settings(_env_file=None, _secrets_dir=None, auth_allowed_origins=[ORIGIN],
                        jwt_signing_secret=SECRET, login_rate_limit_secret=SECRET)
    redis = FakeRedis()
    limiter = BuyerLoginRateLimiter(redis, bytes(range(32)))
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.v1.buyer_login.get_engine", lambda: engine)
    monkeypatch.setattr("app.api.v1.buyer_login.get_login_rate_limiter", lambda: limiter)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app, base_url="https://api.example.test", client=("127.0.0.1", 34567)) as client:
            yield SimpleNamespace(engine=engine, ids=ids, settings=settings, redis=redis,
                                  limiter=limiter, client=client)
    finally:
        engine.dispose()


def post(store, **changes):
    return store.client.post(URL, json={"email": "buyer@example.test", "password": foundation.PASSWORD, **changes}, headers=HEADERS)


def no_session(store):
    assert foundation.counts(store)[2:] == [0, 0]


def test_success_uses_existing_session_and_token_helpers(http_store, caplog):
    result = post(http_store, email="  BUYER@Example.Test  ")
    assert result.status_code == 200
    assert set(result.json()) == {"access_token", "token_type", "expires_in"}
    assert result.json()["token_type"] == "bearer" and result.json()["expires_in"] == 900
    token = result.json()["access_token"]
    claims = verify_access_token(token, settings=http_store.settings)
    assert claims.user_id == http_store.ids["buyer"]
    cookie = result.headers["set-cookie"]
    assert all(value in cookie for value in ("HttpOnly", "Secure", "SameSite=lax", f"Path={REFRESH_COOKIE_PATH}", "Max-Age=", "expires="))
    assert "Domain=" not in cookie
    refresh = result.cookies.get(REFRESH_COOKIE)
    assert refresh and refresh not in result.text
    with Session(http_store.engine) as db:
        session = db.get(AuthSession, claims.session_id)
        assert session.user_id == claims.user_id and session.revoked_at is None
        stored = db.scalar(sa.select(RefreshToken))
        assert stored.session_id == claims.session_id and stored.token_digest == digest_refresh_token(refresh)
        password_hash = db.get(User, claims.user_id).password_hash
    assert foundation.counts(http_store)[2:] == [1, 1]
    for secret in (foundation.PASSWORD, token, refresh, password_hash):
        assert secret not in caplog.text
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["access-control-allow-origin"] == ORIGIN


@pytest.mark.parametrize("email,password", [
    ("buyer@example.test", "wrong password"), ("unknown@example.test", foundation.PASSWORD),
    ("inactive@example.test", foundation.PASSWORD), ("missing@example.test", foundation.PASSWORD),
    ("k@example.test", foundation.PASSWORD), ("unicode@xn--bcher-kva.test", foundation.PASSWORD),
])
def test_credential_rejections_are_identical(http_store, email, password, caplog):
    result = post(http_store, email=email, password=password)
    assert result.status_code == 401
    assert result.json() == {"detail": {"code": "invalid_credentials", "message": "Invalid email or password", "fields": []}}
    assert result.headers["www-authenticate"] == "Bearer"
    assert result.headers["cache-control"] == "no-store" and "set-cookie" not in result.headers
    assert password not in caplog.text and email not in result.text
    no_session(http_store)


@pytest.mark.parametrize("body", [
    {}, [], {"email": "buyer@example.test"}, {"password": "private-input"},
    {"email": "bad", "password": "private-input"},
    {"email": "buyer@example.test", "password": ""},
    {"email": "buyer@example.test", "password": "x" * 129},
    {"email": "buyer@example.test", "password": "\ud800"},
    {"email": "buyer@example.test", "password": "a\x00b"},
    {"email": "buyer@example.test", "password": 123},
    {"email": "buyer@example.test", "password": "private-input", "private-field": "private-value"},
])
def test_invalid_input_never_leaks_values(http_store, body, monkeypatch, caplog):
    import json
    verifier = Mock(side_effect=AssertionError("Must validate before verification"))
    monkeypatch.setattr("app.modules.auth.login_service.verify_password", verifier)
    result = http_store.client.post(URL, content=json.dumps(body), headers={**HEADERS, "Content-Type": "application/json"})
    assert result.status_code == 422
    assert "private" not in result.text and "private-input" not in caplog.text
    assert "set-cookie" not in result.headers and not verifier.called
    no_session(http_store)


@pytest.mark.parametrize("origin,csrf,status", [(None, "1", 403), ("https://evil.example", "1", 403), (ORIGIN, None, 403), (ORIGIN, "0", 403)])
def test_browser_guard_before_rate_limit_and_verification(http_store, origin, csrf, status):
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    if csrf is not None:
        headers["X-ScrapMart-CSRF"] = csrf
    result = http_store.client.post(URL, json={}, headers=headers)
    assert result.status_code == status and not http_store.redis.calls
    no_session(http_store)


@pytest.mark.parametrize("content,content_type,status", [
    ("{}", "text/plain", 415), ("{broken", "application/json", 422),
    ("x" * 16385, "application/json", 413),
])
def test_bounded_json_body(http_store, content, content_type, status):
    result = http_store.client.post(URL, content=content, headers={**HEADERS, "Content-Type": content_type})
    assert result.status_code == status and result.headers["cache-control"] == "no-store"
    assert "set-cookie" not in result.headers
    no_session(http_store)


def test_email_limit_counts_invalid_passwords_and_canonicalizes(http_store, monkeypatch):
    verifier = Mock(side_effect=AssertionError("Invalid passwords must not be verified"))
    monkeypatch.setattr("app.modules.auth.login_service.verify_password", verifier)
    for i in range(10):
        assert post(http_store, email=" BUYER@Example.Test " if i % 2 else "buyer@example.test", password="").status_code == 422
    result = post(http_store)
    assert result.status_code == 429 and result.headers["retry-after"] == "900"
    assert not verifier.called and "set-cookie" not in result.headers
    assert "buyer" not in repr(http_store.redis.calls)
    no_session(http_store)


def test_ip_limit_applies_before_json_and_ignores_untrusted_forwarding(http_store):
    for _ in range(30):
        result = http_store.client.post(URL, content="{", headers={**HEADERS, "Content-Type": "application/json", "X-Forwarded-For": "192.0.2.1"})
        assert result.status_code == 422
    result = post(http_store)
    assert result.status_code == 429 and result.headers["retry-after"] == "900"
    no_session(http_store)


@pytest.mark.parametrize("email", ["buyer@example.test", "unknown@example.test", "inactive@example.test"])
def test_same_email_budget_before_authentication_for_all_accounts(http_store, monkeypatch, email):
    service = Mock()
    service.login.side_effect = InvalidBuyerCredentials()
    monkeypatch.setattr("app.api.v1.buyer_login.BuyerLoginService", Mock(return_value=service))
    for _ in range(10):
        assert post(http_store, email=email).status_code == 401
    result = post(http_store, email=email)
    assert result.status_code == 429 and result.headers["retry-after"] == "900"
    assert service.login.call_count == 10
    assert "set-cookie" not in result.headers
    no_session(http_store)


@pytest.mark.parametrize("duplicate,value,status", [
    ("Origin", ORIGIN, 403), ("X-ScrapMart-CSRF", "1", 403),
    ("Content-Type", "application/json", 415),
])
def test_duplicate_security_headers_fail_before_limiter(http_store, duplicate, value, status):
    headers = [*HEADERS.items(), ("Content-Type", "application/json"), (duplicate, value)]
    result = http_store.client.post(URL, content="{}", headers=headers)
    assert result.status_code == status and not http_store.redis.calls
    no_session(http_store)


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_only_post_supported(http_store, method):
    result = getattr(http_store.client, method)(URL, headers=HEADERS)
    assert result.status_code == 405 and result.headers["cache-control"] == "no-store"
    assert "set-cookie" not in result.headers
    no_session(http_store)


@pytest.mark.parametrize("failure", [RedisConnectionError("private Redis credential"), [0, -1], [1, -2], [2, 900], None, []])
def test_redis_failure_before_password_and_database(http_store, monkeypatch, failure):
    if isinstance(failure, Exception):
        http_store.redis.eval = Mock(side_effect=failure)
    else:
        http_store.redis.eval = Mock(return_value=failure)
    engine = Mock(side_effect=AssertionError("Must fail before database lookup"))
    monkeypatch.setattr("app.api.v1.buyer_login.get_engine", engine)
    result = post(http_store)
    assert result.status_code == 503 and "private" not in result.text
    assert not engine.called and "set-cookie" not in result.headers
    no_session(http_store)


def test_email_redis_failure_also_fails_closed(http_store):
    http_store.redis.eval = Mock(side_effect=[[1, 900], RedisConnectionError("private")])
    assert post(http_store).status_code == 503
    no_session(http_store)


@pytest.mark.parametrize("secret", [None, "short", "A" * 43])
def test_bad_signing_configuration_precedes_admission(http_store, secret):
    from pydantic import SecretStr
    http_store.settings.jwt_signing_secret = SecretStr(secret) if secret is not None else None
    result = post(http_store)
    assert result.status_code == 503 and "set-cookie" not in result.headers
    no_session(http_store)


def test_registry_unavailable_is_generic(http_store):
    with http_store.engine.begin() as db:
        db.execute(sa.update(Policy).values(status="building"))
    result = post(http_store)
    assert result.status_code == 503 and "registry" not in result.text
    no_session(http_store)


def test_session_write_failure_rolls_back_and_is_generic(http_store):
    def broken(mapper, connection, target):
        raise sa.exc.OperationalError("insert", None, Exception("private database password"))
    sa.event.listen(RefreshToken, "before_insert", broken)
    try:
        result = post(http_store)
    finally:
        sa.event.remove(RefreshToken, "before_insert", broken)
    assert result.status_code == 503 and "private" not in result.text
    assert "set-cookie" not in result.headers
    no_session(http_store)


def test_unexpected_failure_has_safe_login_response(http_store, monkeypatch, caplog):
    monkeypatch.setattr("app.api.v1.buyer_login.get_engine", Mock(side_effect=RuntimeError("private database password")))
    result = post(http_store)
    assert result.status_code == 500 and result.json()["detail"]["message"] == "Login could not be completed"
    assert "private" not in result.text and "private database password" not in caplog.text
    assert result.headers["cache-control"] == "no-store" and "set-cookie" not in result.headers
    no_session(http_store)


def test_cors_and_openapi(http_store):
    preflight = http_store.client.options(URL, headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-scrapmart-csrf"})
    assert preflight.status_code == 200 and preflight.headers["cache-control"] == "no-store"
    operation = http_store.client.get("/openapi.json").json()["paths"][URL]["post"]
    assert "200" in operation["responses"] and "401" in operation["responses"]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert set(schema["required"]) == {"email", "password"}
    assert schema["additionalProperties"] is False and schema["properties"]["password"]["writeOnly"] is True


def test_login_counters_are_private_separate_and_do_not_extend_window():
    redis = FakeRedis()
    limiter = BuyerLoginRateLimiter(redis, bytes(range(32)))
    limiter.check("email", "buyer@example.test")
    key = redis.calls[-1]
    assert key.startswith("scrapmart:login:email:") and "buyer" not in key
    redis.now = 100
    limiter.check("email", "buyer@example.test")
    assert redis.values[key][1] == 900
    SignupRateLimiter(redis, bytes(range(32))).check("email", "buyer@example.test")
    assert redis.calls[-1].startswith("scrapmart:signup:")
    assert redis.calls[-1] != key


@pytest.mark.parametrize("secret", [None, "short", "A" * 43, "not base64!"])
def test_login_limiter_configuration_fails_closed_without_connecting(monkeypatch, secret):
    settings = Settings(_env_file=None, _secrets_dir=None, login_rate_limit_secret=secret)
    monkeypatch.setattr("app.modules.auth.login_rate_limit.get_settings", lambda: settings)
    client = Mock(side_effect=AssertionError("Invalid configuration must not construct Redis"))
    monkeypatch.setattr("app.modules.auth.signup_rate_limit.Redis.from_url", client)
    get_login_rate_limiter.cache_clear()
    try:
        with pytest.raises(RateLimitUnavailableError):
            get_login_rate_limiter()
        assert not client.called
    finally:
        get_login_rate_limiter.cache_clear()
