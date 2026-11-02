"""Offline Vendor login, mutable admission state, and shared browser lifecycle."""
from unittest.mock import Mock
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from app.modules.auth.models import User
from app.modules.auth.email_identity_models import EmailIdentityReservation as Reservation, EmailIdentityPolicyState as Policy, POLICY_STATE_ID
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.security import verify_access_token, digest_refresh_token, verify_password
from app.modules.auth.http_security import REFRESH_COOKIE
from app.modules.auth.signup_rate_limit import RateLimitUnavailableError
from app.modules.vendors.models import Vendor
from tests.test_buyer_login import encoded_password, PASSWORD
from tests.test_buyer_login_http import http_store, HEADERS, URL as BUYER_LOGIN

URL = '/api/v1/auth/vendor/login'


@pytest.fixture
def store(http_store, monkeypatch):
    Vendor.__table__.create(http_store.engine)
    with Session(http_store.engine) as db, db.begin():
        for name in ('buyer', 'inactive', 'missing'):
            db.add(Vendor(user_id=http_store.ids[name], business_name='Shop', verification_status='pending'))
        # Login must work for buyer-role identities without any BuyerProfile.
        db.get(User, http_store.ids['missing']).role = 'buyer'
    monkeypatch.setattr('app.api.v1.vendor_login.get_engine', lambda: http_store.engine)
    monkeypatch.setattr('app.api.v1.buyer_sessions.get_engine', lambda: http_store.engine)
    monkeypatch.setattr('app.api.v1.buyer_account.get_engine', lambda: http_store.engine)
    return http_store


def login(store, **changes):
    return store.client.post(URL, json={'email':'buyer@example.test','password':PASSWORD, **changes}, headers=HEADERS)


def assert_no_sessions(store):
    with Session(store.engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(AuthSession)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 0


@pytest.mark.parametrize('status', ['pending','approved','rejected','suspended'])
def test_status_admission_issues_only_identity_and_shared_cookie(store, status, caplog):
    with Session(store.engine) as db, db.begin():
        vendor = db.scalar(sa.select(Vendor).where(Vendor.user_id == store.ids['missing']))
        vendor.verification_status = status
    response = login(store, email=' MISSING@Example.Test ')
    assert response.status_code == 200
    assert set(response.json()) == {'access_token','token_type','expires_in'}
    access = response.json()['access_token']
    claims = verify_access_token(access, settings=store.settings)
    assert claims.user_id == store.ids['missing']
    assert not hasattr(claims, 'role') and not hasattr(claims, 'verification_status')
    raw = response.cookies[REFRESH_COOKIE]
    cookie = response.headers['set-cookie'].lower()
    for flag in ('secure','httponly','samesite=lax','path=/api/v1/auth'):
        assert flag in cookie
    assert 'domain=' not in cookie and raw not in response.text
    assert response.headers['cache-control'] == 'no-store'
    with Session(store.engine) as db:
        token = db.scalar(sa.select(RefreshToken))
        assert token.token_digest == digest_refresh_token(raw)
        assert db.get(AuthSession, claims.session_id).user_id == claims.user_id
    assert access not in caplog.text and raw not in caplog.text and PASSWORD not in caplog.text


@pytest.mark.parametrize('email,password', [('unknown@example.test',PASSWORD),('buyer@example.test','wrong password'),
    ('inactive@example.test',PASSWORD),('legacy@example.test',PASSWORD)])
def test_invalid_credentials_are_generic(store, email, password):
    # legacy has BuyerProfile and vendor role, but no Vendor record.
    response = login(store, email=email, password=password)
    assert response.status_code == 401
    assert response.json()['detail'] == {'code':'invalid_credentials','message':'Invalid email or password','fields':[]}
    assert response.headers['www-authenticate'] == 'Bearer'
    assert 'set-cookie' not in response.headers
    assert_no_sessions(store)


@pytest.mark.parametrize('headers', [{}, {'Origin':HEADERS['Origin']}, {**HEADERS,'Origin':'https://evil.test'},
    {**HEADERS,'X-ScrapMart-CSRF':'0'}])
def test_browser_guards_precede_services(store, monkeypatch, headers):
    service = Mock(side_effect=AssertionError('must not authenticate'))
    monkeypatch.setattr('app.api.v1.vendor_login.VendorLoginService', service)
    assert store.client.post(URL, json={}, headers=headers).status_code == 403
    service.assert_not_called()


def test_validation_body_and_signing_configuration(store):
    assert store.client.post(URL, content='x'*16385, headers=HEADERS).status_code == 413
    assert login(store, role='vendor').status_code == 422
    store.settings.jwt_signing_secret = None
    assert login(store).status_code == 503
    assert_no_sessions(store)


@pytest.mark.parametrize('kind,limit', [('email',10),('ip',30)])
def test_buyer_vendor_share_rate_limit_budgets(store, kind, limit):
    # Invalid credentials also consume counters; IP test avoids email counter.
    for i in range(limit):
        path = BUYER_LOGIN if i % 2 else URL
        email = 'unknown@example.test' if kind == 'email' else f'unknown{i}@example.test'
        response = store.client.post(path, json={'email':email,'password':PASSWORD}, headers=HEADERS)
        assert response.status_code == 401
    response = login(store, email='unknown@example.test' if kind == 'email' else 'another@example.test')
    assert response.status_code == 429 and 'retry-after' in response.headers
    assert_no_sessions(store)


def test_redis_failure_is_closed(store, monkeypatch):
    monkeypatch.setattr('app.api.v1.buyer_login.get_login_rate_limiter', lambda: Mock(check=Mock(side_effect=RateLimitUnavailableError())))
    assert login(store).status_code == 503
    assert_no_sessions(store)


@pytest.mark.parametrize('change', ['password','inactive','vendor_deleted','email','reservation','registry'])
def test_admission_rechecks_after_verification(store, monkeypatch, change):
    def verify(*args, **kwargs):
        # A separate transaction can write while Argon2 runs: no login locks.
        result = verify_password(*args, **kwargs)
        with Session(store.engine) as db, db.begin():
            user = db.get(User, store.ids['buyer'])
            if change == 'password': user.password_hash = 'changed'
            if change == 'inactive': user.is_active = False
            if change == 'vendor_deleted': db.execute(sa.delete(Vendor).where(Vendor.user_id == user.id))
            if change == 'email': user.email = 'changed@example.test'
            if change == 'reservation': db.execute(sa.update(Reservation).where(Reservation.user_id == user.id).values(state='blocked',user_id=None))
            if change == 'registry': db.get(Policy, POLICY_STATE_ID).status = 'building'
        return result
    monkeypatch.setattr('app.modules.auth.vendor_login_service.verify_password', verify)
    response = login(store)
    assert response.status_code == (503 if change == 'registry' else 401)
    assert_no_sessions(store)


@pytest.mark.parametrize('status', ['approved','rejected','suspended'])
def test_changed_recognized_status_is_rechecked_without_granting_approval(store, monkeypatch, status):
    def verify(*args, **kwargs):
        result = verify_password(*args, **kwargs)
        with Session(store.engine) as db, db.begin():
            db.execute(sa.update(Vendor).where(Vendor.user_id == store.ids['buyer']).values(verification_status=status))
        return result
    monkeypatch.setattr('app.modules.auth.vendor_login_service.verify_password', verify)
    assert login(store).status_code == 200
    with Session(store.engine) as db:
        assert db.scalar(sa.select(Vendor.verification_status).where(Vendor.user_id == store.ids['buyer'])) == status


@pytest.mark.parametrize('stage', ['lookup','insert','commit'])
def test_database_failure_rolls_back_and_redacts(store, stage, caplog):
    def fail_sql(connection, cursor, statement, parameters, context, many):
        if (stage == 'lookup' and statement.startswith('SELECT')) or (stage == 'insert' and statement.startswith('INSERT INTO refresh_tokens')):
            raise sa.exc.SQLAlchemyError('private database detail')
    def fail_commit(connection):
        # Raise only on the admission commit, after session inserts.
        if inserted:
            raise sa.exc.SQLAlchemyError('private commit detail')
    inserted = []
    def observe(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO refresh_tokens'): inserted.append(True)
    if stage == 'commit':
        sa.event.listen(store.engine, 'before_cursor_execute', observe)
        sa.event.listen(store.engine, 'commit', fail_commit)
    else:
        sa.event.listen(store.engine, 'before_cursor_execute', fail_sql)
    try:
        response = login(store)
    finally:
        if stage == 'commit':
            sa.event.remove(store.engine, 'before_cursor_execute', observe)
            sa.event.remove(store.engine, 'commit', fail_commit)
        else: sa.event.remove(store.engine, 'before_cursor_execute', fail_sql)
    assert response.status_code == 503 and 'set-cookie' not in response.headers
    assert 'private' not in response.text and 'private' not in caplog.text
    assert_no_sessions(store)


def test_shared_refresh_replay_logout_and_buyer_compatibility(store):
    response = login(store)
    assert response.status_code == 200
    claims = verify_access_token(response.json()['access_token'], settings=store.settings)
    old = response.cookies[REFRESH_COOKIE]
    assert store.client.get('/api/v1/auth/me', headers={'Authorization':'Bearer '+response.json()['access_token']}).status_code == 200
    rotated = store.client.post('/api/v1/auth/refresh', headers={**HEADERS,'Cookie':f'{REFRESH_COOKIE}={old}'})
    assert rotated.status_code == 200
    replay = store.client.post('/api/v1/auth/refresh', headers={**HEADERS,'Cookie':f'{REFRESH_COOKIE}={old}'})
    assert replay.status_code == 401
    with Session(store.engine) as db:
        assert db.get(AuthSession, claims.session_id).revoked_at is not None
    assert store.client.post(BUYER_LOGIN, json={'email':'buyer@example.test','password':PASSWORD},headers=HEADERS).status_code == 200
    assert store.client.post('/api/v1/auth/logout', headers=HEADERS).status_code == 204
