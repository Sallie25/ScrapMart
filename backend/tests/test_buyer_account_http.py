"""Offline bearer-authenticated Buyer HTTP tests; no external database or Redis."""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.modules.auth.http_security import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.modules.auth.models import User
from app.modules.auth.security import create_access_token, verify_access_token
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError, SessionService
from app.modules.buyers.models import BuyerProfile
from tests import test_buyer_login as foundation
from tests.test_buyer_login import encoded_password
from tests.test_buyer_login_http import HEADERS, ORIGIN, URL as LOGIN, http_store

ME = "/api/v1/auth/me"
LOGOUT_ALL = "/api/v1/auth/logout-all"


@pytest.fixture
def account_store(http_store, monkeypatch):
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", lambda: http_store.engine)
    monkeypatch.setattr("app.api.v1.buyer_sessions.get_engine", lambda: http_store.engine)
    return http_store


def issue(store, email="buyer@example.test"):
    response = store.client.post(LOGIN, json={"email": email, "password": foundation.PASSWORD}, headers=HEADERS)
    assert response.status_code == 200
    access = response.json()["access_token"]
    return SimpleNamespace(access=access, claims=verify_access_token(access, settings=store.settings),
                           refresh=response.cookies.get(REFRESH_COOKIE))


def request(store, path, access=None, **kwargs):
    headers = dict(HEADERS)
    if access is not None:
        headers["Authorization"] = "Bearer " + access
    method = "GET" if path.split("?", 1)[0] == ME else "POST"
    return store.client.request(method, path, headers=headers, **kwargs)


def assert_invalid(response):
    assert response.status_code == 401
    assert response.json() == {"detail": {
        "code": "invalid_session", "message": "Authentication session is invalid", "fields": [],
    }}
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers


def test_me_returns_only_supported_safe_fields_for_explicit_buyer(account_store, caplog):
    with Session(account_store.engine) as db, db.begin():
        user = db.get(User, account_store.ids["buyer"])
        user.full_name, user.phone_number = "Buyer Name", "+2348012345678"
        # Foundation intentionally permits vendor-role accounts with a BuyerProfile.
        assert user.role == "vendor"
        password_hash = user.password_hash
        profile = db.scalar(sa.select(BuyerProfile).where(BuyerProfile.user_id == user.id))
        completed, profile_id = profile.signup_completed_at, profile.id
    issued = issue(account_store)
    # GET bearer auth does not depend on browser Origin/CSRF headers or cookies.
    response = account_store.client.get(ME, headers={"Authorization": "Bearer " + issued.access, "Cookie": ""})
    assert response.status_code == 200
    assert response.json() == {
        "email": "buyer@example.test", "full_name": "Buyer Name", "phone_number": "+2348012345678",
        "signup_completed_at": completed.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    for secret in (password_hash, issued.access, issued.refresh, str(profile_id), str(issued.claims.session_id), str(issued.claims.user_id)):
        assert secret not in response.text and secret not in caplog.text
    assert foundation.counts(account_store)[2:] == [1, 1]


def test_me_does_not_select_password_hash_or_write_user(account_store):
    issued = issue(account_store)
    statements = []
    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    sa.event.listen(account_store.engine, "before_cursor_execute", observe)
    try:
        assert request(account_store, ME, issued.access).status_code == 200
    finally:
        sa.event.remove(account_store.engine, "before_cursor_execute", observe)
    assert not any("password_hash" in sql for sql in statements)
    assert not any(sql.startswith(("UPDATE ", "INSERT ", "DELETE ")) for sql in statements)


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic private-token", "Bearer private-token",
                                     " Bearer private-token", "Bearer  private-token", "Bearer\tprivate-token"])
def test_missing_or_malformed_authorization_fails_before_database(account_store, monkeypatch, caplog, path, header):
    engine = Mock(side_effect=AssertionError("Invalid header must not reach database"))
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", engine)
    headers = dict(HEADERS)
    if header is not None:
        headers["Authorization"] = header
    response = account_store.client.request("GET" if path == ME else "POST", path, headers=headers)
    assert_invalid(response)
    assert "private-token" not in response.text and "private-token" not in caplog.text
    assert not engine.called


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
def test_duplicate_authorization_rejected(account_store, path):
    issued = issue(account_store)
    response = account_store.client.request("GET" if path == ME else "POST", path, headers=[
        *HEADERS.items(), ("Authorization", "Bearer " + issued.access), ("Authorization", "Bearer " + issued.access),
    ])
    assert_invalid(response)


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
@pytest.mark.parametrize("change", ["expired", "signature", "issuer", "audience", "type", "future", "algorithm"])
def test_invalid_jwts_are_generic_before_database(account_store, monkeypatch, path, change):
    issued = issue(account_store)
    payload = jwt.decode(issued.access, options={"verify_signature": False})
    now = int(datetime.now(timezone.utc).timestamp())
    if change == "expired":
        payload.update(iat=now - 60, nbf=now - 60, exp=now - 1)
    elif change == "issuer":
        payload["iss"] = "wrong-issuer"
    elif change == "audience":
        payload["aud"] = "wrong-audience"
    elif change == "type":
        payload["type"] = "refresh"
    elif change == "future":
        payload.update(iat=now + 60, nbf=now + 60, exp=now + 120)
    key = bytes(range(64)) if change == "algorithm" else bytes(range(32))
    token = jwt.encode(payload, key, algorithm="HS384" if change == "algorithm" else "HS256")
    if change == "signature":
        token += "tampered"
    engine = Mock(side_effect=AssertionError("Invalid JWT must not reach database"))
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", engine)
    assert_invalid(request(account_store, path, token))
    assert not engine.called


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
@pytest.mark.parametrize("state", ["inactive", "no_profile", "reassigned_profile", "revoked", "expired_session", "future_session", "wrong_owner", "unknown"])
def test_live_session_and_buyer_eligibility_are_required(account_store, path, state):
    issued = issue(account_store)
    other = issue(account_store, "legacy@example.test")
    now = datetime.now(timezone.utc)
    with Session(account_store.engine) as db, db.begin():
        if state == "inactive":
            db.get(User, issued.claims.user_id).is_active = False
        elif state == "no_profile":
            # Role alone never establishes eligibility.
            db.get(User, issued.claims.user_id).role = "buyer"
            db.execute(sa.delete(BuyerProfile).where(BuyerProfile.user_id == issued.claims.user_id))
        elif state == "reassigned_profile":
            db.execute(sa.update(BuyerProfile).where(BuyerProfile.user_id == issued.claims.user_id).values(user_id=account_store.ids["missing"]))
        elif state == "revoked":
            db.get(AuthSession, issued.claims.session_id).revoked_at = now
        elif state == "expired_session":
            session = db.get(AuthSession, issued.claims.session_id)
            session.created_at, session.expires_at = now - timedelta(days=2), now - timedelta(days=1)
        elif state == "future_session":
            db.get(AuthSession, issued.claims.session_id).created_at = now + timedelta(hours=1)
    access = issued.access
    if state == "wrong_owner":
        access = create_access_token(issued.claims.user_id, other.claims.session_id, settings=account_store.settings)
    elif state == "unknown":
        access = create_access_token(uuid.uuid4(), uuid.uuid4(), settings=account_store.settings)
    assert_invalid(request(account_store, path, access))
    with Session(account_store.engine) as db:
        assert db.get(AuthSession, other.claims.session_id).revoked_at is None


def test_cookie_and_body_cannot_substitute_for_bearer_authentication(account_store):
    issued = issue(account_store)
    for path in (ME, LOGOUT_ALL):
        # The login cookie is present, but neither it nor body credentials authorize.
        response = request(account_store, path, json={"access_token": issued.access, "user_id": str(issued.claims.user_id)})
        assert_invalid(response)


def test_me_ignores_caller_supplied_identity(account_store):
    issued = issue(account_store)
    response = request(account_store, ME + "?user_id=" + str(account_store.ids["legacy"]), issued.access,
                       json={"user_id": str(account_store.ids["legacy"])})
    assert response.status_code == 200 and response.json()["email"] == "buyer@example.test"


def test_logout_all_revokes_all_own_sessions_and_current_but_not_other_user(account_store):
    first = issue(account_store)
    second = issue(account_store)
    other = issue(account_store, "legacy@example.test")
    response = request(account_store, LOGOUT_ALL + "?user_id=" + str(other.claims.user_id), first.access,
                       json={"user_id": str(other.claims.user_id), "session_id": str(other.claims.session_id)})
    assert response.status_code == 204 and response.content == b""
    cookie = response.headers["set-cookie"]
    assert all(flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=lax", f"Path={REFRESH_COOKIE_PATH}", "Max-Age=0"))
    assert "Domain=" not in cookie and response.headers["cache-control"] == "no-store"
    with Session(account_store.engine) as db:
        assert db.get(AuthSession, first.claims.session_id).revoked_at is not None
        assert db.get(AuthSession, second.claims.session_id).revoked_at is not None
        assert db.get(AuthSession, other.claims.session_id).revoked_at is None
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 3
    for issued in (first, second):
        assert_invalid(request(account_store, ME, issued.access))
        failed_refresh = account_store.client.post("/api/v1/auth/refresh", headers={**HEADERS, "Cookie": f"{REFRESH_COOKIE}={issued.refresh}"})
        assert failed_refresh.status_code == 401
    assert request(account_store, ME, other.access).status_code == 200
    # A repeat is authenticated again and therefore cannot use revoked credentials.
    assert_invalid(request(account_store, LOGOUT_ALL, first.access))


@pytest.mark.parametrize("headers", [{}, {"Origin": ORIGIN}, {"X-ScrapMart-CSRF": "1"},
                                     {"Origin": "https://evil.example", "X-ScrapMart-CSRF": "1"},
                                     {"Origin": ORIGIN, "X-ScrapMart-CSRF": "0"}])
def test_logout_all_browser_guards_precede_database(account_store, monkeypatch, headers):
    issued = issue(account_store)
    engine = Mock(side_effect=AssertionError("Rejected request must not access database"))
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", engine)
    response = account_store.client.post(LOGOUT_ALL, headers={**headers, "Authorization": "Bearer " + issued.access})
    assert response.status_code == 403 and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store" and not engine.called


@pytest.mark.parametrize("header,value", [("Origin", ORIGIN), ("X-ScrapMart-CSRF", "1")])
def test_logout_all_rejects_duplicate_browser_headers(account_store, header, value):
    issued = issue(account_store)
    response = account_store.client.post(LOGOUT_ALL, headers=[*HEADERS.items(), (header, value), ("Authorization", "Bearer " + issued.access)])
    assert response.status_code == 403 and "set-cookie" not in response.headers


@pytest.mark.parametrize("path,method", [(ME, "get_buyer_profile"), (LOGOUT_ALL, "revoke_all_buyer_sessions")])
def test_safe_service_failure(account_store, monkeypatch, caplog, path, method):
    issued = issue(account_store)
    monkeypatch.setattr(SessionService, method, Mock(side_effect=SessionPersistenceError()))
    response = request(account_store, path, issued.access)
    assert response.status_code == 503 and response.json()["detail"]["code"] == "session_unavailable"
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    assert issued.access not in response.text and issued.access not in caplog.text


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
def test_safe_database_connection_failure(account_store, monkeypatch, path):
    issued = issue(account_store)
    engine = Mock(side_effect=sa.exc.OperationalError("connect", None, Exception("private database password")))
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", engine)
    response = request(account_store, path, issued.access)
    assert response.status_code == 503 and "private" not in response.text and "set-cookie" not in response.headers


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
def test_bad_signing_configuration_fails_closed_before_database(account_store, monkeypatch, path):
    issued = issue(account_store)
    account_store.settings.jwt_signing_secret = SecretStr("invalid")
    engine = Mock(side_effect=AssertionError("Bad signing configuration must fail before database"))
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", engine)
    response = request(account_store, path, issued.access)
    assert response.status_code == 503 and not engine.called and "set-cookie" not in response.headers


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
def test_commit_failure_never_returns_profile_or_success(account_store, monkeypatch, path):
    issued = issue(account_store)
    class FailedSession(Session):
        pass
    @sa.event.listens_for(FailedSession, "before_commit")
    def fail(db):
        db.flush()
        raise sa.exc.OperationalError("commit", None, Exception("private database details"))
    monkeypatch.setattr("app.modules.auth.session_service.Session", FailedSession)
    response = request(account_store, path, issued.access)
    assert response.status_code == 503 and "private" not in response.text and "set-cookie" not in response.headers
    with Session(account_store.engine) as db:
        assert db.get(AuthSession, issued.claims.session_id).revoked_at is None


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
def test_unexpected_failure_is_safe(account_store, monkeypatch, caplog, path):
    issued = issue(account_store)
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", Mock(side_effect=RuntimeError("private database password")))
    response = request(account_store, path, issued.access)
    assert response.status_code == 500 and "private" not in response.text
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    assert "private database password" not in caplog.text and issued.access not in caplog.text


def test_logout_all_rechecks_current_session_after_waiting_for_user(account_store, monkeypatch):
    first = issue(account_store)
    later = issue(account_store)
    engine = sa.create_engine(account_store.engine.url, connect_args={"check_same_thread": False, "timeout": 10})
    @sa.event.listens_for(engine, "connect")
    def foreign_keys(db, _):
        db.execute("PRAGMA foreign_keys=ON")
    monkeypatch.setattr("app.api.v1.buyer_account.get_engine", lambda: engine)
    holding, waiting, release = threading.Event(), threading.Event(), threading.Event()
    class HeldSession(Session):
        pass
    monkeypatch.setattr("app.modules.auth.session_service.Session", HeldSession)
    @sa.event.listens_for(HeldSession, "before_commit")
    def hold(db):
        if threading.current_thread().name == "current-revoker":
            db.flush()
            holding.set()
            assert release.wait(10)
    def observe(connection, cursor, statement, parameters, context, many):
        if threading.current_thread().name != "current-revoker" and statement.startswith("UPDATE users"):
            waiting.set()
    def revoke_current():
        threading.current_thread().name = "current-revoker"
        return SessionService(engine).revoke_session(first.claims.user_id, first.claims.session_id)
    sa.event.listen(engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            revocation = pool.submit(revoke_current)
            try:
                assert holding.wait(10)
                logout = pool.submit(request, account_store, LOGOUT_ALL, first.access)
                assert waiting.wait(10)
            finally:
                release.set()
            assert revocation.result(timeout=30)
            assert_invalid(logout.result(timeout=30))
    finally:
        release.set()
        sa.event.remove(engine, "before_cursor_execute", observe)
        engine.dispose()
    with Session(account_store.engine) as db:
        assert db.get(AuthSession, first.claims.session_id).revoked_at is not None
        assert db.get(AuthSession, later.claims.session_id).revoked_at is None


def test_revocation_after_jwt_verification_is_still_enforced(account_store, monkeypatch):
    issued = issue(account_store)
    original = verify_access_token
    def verified_then_revoked(*args, **kwargs):
        claims = original(*args, **kwargs)
        SessionService(account_store.engine).revoke_session(claims.user_id, claims.session_id)
        return claims
    monkeypatch.setattr("app.api.v1.buyer_account.verify_access_token", verified_then_revoked)
    assert_invalid(request(account_store, ME, issued.access))


@pytest.mark.parametrize("path", [ME, LOGOUT_ALL])
def test_jwt_expiry_during_admission_is_rechecked(account_store, monkeypatch, path):
    issued = issue(account_store)
    # The existing verifier sees a currently valid JWT, but admission's clock
    # advances past its expiry. The database session itself remains unexpired.
    monkeypatch.setattr(SessionService, "_now", lambda self, db: issued.claims.expires_at + timedelta(seconds=1))
    assert_invalid(request(account_store, path, issued.access))
    with Session(account_store.engine) as db:
        assert db.get(AuthSession, issued.claims.session_id).revoked_at is None


def test_existing_cookie_logout_and_replay_disable_me(account_store):
    issued = issue(account_store)
    response = account_store.client.post("/api/v1/auth/logout", headers={**HEADERS, "Cookie": f"{REFRESH_COOKIE}={issued.refresh}"})
    assert response.status_code == 204
    assert_invalid(request(account_store, ME, issued.access))
    other = issue(account_store)
    for status in (200, 401):
        response = account_store.client.post("/api/v1/auth/refresh", headers={**HEADERS, "Cookie": f"{REFRESH_COOKIE}={other.refresh}"})
        assert response.status_code == status
    assert_invalid(request(account_store, ME, other.access))


def test_cors_and_openapi_use_bearer_security_without_secret_parameters(account_store):
    schema = account_store.client.get("/openapi.json").json()
    for path, method in ((ME, "GET"), (LOGOUT_ALL, "POST")):
        operation = schema["paths"][path][method.lower()]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert "requestBody" not in operation
        preflight = account_store.client.options(path, headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,x-scrapmart-csrf",
        })
        assert preflight.status_code == 200 and preflight.headers["cache-control"] == "no-store"
        assert "authorization" in preflight.headers["access-control-allow-headers"].lower()
    properties = schema["components"]["schemas"]["BuyerProfileResponse"]["properties"]
    assert set(properties) == {"email", "full_name", "phone_number", "signup_completed_at"}


def test_logout_all_does_not_expose_credentials_or_internal_identifiers(account_store, caplog):
    issued = issue(account_store)
    response = request(account_store, LOGOUT_ALL, issued.access)
    assert response.status_code == 204 and response.content == b""
    for secret in (issued.access, issued.refresh, str(issued.claims.session_id), str(issued.claims.user_id)):
        assert secret not in response.text and secret not in caplog.text


def test_logout_all_body_limit_and_method_restrictions(account_store):
    issued = issue(account_store)
    assert request(account_store, LOGOUT_ALL, issued.access, content="private" * 3000).status_code == 413
    assert account_store.client.post(ME, headers=HEADERS).status_code == 405
    assert account_store.client.get(LOGOUT_ALL, headers=HEADERS).status_code == 405
    assert request(account_store, ME, issued.access).status_code == 200
