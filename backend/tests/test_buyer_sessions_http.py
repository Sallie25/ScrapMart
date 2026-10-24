"""Offline HTTP lifecycle tests; SQLite does not establish PostgreSQL isolation."""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.modules.auth.http_security import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.modules.auth.models import User
from app.modules.auth.security import digest_refresh_token, generate_refresh_token, verify_access_token
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError, SessionService
from tests import test_buyer_login as foundation
from tests.test_buyer_login import encoded_password
from tests.test_buyer_login_http import HEADERS, ORIGIN, URL as LOGIN, http_store

REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


@pytest.fixture
def sessions_store(http_store, monkeypatch):
    monkeypatch.setattr("app.api.v1.buyer_sessions.get_engine", lambda: http_store.engine)
    return http_store


def issue(store):
    response = store.client.post(LOGIN, headers=HEADERS, json={
        "email": "buyer@example.test", "password": foundation.PASSWORD,
    })
    assert response.status_code == 200
    claims = verify_access_token(response.json()["access_token"], settings=store.settings)
    return response.cookies.get(REFRESH_COOKIE), claims


def send(store, path, token):
    return store.client.post(path, headers={**HEADERS, "Cookie": f"{REFRESH_COOKIE}={token}" if token is not None else ""})


def assert_cookie(response, *, cleared=False):
    value = response.headers["set-cookie"]
    assert all(flag in value for flag in ("Secure", "HttpOnly", "SameSite=lax", f"Path={REFRESH_COOKIE_PATH}", "expires="))
    assert "Domain=" not in value
    if cleared:
        assert "Max-Age=0" in value
    else:
        assert "Max-Age=0" not in value
        assert response.cookies.get(REFRESH_COOKIE)
    assert response.headers["cache-control"] == "no-store"


def test_refresh_rotates_and_retains_absolute_expiry(sessions_store, caplog):
    old, old_claims = issue(sessions_store)
    with Session(sessions_store.engine) as db:
        expiry = db.get(AuthSession, old_claims.session_id).expires_at
    response = send(sessions_store, REFRESH, old)
    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}
    assert response.json()["token_type"] == "bearer" and response.json()["expires_in"] == 900
    jwt = response.json()["access_token"]
    claims = verify_access_token(jwt, settings=sessions_store.settings)
    assert claims.user_id == old_claims.user_id and claims.session_id == old_claims.session_id
    assert claims.token_id != old_claims.token_id
    replacement = response.cookies.get(REFRESH_COOKIE)
    assert replacement != old and old not in response.text and replacement not in response.text
    assert_cookie(response)
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).expires_at == expiry
        rows = db.scalars(sa.select(RefreshToken)).all()
        assert len(rows) == 2 and {row.expires_at for row in rows} == {expiry}
        consumed = next(row for row in rows if row.token_digest == digest_refresh_token(old))
        rotated = next(row for row in rows if row.token_digest == digest_refresh_token(replacement))
        assert consumed.consumed_at is not None and rotated.consumed_at is None
        assert rotated.session_id == claims.session_id
    for secret in (old, replacement, jwt, foundation.PASSWORD):
        assert secret not in caplog.text
    assert SessionService(sessions_store.engine).validate_access_session(claims).session_id == claims.session_id


@pytest.mark.parametrize("token", [None, "", "malformed", "A" * 42, "A" * 44, "*" * 43])
def test_missing_or_malformed_refresh_fails_before_database(sessions_store, monkeypatch, token):
    engine = Mock(side_effect=AssertionError("Invalid credential must not reach database"))
    monkeypatch.setattr("app.api.v1.buyer_sessions.get_engine", engine)
    response = send(sessions_store, REFRESH, token)
    assert response.status_code == 401 and not engine.called
    assert response.json() == {"detail": {"code": "invalid_session", "message": "Authentication session is invalid", "fields": []}}
    assert response.headers["www-authenticate"] == "Bearer"
    assert_cookie(response, cleared=True)


@pytest.mark.parametrize("state", ["unknown", "expired_session", "expired_token", "future_token", "revoked", "inactive"])
def test_invalid_refresh_is_generic_and_does_not_rotate(sessions_store, state, caplog):
    token, claims = issue(sessions_store)
    now = datetime.now(timezone.utc)
    with Session(sessions_store.engine) as db, db.begin():
        session = db.get(AuthSession, claims.session_id)
        row = db.scalar(sa.select(RefreshToken))
        if state == "unknown":
            token = generate_refresh_token()
        elif state == "revoked":
            session.revoked_at = now
        elif state == "inactive":
            db.get(User, claims.user_id).is_active = False
        elif state == "expired_session":
            session.created_at, session.expires_at = now - timedelta(days=2), now - timedelta(days=1)
            row.created_at, row.expires_at = session.created_at, session.expires_at
        elif state == "expired_token":
            row.created_at, row.expires_at = now - timedelta(days=2), now - timedelta(days=1)
        else:
            row.created_at = now + timedelta(hours=1)
    response = send(sessions_store, REFRESH, token)
    assert response.status_code == 401
    assert response.json()["detail"]["message"] == "Authentication session is invalid"
    assert token not in response.text and token not in caplog.text
    assert_cookie(response, cleared=True)
    assert foundation.counts(sessions_store)[2:] == [1, 1]


def test_replay_revocation_commits_and_invalidates_replacement(sessions_store):
    old, claims = issue(sessions_store)
    first = send(sessions_store, REFRESH, old)
    replacement = first.cookies.get(REFRESH_COOKIE)
    assert first.status_code == 200
    replay = send(sessions_store, REFRESH, old)
    assert replay.status_code == 401
    assert_cookie(replay, cleared=True)
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is not None
    assert send(sessions_store, REFRESH, replacement).status_code == 401
    with pytest.raises(SessionAuthenticationError):
        SessionService(sessions_store.engine).validate_access_session(claims)
    assert foundation.counts(sessions_store)[2:] == [1, 2]


def test_concurrent_refresh_has_one_rotation_and_committed_replay_revocation(sessions_store, monkeypatch):
    token, claims = issue(sessions_store)
    # Separate connections are essential: the ordinary HTTP fixture's StaticPool
    # is for sequential tests. This exercises SQLite's writer serialization,
    # not PostgreSQL row locks or its three isolation levels.
    engine = sa.create_engine(sessions_store.engine.url, connect_args={"check_same_thread": False, "timeout": 10})
    @sa.event.listens_for(engine, "connect")
    def foreign_keys(db, _):
        db.execute("PRAGMA foreign_keys=ON")
    monkeypatch.setattr("app.api.v1.buyer_sessions.get_engine", lambda: engine)
    barrier = threading.Barrier(2)
    def synchronize(connection, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE users"):
            barrier.wait(timeout=10)
    sa.event.listen(engine, "before_cursor_execute", synchronize)
    def refresh():
        with TestClient(sessions_store.client.app, base_url="https://api.example.test") as client:
            return client.post(REFRESH, headers={**HEADERS, "Cookie": f"{REFRESH_COOKIE}={token}"})
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(refresh) for _ in range(2)]
            responses = [future.result(timeout=30) for future in futures]
    finally:
        sa.event.remove(engine, "before_cursor_execute", synchronize)
        engine.dispose()
    assert sorted(response.status_code for response in responses) == [200, 401]
    assert foundation.counts(sessions_store)[2:] == [1, 2]
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is not None
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken).where(RefreshToken.consumed_at.is_not(None))) == 1
    winner = next(response for response in responses if response.status_code == 200)
    assert send(sessions_store, REFRESH, winner.cookies.get(REFRESH_COOKIE)).status_code == 401


def test_logout_revokes_current_session_and_retains_history(sessions_store):
    token, claims = issue(sessions_store)
    other, other_claims = issue(sessions_store)
    response = send(sessions_store, LOGOUT, token)
    assert response.status_code == 204 and response.content == b""
    assert_cookie(response, cleared=True)
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is not None
        assert db.get(AuthSession, other_claims.session_id).revoked_at is None
    with pytest.raises(SessionAuthenticationError):
        SessionService(sessions_store.engine).validate_access_session(claims)
    assert send(sessions_store, REFRESH, token).status_code == 401
    assert send(sessions_store, REFRESH, other).status_code == 200
    assert send(sessions_store, LOGOUT, token).status_code == 204
    assert foundation.counts(sessions_store)[2:] == [2, 3]


@pytest.mark.parametrize("token", [None, "malformed", "", "*" * 43])
def test_logout_missing_or_malformed_is_idempotent_without_database(sessions_store, monkeypatch, token):
    engine = Mock(side_effect=AssertionError("No database access required"))
    monkeypatch.setattr("app.api.v1.buyer_sessions.get_engine", engine)
    response = send(sessions_store, LOGOUT, token)
    assert response.status_code == 204 and response.content == b"" and not engine.called
    assert_cookie(response, cleared=True)


@pytest.mark.parametrize("state", ["unknown", "expired", "inactive", "consumed", "revoked"])
def test_logout_known_and_unknown_states_share_response(sessions_store, state):
    token, claims = issue(sessions_store)
    if state == "consumed":
        assert send(sessions_store, REFRESH, token).status_code == 200
    else:
        now = datetime.now(timezone.utc)
        with Session(sessions_store.engine) as db, db.begin():
            session = db.get(AuthSession, claims.session_id)
            if state == "unknown":
                token = generate_refresh_token()
            elif state == "expired":
                session.created_at, session.expires_at = now - timedelta(days=2), now - timedelta(days=1)
            elif state == "inactive":
                db.get(User, claims.user_id).is_active = False
            else:
                session.revoked_at = now
    response = send(sessions_store, LOGOUT, token)
    assert response.status_code == 204 and response.content == b""
    assert_cookie(response, cleared=True)
    if state != "unknown":
        with Session(sessions_store.engine) as db:
            assert db.get(AuthSession, claims.session_id).revoked_at is not None


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
@pytest.mark.parametrize("headers", [{}, {"Origin": ORIGIN}, {"X-ScrapMart-CSRF": "1"},
                                     {"Origin": "https://evil.example", "X-ScrapMart-CSRF": "1"},
                                     {"Origin": ORIGIN, "X-ScrapMart-CSRF": "0"}])
def test_origin_csrf_rejection_does_not_clear_cookie_or_mutate(sessions_store, path, headers):
    token, claims = issue(sessions_store)
    response = sessions_store.client.post(path, headers={**headers, "Cookie": f"{REFRESH_COOKIE}={token}"})
    assert response.status_code == 403 and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is None
        assert db.scalar(sa.select(RefreshToken)).consumed_at is None


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
def test_duplicate_cookie_rejected_without_selecting_a_session(sessions_store, path):
    token, claims = issue(sessions_store)
    response = sessions_store.client.post(path, headers={**HEADERS, "Cookie": f"{REFRESH_COOKIE}={token}; {REFRESH_COOKIE}={generate_refresh_token()}"})
    assert response.status_code == (401 if path == REFRESH else 204)
    assert_cookie(response, cleared=True)
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is None


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
def test_tokens_are_not_read_from_body_or_authorization(sessions_store, path):
    token, claims = issue(sessions_store)
    response = sessions_store.client.post(path, json={"refresh_token": token}, headers={
        **HEADERS, "Cookie": "", "Authorization": f"Bearer {token}",
    })
    assert response.status_code == (401 if path == REFRESH else 204)
    assert token not in response.text
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is None
        assert db.scalar(sa.select(RefreshToken)).consumed_at is None


@pytest.mark.parametrize("path,method", [(REFRESH, "rotate_refresh_token"), (LOGOUT, "revoke_refresh_session")])
def test_infrastructure_failure_is_safe_and_does_not_clear_cookie(sessions_store, monkeypatch, caplog, path, method):
    token, _ = issue(sessions_store)
    monkeypatch.setattr(SessionService, method, Mock(side_effect=SessionPersistenceError()))
    response = send(sessions_store, path, token)
    assert response.status_code == 503 and response.json()["detail"]["code"] == "session_unavailable"
    assert "set-cookie" not in response.headers
    assert token not in response.text and token not in caplog.text
    assert response.headers["cache-control"] == "no-store"


def test_refresh_bad_signing_configuration_does_not_consume_token(sessions_store):
    token, _ = issue(sessions_store)
    sessions_store.settings.jwt_signing_secret = SecretStr("invalid")
    response = send(sessions_store, REFRESH, token)
    assert response.status_code == 503 and "set-cookie" not in response.headers
    with Session(sessions_store.engine) as db:
        assert db.scalar(sa.select(RefreshToken)).consumed_at is None
    assert send(sessions_store, LOGOUT, token).status_code == 204


def test_refresh_insert_failure_rolls_back_consumption(sessions_store):
    token, _ = issue(sessions_store)
    def fail(mapper, connection, target):
        raise sa.exc.OperationalError("insert", None, Exception("private token details"))
    sa.event.listen(RefreshToken, "before_insert", fail)
    try:
        response = send(sessions_store, REFRESH, token)
    finally:
        sa.event.remove(RefreshToken, "before_insert", fail)
    assert response.status_code == 503 and "private" not in response.text
    assert "set-cookie" not in response.headers
    with Session(sessions_store.engine) as db:
        assert db.scalar(sa.select(RefreshToken)).consumed_at is None
    assert foundation.counts(sessions_store)[2:] == [1, 1]


def test_logout_commit_failure_is_not_reported_as_success(sessions_store, monkeypatch):
    token, claims = issue(sessions_store)
    class FailedSession(Session):
        pass
    @sa.event.listens_for(FailedSession, "before_commit")
    def fail(db):
        db.flush()
        raise sa.exc.OperationalError("commit", None, Exception("private database details"))
    monkeypatch.setattr("app.modules.auth.session_service.Session", FailedSession)
    response = send(sessions_store, LOGOUT, token)
    assert response.status_code == 503 and "private" not in response.text
    assert "set-cookie" not in response.headers
    with Session(sessions_store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is None


@pytest.mark.parametrize("state", ["40001", "40P01", "08006"])
def test_logout_uses_existing_bounded_transaction_retry(sessions_store, monkeypatch, state):
    token, claims = issue(sessions_store)
    attempts = []
    class RetriedSession(Session):
        pass
    class Conflict(Exception):
        sqlstate = state
    @sa.event.listens_for(RetriedSession, "before_commit")
    def fail_once(db):
        db.flush()
        attempts.append(db)
        if len(attempts) == 1:
            raise sa.exc.DBAPIError("commit", None, Conflict())
    monkeypatch.setattr("app.modules.auth.session_service.Session", RetriedSession)
    response = send(sessions_store, LOGOUT, token)
    retryable = state in {"40001", "40P01"}
    assert response.status_code == (204 if retryable else 503)
    assert len(attempts) == (2 if retryable else 1)
    if retryable:
        assert attempts[0] is not attempts[1]
    with Session(sessions_store.engine) as db:
        assert (db.get(AuthSession, claims.session_id).revoked_at is not None) == retryable


def test_logout_preserves_user_session_token_lock_order(sessions_store):
    token, _ = issue(sessions_store)
    statements = []
    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    sa.event.listen(sessions_store.engine, "before_cursor_execute", observe)
    try:
        assert send(sessions_store, LOGOUT, token).status_code == 204
    finally:
        sa.event.remove(sessions_store.engine, "before_cursor_execute", observe)
    user = next(i for i, sql in enumerate(statements) if sql.startswith("UPDATE users"))
    session = next(i for i, sql in enumerate(statements) if i > user and sql.startswith("SELECT auth_sessions"))
    refresh = next(i for i, sql in enumerate(statements) if i > session and sql.startswith("SELECT refresh_tokens"))
    revocation = next(i for i, sql in enumerate(statements) if sql.startswith("UPDATE auth_sessions"))
    assert user < session < refresh < revocation


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
@pytest.mark.parametrize("duplicate,value", [("Origin", ORIGIN), ("X-ScrapMart-CSRF", "1")])
def test_duplicate_browser_security_headers_rejected(sessions_store, path, duplicate, value):
    token, _ = issue(sessions_store)
    response = sessions_store.client.post(path, headers=[*HEADERS.items(), (duplicate, value), ("Cookie", f"{REFRESH_COOKIE}={token}")])
    assert response.status_code == 403 and "set-cookie" not in response.headers


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_lifecycle_is_post_only(sessions_store, path, method):
    response = getattr(sessions_store.client, method)(path, headers=HEADERS)
    assert response.status_code == 405 and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
def test_unexpected_failure_is_safe(sessions_store, monkeypatch, caplog, path):
    token, _ = issue(sessions_store)
    monkeypatch.setattr("app.api.v1.buyer_sessions.get_engine", Mock(side_effect=RuntimeError("private database password")))
    response = send(sessions_store, path, token)
    assert response.status_code == 500 and "private" not in response.text
    assert "private database password" not in caplog.text and token not in caplog.text
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
def test_no_sensitive_logout_logging_and_no_redis_dependency(sessions_store, path, caplog):
    token, _ = issue(sessions_store)
    sessions_store.redis.eval = Mock(side_effect=AssertionError("Session lifecycle must not reuse login budgets"))
    response = send(sessions_store, path, token)
    assert response.status_code == (200 if path == REFRESH else 204)
    assert not sessions_store.redis.eval.called
    assert token not in caplog.text and token not in response.text


def test_openapi_cookie_only_contract_and_cors(sessions_store):
    schema = sessions_store.client.get("/openapi.json").json()
    for path in (REFRESH, LOGOUT):
        operation = schema["paths"][path]["post"]
        assert "requestBody" not in operation
        assert {parameter["name"] for parameter in operation["parameters"]} == {"Origin", "X-ScrapMart-CSRF"}
        response = sessions_store.client.options(path, headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-scrapmart-csrf"})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [REFRESH, LOGOUT])
def test_body_limits_apply_without_echoing_token(sessions_store, path):
    response = sessions_store.client.post(path, content="private" * 3000, headers=HEADERS)
    assert response.status_code == 413 and "private" not in response.text
    assert "set-cookie" not in response.headers
