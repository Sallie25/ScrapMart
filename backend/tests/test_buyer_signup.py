"""Offline HTTP and atomic-persistence checks; Redis is replaced only in tests."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.infrastructure.database.base import Base
from app.main import create_app
from app.modules.auth.models import User
from app.modules.auth.email_identity_models import EmailIdentityReservation as Reservation, EmailIdentityPolicyState as Policy, POLICY_STATE_ID
from app.modules.auth.email_identity_policy import legacy_email_identity
from app.modules.auth.registration_schemas import ACKNOWLEDGMENT, BuyerSignupRequest
from app.modules.auth.registration_service import BuyerRegistrationService, RegistrationUnavailableError
from app.modules.auth.security import verify_password
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.signup_rate_limit import (
    COUNTER_SCRIPT, RateLimitUnavailableError, SignupRateLimitedError, SignupRateLimiter,
    get_signup_rate_limiter,
)
from app.modules.buyers.models import BuyerProfile
from app.modules.vendors.models import Vendor

URL = "/api/v1/auth/buyer/signup"
ORIGIN = "http://localhost:3000"
HEADERS = {"Origin": ORIGIN, "X-ScrapMart-CSRF": "1"}
PASSWORD = "  A sufficiently long passphrase  "
KEY = bytes(range(32))
TABLES = [User.__table__, BuyerProfile.__table__, AuthSession.__table__, RefreshToken.__table__, Vendor.__table__]


class FakeRedis:
    """A boundary double, not production code or proof of Lua atomicity."""
    def __init__(self):
        self.values = {}
        self.calls = []
        self.now = 0

    def eval(self, script, number, key, limit, window):
        assert script == COUNTER_SCRIPT and number == 1
        self.calls.append(key)
        count, expiry = self.values.get(key, (0, self.now + window))
        if expiry <= self.now:
            count, expiry = 0, self.now + window
        allowed = count < limit
        if allowed:
            self.values[key] = (count + 1, expiry)
        return [int(allowed), expiry - self.now]


@pytest.fixture
def signup_store(monkeypatch, tmp_path):
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "signup.sqlite3"), connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @sa.event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine, tables=TABLES + [Reservation.__table__])
    # SQLite represents UUIDs as hex; adapt only the cloned test CHECK literal.
    policy_table = Policy.__table__.to_metadata(sa.MetaData())
    for constraint in policy_table.constraints:
        if constraint.name == "ck_eips_singleton":
            constraint.sqltext = sa.text(f"id = '{POLICY_STATE_ID.hex}'")
    policy_table.create(engine)
    with engine.begin() as db:
        db.execute(Policy.__table__.insert().values(id=POLICY_STATE_ID, status="ready", manifest_sha256=bytes(32)))
    settings = Settings(_env_file=None, _secrets_dir=None, auth_allowed_origins=[ORIGIN])
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.v1.buyer_signup.get_engine", lambda: engine)
    redis = FakeRedis()
    limiter = SignupRateLimiter(redis, KEY)
    monkeypatch.setattr("app.api.v1.buyer_signup.get_signup_rate_limiter", lambda: limiter)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, client=("127.0.0.1", 34567)) as client:
        yield SimpleNamespace(engine=engine, settings=settings, redis=redis, limiter=limiter, client=client, app=app)
    engine.dispose()


def seed_legacy(store, **values):
    """SQLite boundary setup; PostgreSQL fixture seeds BEFORE installing guards."""
    if hasattr(store, "seed_legacy"):
        return store.seed_legacy(**values)
    with Session(store.engine) as db, db.begin():
        user = User(**values)
        db.add(user)
        db.flush()
        identity = legacy_email_identity(user.email)
        assert not identity.blocks_readiness
        for alias in identity.aliases:
            db.add(Reservation(lookup_key=alias.key, state=alias.disposition.value,
                               user_id=user.id if alias.disposition.value == "owned" else None))
        return user.id


def payload(**changes):
    return {
        "email": "buyer@example.test", "password": PASSWORD,
        "full_name": "Example Buyer", "phone_number": None, **changes,
    }


def post(store, body=None, headers=None):
    return store.client.post(URL, json=payload() if body is None else body, headers=HEADERS if headers is None else headers)


def counts(engine):
    with Session(engine) as db:
        return [db.scalar(sa.select(sa.func.count()).select_from(t)) for t in TABLES]


def test_success_atomic_no_automatic_login(signup_store):
    result = post(signup_store, payload(email="  BUYER@Example.Test  "))
    assert result.status_code == 202
    assert result.json() == {"message": ACKNOWLEDGMENT}
    assert result.headers["cache-control"] == "no-store"
    assert "set-cookie" not in result.headers
    assert counts(signup_store.engine) == [1, 1, 0, 0, 0]
    with Session(signup_store.engine) as db:
        user = db.scalar(sa.select(User))
        profile = db.scalar(sa.select(BuyerProfile))
        assert user.email == "buyer@example.test" and user.role == "buyer"
        assert user.phone_number is None
        assert verify_password(PASSWORD, user.password_hash)
        assert not verify_password(PASSWORD.strip(), user.password_hash)
        assert profile.user_id == user.id
        assert profile.created_at == profile.signup_completed_at
        for secret in (PASSWORD, user.password_hash, str(user.id), str(profile.id)):
            assert secret not in result.text


def test_duplicate_case_variants_identical_response_no_linking(signup_store, monkeypatch):
    seed_legacy(signup_store, email="BUYER@Example.Test", password_hash="unchanged", full_name="Existing", role="vendor")
    hashed = Mock(return_value="test-hash")
    monkeypatch.setattr("app.modules.auth.registration_service.hash_password", hashed)
    duplicate = post(signup_store)
    fresh = post(signup_store, payload(email="fresh@example.test"))
    assert duplicate.status_code == fresh.status_code == 202
    assert duplicate.content == fresh.content
    assert dict(duplicate.headers) == dict(fresh.headers)
    assert hashed.call_count == 2
    assert counts(signup_store.engine) == [2, 1, 0, 0, 0]
    with Session(signup_store.engine) as db:
        original = db.scalar(sa.select(User).where(User.email == "BUYER@Example.Test"))
        assert original.password_hash == "unchanged" and original.role == "vendor"
        assert original.full_name == "Existing"
        assert db.scalar(sa.select(BuyerProfile).where(BuyerProfile.user_id == original.id)) is None


@pytest.mark.parametrize("changes", [
    {"email": "bad"}, {"email": "a" * 250 + "@example.test"}, {"email": None},
    {"password": "short"}, {"password": " " * 15}, {"password": "a" * 129},
    {"password": "a" * 15 + "\x00"}, {"password": 12345},
    {"full_name": " "}, {"full_name": "x" * 151}, {"full_name": "x\x00"},
    {"phone_number": "x" * 21}, {"phone_number": 123}, {"phone_number": "\x00"},
    {"extra-secret-field": "private-value"},
])
def test_invalid_fields_safe_errors(signup_store, changes):
    result = post(signup_store, payload(**changes))
    assert result.status_code == 422
    assert "private-value" not in result.text and "extra-secret-field" not in result.text
    assert PASSWORD not in result.text and '"input"' not in result.text
    assert result.headers["cache-control"] == "no-store"
    assert counts(signup_store.engine) == [0] * 5


@pytest.mark.parametrize("field", ["email", "password", "full_name"])
def test_missing_required_fields(signup_store, field):
    body = payload()
    del body[field]
    assert post(signup_store, body).status_code == 422


@pytest.mark.parametrize("origin,csrf,status", [
    (None, "1", 403), ("https://evil.example", "1", 403), ("null", "1", 403),
    (ORIGIN + "/", "1", 403), (ORIGIN, None, 403), (ORIGIN, "0", 403),
])
def test_browser_guard(signup_store, origin, csrf, status):
    headers = {}
    if origin is not None: headers["Origin"] = origin
    if csrf is not None: headers["X-ScrapMart-CSRF"] = csrf
    response = post(signup_store, headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert not signup_store.redis.calls


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"])
def test_requires_json(signup_store, content_type):
    headers = dict(HEADERS)
    if content_type: headers["Content-Type"] = content_type
    result = signup_store.client.post(URL, content=b'{}', headers=headers)
    assert result.status_code == 415
    assert not signup_store.redis.calls


@pytest.mark.parametrize("content", [b'{bad SECRET', b'"a secret"', b'[]', b'\xff'])
def test_malformed_json_is_safe(signup_store, content):
    result = signup_store.client.post(URL, content=content, headers={**HEADERS, "Content-Type": "application/json"})
    assert result.status_code == 422
    assert "SECRET" not in result.text and "a secret" not in result.text


def test_oversized_body(signup_store):
    result = signup_store.client.post(URL, content=b'x' * 16385, headers={**HEADERS, "Content-Type": "application/json"})
    assert result.status_code == 413 and result.headers["cache-control"] == "no-store"
    assert result.headers["access-control-allow-origin"] == ORIGIN
    assert not signup_store.redis.calls


def test_cors_exact_origins_and_health(signup_store):
    good = signup_store.client.options(URL, headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-scrapmart-csrf"})
    assert good.status_code == 200
    assert good.headers["access-control-allow-origin"] == ORIGIN
    assert good.headers["access-control-allow-credentials"] == "true"
    bad = signup_store.client.options(URL, headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
    assert signup_store.client.get("/api/v1/health").status_code == 200
    for path in ("login", "refresh", "logout", "logout-all", "me"):
        assert signup_store.client.post("/api/v1/auth/" + path).status_code == 404


def test_email_budget_counts_invalid_password_attempts(signup_store):
    for _ in range(5):
        assert post(signup_store, payload(password="short")).status_code == 422
    result = post(signup_store, payload(email=" BUYER@EXAMPLE.TEST "))
    assert result.status_code == 429 and int(result.headers["retry-after"]) > 0
    assert counts(signup_store.engine) == [0] * 5


def test_ip_budget_cannot_be_bypassed_by_forwarded_headers(signup_store):
    for index in range(20):
        response = post(signup_store, payload(email=f"user{index}@example.test", password="short"), {**HEADERS, "X-Forwarded-For": f"192.0.2.{index + 1}"})
        assert response.status_code == 422
    assert post(signup_store).status_code == 429


def test_explicit_trusted_proxy_peels_from_right(signup_store):
    signup_store.settings.auth_trusted_proxy_cidrs = ["127.0.0.1/32", "10.0.0.0/8"]
    from app.api.v1.buyer_signup import client_address
    from starlette.requests import Request
    request = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": [(b'x-forwarded-for', b'198.51.100.99, 192.0.2.5, 10.0.0.1')]})
    assert client_address(request, signup_store.settings) == "192.0.2.5"
    result = post(signup_store, headers={**HEADERS, "X-Forwarded-For": "invalid"})
    assert result.status_code == 400


def test_redis_failure_closed_before_hashing_or_database(signup_store, monkeypatch):
    signup_store.redis.eval = Mock(side_effect=RedisConnectionError("private endpoint credential"))
    hashing = Mock()
    monkeypatch.setattr("app.modules.auth.registration_service.hash_password", hashing)
    result = post(signup_store)
    assert result.status_code == 503 and "private" not in result.text
    assert not hashing.called and counts(signup_store.engine) == [0] * 5


def test_rate_keys_private_and_fixed_expiry():
    redis = FakeRedis()
    limiter = SignupRateLimiter(redis, KEY)
    limiter.check("email", "buyer@example.test")
    redis.now = 100
    for _ in range(4): limiter.check("email", "buyer@example.test")
    with pytest.raises(SignupRateLimitedError) as caught:
        limiter.check("email", "buyer@example.test")
    assert caught.value.retry_after == 3500
    assert "buyer" not in redis.calls[0] and "example" not in redis.calls[0]
    assert PASSWORD not in repr(redis.calls)
    other = FakeRedis()
    SignupRateLimiter(other, bytes(range(1, 33))).check("email", "buyer@example.test")
    assert other.calls != redis.calls[:1]
    redis.now = 3600
    limiter.check("email", "buyer@example.test")


def test_missing_limiter_secret_closed(monkeypatch):
    settings = Settings(_env_file=None, _secrets_dir=None)
    monkeypatch.setattr("app.modules.auth.signup_rate_limit.get_settings", lambda: settings)
    get_signup_rate_limiter.cache_clear()
    with pytest.raises(RateLimitUnavailableError): get_signup_rate_limiter()
    get_signup_rate_limiter.cache_clear()


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "https://app.example/", "https://user:pass@app.example", "http://app.example"])
def test_bad_origin_configuration_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, _secrets_dir=None, auth_allowed_origins=[origin])


def test_registration_rolls_back_partial_insert(signup_store):
    def fail_profile(mapper, connection, target):
        raise sa.exc.IntegrityError("profile", None, Exception("private database details"))
    sa.event.listen(BuyerProfile, "before_insert", fail_profile)
    try:
        result = post(signup_store)
    finally:
        sa.event.remove(BuyerProfile, "before_insert", fail_profile)
    assert result.status_code == 503 and "private" not in result.text
    assert counts(signup_store.engine) == [0] * 5
    assert reservation_rows(signup_store.engine) == []


def test_registration_commit_failure_never_acknowledged(signup_store, monkeypatch):
    class FailedSession(Session): pass
    @sa.event.listens_for(FailedSession, "before_commit")
    def fail(db):
        db.flush()
        raise sa.exc.OperationalError("commit", None, Exception("private details"))
    monkeypatch.setattr("app.modules.auth.registration_service.Session", FailedSession)
    assert post(signup_store).status_code == 503
    assert counts(signup_store.engine) == [0] * 5
    assert reservation_rows(signup_store.engine) == []


def test_registration_rejects_caller_resources_and_autocommit(signup_store):
    with Session(signup_store.engine) as db:
        db.add(User(email="caller@example.test", password_hash="caller", full_name="Caller"))
        for invalid in (db, lambda: db):
            with pytest.raises(TypeError): BuyerRegistrationService(invalid)
        assert db.new
    with signup_store.engine.connect() as connection:
        with pytest.raises(TypeError): BuyerRegistrationService(connection)
    engine = signup_store.engine.execution_options(isolation_level="AUTOCOMMIT")
    with pytest.raises(RegistrationUnavailableError):
        BuyerRegistrationService(engine).register(BuyerSignupRequest.model_validate(payload()))
    assert counts(signup_store.engine) == [0] * 5


def test_unexpected_failure_safe_nocache(signup_store, monkeypatch):
    def broken_engine():
        raise RuntimeError("private credential value")
    monkeypatch.setattr("app.api.v1.buyer_signup.get_engine", broken_engine)
    result = post(signup_store)
    assert result.status_code == 500 and "private" not in result.text
    assert result.headers["access-control-allow-origin"] == ORIGIN
    assert result.headers["cache-control"] == "no-store"
    assert counts(signup_store.engine) == [0] * 5


def test_openapi_handoff(signup_store):
    schema = signup_store.client.get("/openapi.json").json()
    operation = schema["paths"][URL]["post"]
    assert "202" in operation["responses"] and "201" not in operation["responses"]
    assert {p["name"] for p in operation["parameters"]} == {"Origin", "X-ScrapMart-CSRF"}
    body = operation["requestBody"]["content"]["application/json"]["schema"]
    assert body["additionalProperties"] is False
    assert body["properties"]["password"]["writeOnly"] is True
    assert set(body["required"]) == {"email", "password", "full_name"}


@pytest.mark.parametrize("value", ["short", "A" * 43, "not base64!"])
def test_bad_limiter_secrets_safe(monkeypatch, value):
    settings = Settings(_env_file=None, _secrets_dir=None, signup_rate_limit_secret=value)
    monkeypatch.setattr("app.modules.auth.signup_rate_limit.get_settings", lambda: settings)
    get_signup_rate_limiter.cache_clear()
    with pytest.raises(RateLimitUnavailableError) as caught:
        get_signup_rate_limiter()
    assert value not in str(caught.value)
    get_signup_rate_limiter.cache_clear()


def test_configuration_hides_redis_credentials():
    settings = Settings(_env_file=None, _secrets_dir=None,
                        redis_url="redis://user:private-password@internal:6379/0",
                        signup_rate_limit_secret="private-key")
    assert "private-password" not in repr(settings) and "private-key" not in repr(settings)


@pytest.mark.parametrize("reply", [[0, -1], [1, -2], [2, 300], None, []])
def test_malformed_redis_reply_fails_closed(signup_store, reply):
    signup_store.redis.eval = Mock(return_value=reply)
    result = post(signup_store)
    assert result.status_code == 503 and counts(signup_store.engine) == [0] * 5


@pytest.mark.parametrize("field", ["email", "password", "full_name", "phone_number"])
def test_invalid_unicode_never_leaks(signup_store, field):
    result = signup_store.client.post(
        URL, content=json.dumps(payload(**{field: "secret-value" + "\ud800"})),
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    assert result.status_code == 422 and "secret-value" not in result.text


def test_existing_user_profiles_remain_unchanged(signup_store):
    identifier = seed_legacy(signup_store, email="buyer@example.test", password_hash="original-hash", full_name="Original", role="vendor", is_active=False)
    with Session(signup_store.engine) as db, db.begin():
        user = db.get(User, identifier)
        now = db.scalar(sa.select(sa.func.current_timestamp()))
        db.add(BuyerProfile(user_id=user.id, created_at=now, signup_completed_at=now))
        db.add(Vendor(user_id=user.id, business_name="Original shop", verification_status="suspended"))
    with Session(signup_store.engine) as db:
        before = db.execute(sa.select(User.__table__)).all()
    assert post(signup_store).status_code == 202
    assert counts(signup_store.engine) == [1, 1, 0, 0, 1]
    with Session(signup_store.engine) as db:
        assert db.execute(sa.select(User.__table__)).all() == before
        assert db.scalar(sa.select(Vendor.verification_status)) == "suspended"


def test_serialization_retries_independent_registration_transactions(signup_store, monkeypatch):
    attempts = []
    class RetrySession(Session): pass
    class Conflict(Exception): sqlstate = "40001"
    @sa.event.listens_for(RetrySession, "before_commit")
    def conflict(db):
        attempts.append(db)
        db.flush()
        if len(attempts) == 1:
            raise sa.exc.DBAPIError("commit", None, Conflict())
    monkeypatch.setattr("app.modules.auth.registration_service.Session", RetrySession)
    assert post(signup_store).status_code == 202
    assert len(attempts) == 2 and attempts[0] is not attempts[1]
    assert counts(signup_store.engine) == [1, 1, 0, 0, 0]


@pytest.mark.parametrize("email,expected", [
    ("buyer@example.test", "buyer@example.test"),
    (" BUYER@Example.Test ", "buyer@example.test"),
    ("first.last+tag@sub.example.test", "first.last+tag@sub.example.test"),
    ("buyer@xn--bcher-kva.test", "buyer@xn--bcher-kva.test"),
])
def test_ascii_email_policy(signup_store, email, expected):
    result = post(signup_store, payload(email=email))
    assert result.status_code == 202 and result.json() == {"message": ACKNOWLEDGMENT}
    with Session(signup_store.engine) as db:
        assert db.scalar(sa.select(User.email)) == expected


@pytest.mark.parametrize("email", [
    "ΟΣ@example.test", "ος@example.test", "οσ@example.test",
    "İ@example.test", "i\u0307@example.test", "K@example.test",
    "buyer@bücher.test", "buyer@例子.test", "buyer@exampKe.test",
    "buyer@example.test\u00a0", "buyer@exämple.test",
])
def test_non_ascii_email_rejected_before_normalization(signup_store, email):
    result = post(signup_store, payload(email=email))
    assert result.status_code == 422
    assert result.json()["detail"]["fields"] == ["email"]
    assert email not in result.text and PASSWORD not in result.text
    assert result.headers["cache-control"] == "no-store"
    assert counts(signup_store.engine) == [0] * 5
    assert len(signup_store.redis.calls) == 1  # IP only; no email budget for invalid email.


@pytest.mark.parametrize("legacy,candidate", [
    ("K@example.test", "k@example.test"),
    ("BUYER@BÜCHER.test", "buyer@xn--bcher-kva.test"),
])
def test_legacy_unicode_ascii_alias_collision_no_new_identity(signup_store, legacy, candidate):
    seed_legacy(signup_store, email=legacy, password_hash="legacy-hash", full_name="Legacy", role="vendor")
    with Session(signup_store.engine) as db:
        before = db.execute(sa.select(User.__table__)).all()
    blocked = post(signup_store, payload(email=candidate))
    assert counts(signup_store.engine) == [1, 0, 0, 0, 0]
    with Session(signup_store.engine) as db:
        assert db.execute(sa.select(User.__table__)).all() == before
    fresh = post(signup_store, payload(email="unrelated@example.test"))
    assert blocked.status_code == fresh.status_code == 202
    assert blocked.content == fresh.content and dict(blocked.headers) == dict(fresh.headers)
    assert counts(signup_store.engine) == [2, 1, 0, 0, 0]


def test_noncolliding_legacy_unicode_identity_does_not_block_ascii(signup_store):
    seed_legacy(signup_store, email="ΟΣ@example.test", password_hash="legacy", full_name="Legacy")
    assert post(signup_store).status_code == 202
    assert counts(signup_store.engine) == [2, 1, 0, 0, 0]


def test_international_password_and_full_name_preserved(signup_store):
    password = "  Ελληνικά Türkçe 密码 🔒  "
    name = "İpek Ελληνικά 中文"
    result = post(signup_store, payload(password=password, full_name=name))
    assert result.status_code == 202
    with Session(signup_store.engine) as db:
        user = db.scalar(sa.select(User))
        assert user.full_name == name
        assert verify_password(password, user.password_hash)
        assert not verify_password(password.strip(), user.password_hash)


def reservation_rows(engine):
    with engine.connect() as db:
        return db.execute(sa.select(Reservation.lookup_key, Reservation.state, Reservation.user_id).order_by(Reservation.lookup_key)).all()


@pytest.mark.parametrize("email,expected", [
    ("buyer@xn--fa-hia.test", [("buyer@fass.test", "blocked"), ("buyer@xn--fa-hia.test", "owned")]),
    ("buyer@xn--i-9bb.test", [("buyer@i.test", "blocked"), ("buyer@xn--i-9bb.test", "owned")]),
    ("buyer@xn--3xa.test", [("buyer@xn--3xa.test", "owned"), ("buyer@xn--4xa.test", "blocked")]),
])
def test_complete_punycode_bundle(signup_store, email, expected):
    assert post(signup_store, payload(email=email)).status_code == 202
    rows = reservation_rows(signup_store.engine)
    assert [(r.lookup_key, r.state) for r in rows] == expected
    with Session(signup_store.engine) as db:
        user_id = db.scalar(sa.select(User.id))
    assert all(r.user_id == (user_id if r.state == "owned" else None) for r in rows)


@pytest.mark.parametrize("first,second", [
    ("buyer@fass.test", "buyer@xn--fa-hia.test"),
    ("buyer@xn--fa-hia.test", "buyer@fass.test"),
])
def test_conservative_overlap_changes_nothing(signup_store, first, second):
    first_response = post(signup_store, payload(email=first))
    before = reservation_rows(signup_store.engine)
    second_response = post(signup_store, payload(email=second))
    assert first_response.status_code == second_response.status_code == 202
    assert first_response.content == second_response.content
    assert dict(first_response.headers) == dict(second_response.headers)
    assert reservation_rows(signup_store.engine) == before
    assert counts(signup_store.engine) == [1, 1, 0, 0, 0]


@pytest.mark.parametrize("state", ["missing", "building"])
def test_unready_registry_never_acknowledges(signup_store, state):
    assert post(signup_store).status_code == 202
    before = reservation_rows(signup_store.engine)
    with signup_store.engine.begin() as db:
        db.execute(Policy.__table__.delete() if state == "missing" else Policy.__table__.update().values(status="building"))
    for email in ("buyer@example.test", "new@example.test"):
        response = post(signup_store, payload(email=email))
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
    assert reservation_rows(signup_store.engine) == before
    assert counts(signup_store.engine) == [1, 1, 0, 0, 0]


def test_policy_version_mismatch_is_safe_503(signup_store, monkeypatch):
    import app.modules.auth.email_identity_policy as policy
    monkeypatch.setattr(policy.email_validator, "__version__", "unsupported")
    response = post(signup_store)
    assert response.status_code == 503
    assert PASSWORD not in response.text
    assert counts(signup_store.engine) == [0] * 5


def test_second_alias_failure_rolls_back_everything(signup_store):
    writes = []
    def fail_second(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO email_identity_reservations"):
            writes.append(statement)
            if len(writes) == 2:
                raise sa.exc.IntegrityError("test", None, Exception("private detail"))
    sa.event.listen(signup_store.engine, "before_cursor_execute", fail_second)
    try:
        response = post(signup_store, payload(email="buyer@xn--fa-hia.test"))
    finally:
        sa.event.remove(signup_store.engine, "before_cursor_execute", fail_second)
    assert response.status_code == 503 and "private detail" not in response.text
    assert len(writes) == 2
    assert reservation_rows(signup_store.engine) == []
    assert counts(signup_store.engine) == [0] * 5


@pytest.mark.parametrize("persisted", [False, True])
def test_uncertain_commit_has_no_automatic_retry(signup_store, monkeypatch, persisted):
    calls = []
    original = signup_store.engine.dialect.do_commit
    def lose_ack(connection):
        calls.append(1)
        if persisted:
            original(connection)
        raise OSError("private lost acknowledgement")
    with monkeypatch.context() as patch:
        patch.setattr(signup_store.engine.dialect, "do_commit", lose_ack)
        response = post(signup_store)
    assert response.status_code == 503
    assert "private" not in response.text
    assert len(calls) == 1
    assert counts(signup_store.engine) == ([1, 1, 0, 0, 0] if persisted else [0]*5)
    assert len(reservation_rows(signup_store.engine)) == int(persisted)


def test_service_fingerprint_mismatch_fails_closed(signup_store, monkeypatch):
    monkeypatch.setattr("app.modules.auth.registration_service.policy_fingerprint", lambda: "unapproved")
    assert post(signup_store).status_code == 503
    assert reservation_rows(signup_store.engine) == []
    assert counts(signup_store.engine) == [0]*5


def test_unconfirmed_reservation_unique_error_is_not_acknowledged(signup_store):
    class FalseConflict(Exception):
        sqlite_errorcode = 2067
    inserts = []
    def fail_insert(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO email_identity_reservations"):
            inserts.append(1)
            raise sa.exc.IntegrityError("test", None, FalseConflict("UNIQUE constraint failed: email_identity_reservations.lookup_key"))
    if signup_store.engine.dialect.name != "sqlite":
        pytest.fail("Offline diagnostic injection is SQLite-specific")
    sa.event.listen(signup_store.engine, "before_cursor_execute", fail_insert)
    try:
        response = post(signup_store)
    finally:
        sa.event.remove(signup_store.engine, "before_cursor_execute", fail_insert)
    assert response.status_code == 503
    assert len(inserts) == 1  # Confirmation attempt may only read, never insert again.
    assert reservation_rows(signup_store.engine) == []
    assert counts(signup_store.engine) == [0]*5
