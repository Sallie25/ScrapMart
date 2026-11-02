"""Offline Vendor registration/enrollment boundaries and persistence guarantees."""
import base64
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.orm import Session

from tests.test_buyer_signup import signup_store, HEADERS, PASSWORD, seed_legacy, payload
from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.email_identity_models import EmailIdentityReservation as Reservation
from app.modules.auth.registration_service import RegistrationUnavailableError
from app.modules.auth.vendor_service import VendorRegistrationService, VendorEnrollmentService
from app.modules.auth.vendor_schemas import VendorSignupRequest, VendorEnrollmentRequest
from app.modules.auth.security import hash_password, verify_password, create_access_token, verify_access_token
from app.modules.auth.signup_rate_limit import RateLimitUnavailableError
from app.modules.buyers.models import BuyerProfile
from app.modules.vendors.models import Vendor

SIGNUP = '/api/v1/auth/vendor/signup'
ENROLL = '/api/v1/auth/vendor/enroll'


@pytest.fixture
def store(signup_store, monkeypatch):
    monkeypatch.setattr('app.api.v1.vendor_registration.get_engine', lambda: signup_store.engine)
    signup_store.settings.jwt_signing_secret = SecretStr(base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip('='))
    monkeypatch.setattr('app.api.v1.vendor_registration.enforce_login_limit', lambda *args: None)
    return signup_store


def body(**changes):
    return {**payload(business_name='Example shop'), **changes}


def signup(store, **changes):
    return store.client.post(SIGNUP, json=body(**changes), headers=HEADERS)


def count(db, model):
    return db.scalar(sa.select(sa.func.count()).select_from(model))


def test_signup_success_duplicate_and_no_buyer_or_session(store):
    first = signup(store, email=' BUYER@Example.Test ')
    assert first.status_code == 202 and 'set-cookie' not in first.headers
    assert first.headers['cache-control'] == 'no-store'
    assert signup(store).json() == first.json()
    with Session(store.engine) as db:
        user = db.scalar(sa.select(User))
        assert user.email == 'buyer@example.test' and user.role == 'vendor'
        assert verify_password(PASSWORD, user.password_hash)
        vendor = db.scalar(sa.select(Vendor))
        assert vendor.user_id == user.id and vendor.verification_status == 'pending'
        assert vendor.business_name == 'Example shop'
        assert [count(db, m) for m in (User, Vendor, BuyerProfile, AuthSession, RefreshToken)] == [1, 1, 0, 0, 0]


def test_reserved_identity_does_not_create_or_link(store):
    with Session(store.engine) as db, db.begin():
        db.add(Reservation(lookup_key='buyer@example.test', state='blocked', user_id=None))
    assert signup(store).status_code == 202
    with Session(store.engine) as db:
        assert count(db, User) == count(db, Vendor) == 0


@pytest.mark.parametrize('change', [dict(business_name=' '), dict(business_name='x'*201),
    dict(password='short'), dict(email='非@example.test'), dict(role='admin'),
    dict(verification_status='approved'), dict(user_id='anything'), dict(full_name='')])
def test_invalid_inputs_are_sanitized(store, change):
    response = signup(store, **change)
    assert response.status_code == 422
    assert PASSWORD not in response.text and 'input' not in response.json()['detail']


def test_guards_limits_body_and_fail_closed(store, monkeypatch):
    assert store.client.post(SIGNUP, json=body()).status_code == 403
    assert store.client.post(SIGNUP, content='x'*16385, headers=HEADERS).status_code == 413
    monkeypatch.setattr('app.api.v1.buyer_signup.get_signup_rate_limiter', lambda: Mock(check=Mock(side_effect=RateLimitUnavailableError())))
    assert signup(store).status_code == 503


def test_signup_rate_limit(store):
    for _ in range(5):
        assert signup(store).status_code == 202
    response = signup(store)
    assert response.status_code == 429 and 'retry-after' in response.headers


def test_registration_rollback(store, monkeypatch):
    def broken(self, db, user_id, signup):
        raise sa.exc.SQLAlchemyError('private database detail')
    monkeypatch.setattr(VendorRegistrationService, '_add_profile', broken)
    response = signup(store)
    assert response.status_code == 503 and 'private database' not in response.text
    with Session(store.engine) as db:
        assert [count(db, m) for m in (User, Vendor, Reservation)] == [0, 0, 0]


def identity(store):
    user_id = seed_legacy(store, email='buyer@example.test', password_hash=hash_password(PASSWORD), full_name='Buyer', role='buyer')
    now = datetime.now(timezone.utc)
    with Session(store.engine) as db, db.begin():
        db.add(BuyerProfile(user_id=user_id, created_at=now, signup_completed_at=now))
    from app.modules.auth.session_service import SessionService
    credentials = SessionService(store.engine, settings=store.settings).create_session(user_id)
    token = create_access_token(user_id, credentials.session_id, settings=store.settings)
    return user_id, token, verify_access_token(token, settings=store.settings)


def enroll(store, token, **changes):
    return store.client.post(ENROLL, json={'business_name':'New shop', 'current_password':PASSWORD, **changes},
                             headers={**HEADERS, 'Authorization':'Bearer '+token})


def test_enrollment_preserves_identity_and_existing_status(store):
    user_id, token, _ = identity(store)
    with Session(store.engine) as db:
        original = db.get(User, user_id).password_hash
    assert enroll(store, token).status_code == 204
    with Session(store.engine) as db, db.begin():
        vendor = db.scalar(sa.select(Vendor))
        assert vendor.verification_status == 'pending'
        vendor.verification_status = 'suspended'
    assert enroll(store, token, business_name='Replacement').status_code == 204
    with Session(store.engine) as db:
        user = db.get(User, user_id)
        vendor = db.scalar(sa.select(Vendor))
        assert user.password_hash == original and user.role == 'buyer'
        assert count(db, BuyerProfile) == 1 and count(db, Vendor) == 1
        assert vendor.verification_status == 'suspended' and vendor.business_name == 'New shop'


@pytest.mark.parametrize('state', ['wrong_password','missing','expired','revoked','inactive','no_buyer'])
def test_enrollment_rejects_invalid_authentication(store, state):
    user_id, token, claims = identity(store)
    with Session(store.engine) as db, db.begin():
        session = db.get(AuthSession, claims.session_id)
        if state == 'revoked': session.revoked_at = datetime.now(timezone.utc)
        if state == 'expired':
            session.created_at = datetime.now(timezone.utc)-timedelta(days=2)
            session.expires_at = datetime.now(timezone.utc)-timedelta(days=1)
        if state == 'inactive': db.get(User,user_id).is_active = False
        if state == 'no_buyer': db.execute(sa.delete(BuyerProfile))
    response = enroll(store, '' if state == 'missing' else token,
                      current_password='incorrect password' if state == 'wrong_password' else PASSWORD)
    assert response.status_code == 401
    with Session(store.engine) as db:
        assert count(db, Vendor) == 0


def test_enrollment_guards_and_redaction(store):
    _, token, _ = identity(store)
    assert store.client.post(ENROLL, json={}, headers={'Authorization':'Bearer '+token}).status_code == 403
    assert enroll(store, token, role='vendor').status_code == 422
    assert store.client.post(ENROLL, content='x'*16385, headers=HEADERS).status_code == 413


def test_concurrent_operations(store, monkeypatch):
    # Separate connections, not the fixture's shared StaticPool connection.
    engine = sa.create_engine(store.engine.url, connect_args={'check_same_thread':False, 'timeout':10})
    request = VendorSignupRequest.model_validate(body())
    barrier = threading.Barrier(2)
    original_hash = hash_password
    def concurrent_hash(password):
        result = original_hash(password)
        barrier.wait(timeout=10)
        return result
    monkeypatch.setattr('app.modules.auth.registration_service.hash_password', concurrent_hash)
    def register(_):
        try:
            VendorRegistrationService(engine).register(request)
            return 'ok'
        except RegistrationUnavailableError:
            return 'retry'
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(register, range(2)))
    assert 'ok' in outcomes
    with Session(engine) as db:
        assert count(db, User) == count(db, Vendor) == 1
    # A separate Buyer identity exercises serialized, idempotent enrollment.
    with Session(store.engine) as db, db.begin():
        db.execute(sa.delete(Vendor)); db.execute(sa.delete(Reservation)); db.execute(sa.delete(User))
    _, _, claims = identity(store)
    value = VendorEnrollmentRequest(business_name='Shop', current_password=PASSWORD)
    barrier = threading.Barrier(2)
    def concurrent_verify(*args, **kwargs):
        result = verify_password(*args, **kwargs)
        barrier.wait(timeout=10)
        return result
    monkeypatch.setattr('app.modules.auth.vendor_service.verify_password', concurrent_verify)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: VendorEnrollmentService(engine).enroll(claims, value), range(2)))
    with Session(engine) as db:
        assert count(db, Vendor) == 1 and count(db, BuyerProfile) == 1
    engine.dispose()


@pytest.mark.parametrize('change', ['password', 'revocation', 'jwt_expiry'])
def test_enrollment_rechecks_after_password_verification(store, monkeypatch, change):
    user_id, token, claims = identity(store)
    def changed(*args, **kwargs):
        result = verify_password(*args, **kwargs)
        with Session(store.engine) as db, db.begin():
            if change == 'password': db.get(User, user_id).password_hash = 'changed-hash'
            if change == 'revocation': db.get(AuthSession, claims.session_id).revoked_at = datetime.now(timezone.utc)
        return result
    monkeypatch.setattr('app.modules.auth.vendor_service.verify_password', changed)
    if change == 'jwt_expiry':
        # The first validation succeeds, then admission samples after JWT expiry.
        original = VendorEnrollmentService._now
        calls = []
        def later(self, db):
            calls.append(True)
            return original(self, db) if len(calls) == 1 else claims.expires_at + timedelta(seconds=1)
        monkeypatch.setattr(VendorEnrollmentService, '_now', later)
    assert enroll(store, token).status_code == 401
    with Session(store.engine) as db:
        assert count(db, Vendor) == 0


def test_enrollment_insert_failure_rolls_back_and_redacts(store):
    user_id, token, _ = identity(store)
    def reject(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO vendors'):
            raise sa.exc.SQLAlchemyError('secret insert detail')
    sa.event.listen(store.engine, 'before_cursor_execute', reject)
    try:
        response = enroll(store, token)
    finally:
        sa.event.remove(store.engine, 'before_cursor_execute', reject)
    assert response.status_code == 503 and 'secret insert detail' not in response.text
    with Session(store.engine) as db:
        assert count(db, Vendor) == 0 and count(db, BuyerProfile) == 1
        assert db.get(User, user_id).role == 'buyer'


def test_enrollment_rate_limits_fail_closed(store, monkeypatch):
    from app.modules.auth.signup_rate_limit import SignupRateLimitedError
    from app.api.v1.buyer_login import enforce_limit
    _, token, _ = identity(store)
    monkeypatch.setattr('app.api.v1.vendor_registration.enforce_login_limit', enforce_limit)
    for error, status in [(SignupRateLimitedError(30), 429), (RateLimitUnavailableError(), 503)]:
        monkeypatch.setattr('app.api.v1.buyer_login.get_login_rate_limiter', lambda: Mock(check=Mock(side_effect=error)))
        assert enroll(store, token).status_code == status
    with Session(store.engine) as db:
        assert count(db, Vendor) == 0
