"""Offline Vendor profile/capability and transaction-bound authorization checks."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import jwt
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql

from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.security import create_access_token, verify_access_token
from app.modules.auth.session_service import SessionService, SessionAuthenticationError, SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError
from app.modules.buyers.models import BuyerProfile
from app.modules.vendors.models import Vendor
from tests.test_buyer_login import encoded_password
from tests.test_buyer_login_http import http_store
from tests.test_vendor_login import store as login_store

ME = '/api/v1/auth/vendor/me'
CAP = '/api/v1/auth/capabilities'


@pytest.fixture
def store(login_store, monkeypatch):
    monkeypatch.setattr('app.api.v1.vendor_account.get_engine', lambda: login_store.engine)
    return login_store


def issue(store, name='buyer'):
    credentials = SessionService(store.engine, settings=store.settings).create_session(store.ids[name])
    token = create_access_token(credentials.user_id, credentials.session_id, settings=store.settings)
    return token, verify_access_token(token, settings=store.settings)


def get(store, path, token):
    return store.client.get(path, headers={'Authorization':'Bearer '+token})


def service(store, **kwargs):
    return VendorAuthorizationService(store.engine, settings=store.settings, **kwargs)


@pytest.mark.parametrize('status', ['pending','approved','rejected','suspended'])
def test_profile_safe_projection_and_live_status(store, status, caplog):
    token, claims = issue(store)
    with Session(store.engine) as db, db.begin():
        user = db.get(User, claims.user_id)
        user.full_name, user.phone_number = 'Owner', '+2348000000000'
        password_hash = user.password_hash
        vendor = db.scalar(sa.select(Vendor).where(Vendor.user_id == claims.user_id))
        vendor.verification_status = status
        vendor_id, created_at = vendor.id, vendor.created_at
    statements = []
    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    sa.event.listen(store.engine, 'before_cursor_execute', observe)
    try:
        response = get(store, ME, token)
    finally:
        sa.event.remove(store.engine, 'before_cursor_execute', observe)
    assert response.status_code == 200
    assert response.json() == {'business_name':'Shop','verification_status':status,
        'full_name':'Owner','email':'buyer@example.test','phone_number':'+2348000000000',
        'created_at':created_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00','Z')}
    assert response.headers['cache-control'] == 'no-store' and 'set-cookie' not in response.headers
    assert not any('password_hash' in sql or 'refresh_tokens' in sql or sql.startswith(('UPDATE','INSERT','DELETE')) for sql in statements)
    for secret in (password_hash,token,str(claims.user_id),str(claims.session_id),str(vendor_id)):
        assert secret not in response.text and secret not in caplog.text


@pytest.mark.parametrize('name,buyer,vendor', [('buyer',True,True),('missing',False,True),('legacy',True,False)])
def test_experience_isolation_and_capabilities(store, name, buyer, vendor):
    token, _ = issue(store, name)
    before = []
    with Session(store.engine) as db:
        before = [db.scalar(sa.select(sa.func.count()).select_from(m)) for m in (User,BuyerProfile,Vendor,AuthSession)]
    response = get(store,CAP,token)
    assert response.status_code == 200
    assert response.json() == {'buyer':buyer,'vendor':vendor,'vendor_verification_status':'pending' if vendor else None}
    assert get(store,ME,token).status_code == (200 if vendor else 403)
    assert get(store,'/api/v1/auth/me',token).status_code == (200 if buyer else 401)
    # Repeated experience selection is just authorized reads, not enrollment.
    assert get(store,CAP,token).json() == response.json()
    with Session(store.engine) as db:
        assert [db.scalar(sa.select(sa.func.count()).select_from(m)) for m in (User,BuyerProfile,Vendor,AuthSession)] == before


@pytest.mark.parametrize('path', [ME,CAP])
@pytest.mark.parametrize('state', ['invalid','jwt_expired','session_expired','revoked','inactive','wrong_owner','missing'])
def test_authentication_rejections(store, path, state):
    token, claims = issue(store)
    with Session(store.engine) as db, db.begin():
        row = db.get(AuthSession,claims.session_id)
        if state == 'revoked': row.revoked_at = datetime.now(timezone.utc)
        if state == 'session_expired':
            row.created_at = datetime.now(timezone.utc)-timedelta(days=2)
            row.expires_at = datetime.now(timezone.utc)-timedelta(days=1)
        if state == 'inactive': db.get(User,claims.user_id).is_active = False
        if state == 'wrong_owner': row.user_id = store.ids['legacy']
        if state == 'missing':
            db.execute(sa.delete(RefreshToken).where(RefreshToken.session_id==row.id))
            db.delete(row)
    if state == 'invalid': token = 'invalid'
    if state == 'jwt_expired':
        payload = jwt.decode(token,options={'verify_signature':False})
        payload['iat'] -= 3600; payload['nbf'] -= 3600; payload['exp'] -= 3600
        import base64
        key = base64.urlsafe_b64decode(store.settings.jwt_signing_secret.get_secret_value()+'=')
        token = jwt.encode(payload,key,algorithm='HS256')
    response = get(store,path,token)
    assert response.status_code == 401
    assert response.json()['detail']['code'] == 'invalid_session'
    assert response.headers['cache-control'] == 'no-store' and 'set-cookie' not in response.headers


@pytest.mark.parametrize('status', ['pending','approved','rejected','suspended'])
def test_approved_only_read_and_mutation_authorization(store, status, monkeypatch):
    _, claims = issue(store)
    with Session(store.engine) as db, db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status=status))
    callback = Mock(return_value='done')
    if status == 'approved':
        from tests.review_support import prepare_case
        prepare_case(store,claims,monkeypatch,approve=True)
        identity = service(store).require_approved_vendor(claims)
        assert identity.user_id == claims.user_id
        assert service(store).run_approved_vendor_operation(claims,callback) == 'done'
        assert callback.call_count == 1
    else:
        with pytest.raises(VendorPermissionError): service(store).require_approved_vendor(claims)
        with pytest.raises(VendorPermissionError): service(store).run_approved_vendor_operation(claims,callback)
        callback.assert_not_called()


def test_suspension_effective_with_same_token_and_no_cached_grant(store,monkeypatch):
    token, claims = issue(store)
    from tests.review_support import prepare_case
    prepare_case(store,claims,monkeypatch,approve=True)
    for status in ('approved','suspended','rejected','pending'):
        with Session(store.engine) as db, db.begin():
            db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status=status))
        assert get(store,ME,token).json()['verification_status'] == status
        assert get(store,CAP,token).json()['vendor_verification_status'] == status
        if status == 'approved': service(store).require_approved_vendor(claims)
        else:
            with pytest.raises(VendorPermissionError): service(store).require_approved_vendor(claims)


def test_mutation_callback_shares_transaction_and_rollback(store,monkeypatch):
    _,claims=issue(store)
    from tests.review_support import prepare_case
    prepare_case(store,claims,monkeypatch,approve=True)
    # An isolated operation table avoids mutating the verified shop evidence.
    with store.engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE operation_effects (value TEXT)')
        db.exec_driver_sql("INSERT INTO operation_effects VALUES ('initial')")
    def write(db, identity):
        assert db.in_transaction() and identity.user_id == claims.user_id
        db.execute(sa.text("UPDATE operation_effects SET value='Changed'"))
        return 'committed'
    assert service(store).run_approved_vendor_operation(claims,write) == 'committed'
    def fail(db, identity):
        db.execute(sa.text("UPDATE operation_effects SET value='Rolled back'"))
        raise sa.exc.SQLAlchemyError('private failure')
    with pytest.raises(SessionPersistenceError): service(store).run_approved_vendor_operation(claims,fail)
    with store.engine.connect() as db:
        assert db.exec_driver_sql('SELECT value FROM operation_effects').scalar_one() == 'Changed'


def test_mutation_locks_order_and_post_lock_expiry(store):
    _,claims=issue(store)
    with Session(store.engine) as db, db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status='approved'))
    statements=[]
    def observe(state):
        statements.append(str(state.statement.compile(dialect=postgresql.dialect())))
    sa.event.listen(Session,'do_orm_execute',observe)
    callback=Mock()
    def after_locks():
        assert any('UPDATE users' in sql for sql in statements)
        assert any('FOR UPDATE' in sql and 'auth_sessions' in sql for sql in statements)
        assert any('FOR SHARE' in sql and 'vendors' in sql for sql in statements)
        return claims.expires_at+timedelta(seconds=1)
    try:
        with pytest.raises(SessionAuthenticationError):
            service(store,clock=after_locks).run_approved_vendor_operation(claims,callback)
    finally:
        sa.event.remove(Session,'do_orm_execute',observe)
    callback.assert_not_called()
    assert statements[0].startswith('UPDATE users')
    assert 'auth_sessions' in statements[1] and 'FOR UPDATE' in statements[1]
    assert 'vendors' in statements[2] and 'FOR SHARE' in statements[2]


@pytest.mark.parametrize('path',[ME,CAP])
def test_safe_infrastructure_errors(store,monkeypatch,path,caplog):
    token,_=issue(store)
    monkeypatch.setattr('app.api.v1.vendor_account.get_engine', Mock(side_effect=sa.exc.SQLAlchemyError('private database error')))
    response=get(store,path,token)
    assert response.status_code==503 and 'private database error' not in response.text+caplog.text
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('state',['revoked','inactive','expired','missing_vendor'])
def test_selling_helpers_reject_without_running_mutation(store,state):
    _,claims=issue(store)
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status='approved'))
        if state=='revoked': db.get(AuthSession,claims.session_id).revoked_at=datetime.now(timezone.utc)
        if state=='inactive': db.get(User,claims.user_id).is_active=False
        if state=='missing_vendor': db.execute(sa.delete(Vendor).where(Vendor.user_id==claims.user_id))
    if state=='expired':
        from dataclasses import replace
        claims=replace(claims,expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
    error=VendorPermissionError if state=='missing_vendor' else SessionAuthenticationError
    with pytest.raises(error): service(store).require_approved_vendor(claims)
    callback=Mock()
    with pytest.raises(error): service(store).run_approved_vendor_operation(claims,callback)
    callback.assert_not_called()


def test_no_profiles_capabilities_do_not_infer_legacy_role(store):
    token,claims=issue(store,'legacy')
    with Session(store.engine) as db,db.begin():
        db.execute(sa.delete(BuyerProfile).where(BuyerProfile.user_id==claims.user_id))
        assert db.get(User,claims.user_id).role=='vendor'
    response=get(store,CAP,token)
    assert response.status_code==200
    assert response.json()=={'buyer':False,'vendor':False,'vendor_verification_status':None}
    assert response.headers['cache-control']=='no-store' and 'set-cookie' not in response.headers
    assert get(store,ME,token).status_code==403


def test_buyer_logout_all_still_revokes_vendor_profile_access(store):
    from tests.test_buyer_login_http import HEADERS
    token,_=issue(store)
    response=store.client.post('/api/v1/auth/logout-all',headers={**HEADERS,'Authorization':'Bearer '+token})
    assert response.status_code==204
    assert get(store,ME,token).status_code==401
    assert get(store,CAP,token).status_code==401
