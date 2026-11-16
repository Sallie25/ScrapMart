"""Shared Vendor/Buyer session lifecycle; no live PostgreSQL or Redis access."""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql

from app.modules.auth.models import User
from app.modules.auth.http_security import REFRESH_COOKIE
from app.modules.auth.security import verify_access_token
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionAuthenticationError
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError
from app.modules.vendors.models import Vendor
from tests.test_vendor_account import store, login_store, http_store, encoded_password, service, get, ME, CAP
from tests.test_buyer_login_http import HEADERS, URL as BUYER_LOGIN
from tests.test_buyer_login import PASSWORD
from tests.test_buyer_sessions_http import assert_cookie

ALL='/api/v1/auth/vendor/logout-all'
REFRESH='/api/v1/auth/refresh'
LOGOUT='/api/v1/auth/logout'


def issued(store, name='buyer', buyer=False):
    path=BUYER_LOGIN if buyer else '/api/v1/auth/vendor/login'
    response=store.client.post(path,json={'email':f'{name}@example.test','password':PASSWORD},headers=HEADERS)
    assert response.status_code==200
    access=response.json()['access_token']
    return access,response.cookies[REFRESH_COOKIE],verify_access_token(access,settings=store.settings)


def send(store,path,refresh):
    return store.client.post(path,headers={**HEADERS,'Cookie':f'{REFRESH_COOKIE}={refresh}'})


def logout_all(store,access):
    return store.client.post(ALL,headers={**HEADERS,'Authorization':'Bearer '+access})


@pytest.mark.parametrize('name',['buyer','missing'])
@pytest.mark.parametrize('status',['pending','approved','rejected','suspended'])
def test_vendor_refresh_retains_live_capabilities_and_no_approval(store,name,status):
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==store.ids[name]).values(verification_status=status))
    access,refresh,claims=issued(store,name)
    response=send(store,REFRESH,refresh)
    assert response.status_code==200
    assert_cookie(response)
    new_claims=verify_access_token(response.json()['access_token'],settings=store.settings)
    assert new_claims.session_id==claims.session_id
    assert response.cookies[REFRESH_COOKIE]!=refresh
    assert get(store,ME,response.json()['access_token']).json()['verification_status']==status
    assert get(store,'/api/v1/auth/me',response.json()['access_token']).status_code==(200 if name=='buyer' else 401)
    if status!='approved':
        with pytest.raises(VendorPermissionError): service(store).require_approved_vendor(new_claims)
    with Session(store.engine) as db:
        session=db.get(AuthSession,claims.session_id)
        assert all(t.expires_at==session.expires_at for t in db.scalars(sa.select(RefreshToken).where(RefreshToken.session_id==session.id)))


@pytest.mark.parametrize('name',['buyer','missing'])
def test_vendor_logout_revokes_only_cookie_session(store,name):
    access,refresh,claims=issued(store,name)
    other,other_refresh,other_claims=issued(store,name)
    response=send(store,LOGOUT,refresh)
    assert response.status_code==204 and response.content==b''
    assert_cookie(response,cleared=True)
    assert get(store,ME,access).status_code==401
    assert send(store,REFRESH,refresh).status_code==401
    assert get(store,ME,other).status_code==200
    assert send(store,LOGOUT,refresh).status_code==204
    with Session(store.engine) as db:
        assert db.get(AuthSession,other_claims.session_id).revoked_at is None


@pytest.mark.parametrize('status',['pending','approved','rejected','suspended'])
def test_logout_all_revokes_buyer_and_vendor_sessions_but_not_other_user(store,status):
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==store.ids['buyer']).values(verification_status=status))
    buyer,buyer_refresh,buyer_claims=issued(store,buyer=True)
    vendor,vendor_refresh,vendor_claims=issued(store)
    other,_,other_claims=issued(store,'missing')
    response=logout_all(store,vendor)
    assert response.status_code==204 and response.content==b''
    assert_cookie(response,cleared=True)
    assert response.headers['cache-control']=='no-store'
    for access,refresh in ((buyer,buyer_refresh),(vendor,vendor_refresh)):
        assert get(store,ME,access).status_code==401
        assert get(store,'/api/v1/auth/me',access).status_code==401
        assert send(store,REFRESH,refresh).status_code==401
    assert logout_all(store,vendor).status_code==401
    assert get(store,ME,other).status_code==200
    with Session(store.engine) as db:
        assert db.get(AuthSession,other_claims.session_id).revoked_at is None


def test_vendor_only_logout_all_and_buyer_only_denial(store):
    vendor,_,_=issued(store,'missing')
    assert store.client.post('/api/v1/auth/logout-all',headers={**HEADERS,'Authorization':'Bearer '+vendor}).status_code==401
    assert logout_all(store,vendor).status_code==204
    buyer,_,claims=issued(store,'legacy',buyer=True)
    response=logout_all(store,buyer)
    assert response.status_code==403 and 'set-cookie' not in response.headers
    with Session(store.engine) as db:
        assert db.get(AuthSession,claims.session_id).revoked_at is None


@pytest.mark.parametrize('path',[REFRESH,LOGOUT,ALL])
def test_origin_csrf_and_body_limit(store,path):
    access,refresh,_=issued(store)
    for headers in ({}, {'Origin':HEADERS['Origin']}, {**HEADERS,'Origin':'https://evil.test'}):
        response=store.client.post(path,headers={**headers,'Authorization':'Bearer '+access,'Cookie':f'{REFRESH_COOKIE}={refresh}'})
        assert response.status_code==403 and 'set-cookie' not in response.headers
    response=store.client.post(path,content='x'*16385,headers=HEADERS)
    assert response.status_code==413


@pytest.mark.parametrize('state',['invalid','revoked','expired','inactive'])
def test_logout_all_invalid_authentication(store,state):
    access,_,claims=issued(store)
    with Session(store.engine) as db,db.begin():
        session=db.get(AuthSession,claims.session_id)
        if state=='revoked': session.revoked_at=datetime.now(timezone.utc)
        if state=='inactive': db.get(User,claims.user_id).is_active=False
        if state=='expired':
            session.created_at=datetime.now(timezone.utc)-timedelta(days=2)
            session.expires_at=datetime.now(timezone.utc)-timedelta(days=1)
    response=logout_all(store,'invalid' if state=='invalid' else access)
    assert response.status_code==401 and 'set-cookie' not in response.headers


def test_live_suspension_after_login_refresh_and_replay_across_experiences(store,monkeypatch):
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==store.ids['buyer']).values(verification_status='approved'))
    buyer,old,claims=issued(store,buyer=True)
    from tests.review_support import prepare_case
    prepare_case(store,claims,monkeypatch,approve=True)
    service(store).require_approved_vendor(claims)
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status='suspended'))
    rotated=send(store,REFRESH,old)
    assert rotated.status_code==200
    new_access=rotated.json()['access_token']
    assert get(store,ME,new_access).json()['verification_status']=='suspended'
    with pytest.raises(VendorPermissionError):
        service(store).require_approved_vendor(verify_access_token(new_access,settings=store.settings))
    assert get(store,'/api/v1/auth/me',new_access).status_code==200
    assert send(store,REFRESH,old).status_code==401
    assert get(store,ME,buyer).status_code==401
    assert get(store,'/api/v1/auth/me',new_access).status_code==401
    assert send(store,REFRESH,rotated.cookies[REFRESH_COOKIE]).status_code==401


@pytest.mark.parametrize('state',['inactive','expired','revoked'])
def test_refresh_checks_live_account_and_session(store,state):
    _,refresh,claims=issued(store,'missing')
    with Session(store.engine) as db,db.begin():
        session=db.get(AuthSession,claims.session_id)
        if state=='inactive': db.get(User,claims.user_id).is_active=False
        if state=='revoked': session.revoked_at=datetime.now(timezone.utc)
        if state=='expired':
            session.created_at=datetime.now(timezone.utc)-timedelta(days=2)
            session.expires_at=datetime.now(timezone.utc)-timedelta(days=1)
    assert send(store,REFRESH,refresh).status_code==401


def test_concurrent_vendor_refresh_commits_replay_revocation(store,monkeypatch):
    access,refresh,claims=issued(store,'missing')
    engine=sa.create_engine(store.engine.url,connect_args={'check_same_thread':False,'timeout':10})
    @sa.event.listens_for(engine,'connect')
    def foreign_keys(connection,_): connection.execute('PRAGMA foreign_keys=ON')
    monkeypatch.setattr('app.api.v1.buyer_sessions.get_engine',lambda:engine)
    barrier=threading.Barrier(2)
    def synchronize(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE users'): barrier.wait(timeout=10)
    sa.event.listen(engine,'before_cursor_execute',synchronize)
    def refresh_request():
        with TestClient(store.client.app,base_url='https://api.example.test') as client:
            return client.post(REFRESH,headers={**HEADERS,'Cookie':f'{REFRESH_COOKIE}={refresh}'})
    try:
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(refresh_request) for _ in range(2)]
            responses=[future.result(timeout=30) for future in futures]
    finally:
        sa.event.remove(engine,'before_cursor_execute',synchronize)
        engine.dispose()
    assert sorted(r.status_code for r in responses)==[200,401]
    assert get(store,ME,access).status_code==401
    winner=next(r for r in responses if r.status_code==200)
    assert send(store,REFRESH,winner.cookies[REFRESH_COOKIE]).status_code==401
    with Session(store.engine) as db:
        assert db.get(AuthSession,claims.session_id).revoked_at is not None
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken).where(RefreshToken.session_id==claims.session_id))==2


@pytest.mark.parametrize('path',[REFRESH,LOGOUT,ALL])
def test_infrastructure_failure_retains_cookie_and_redacts(store,monkeypatch,path,caplog):
    access,refresh,_=issued(store)
    target='app.api.v1.vendor_account.get_engine' if path==ALL else 'app.api.v1.buyer_sessions.get_engine'
    monkeypatch.setattr(target,Mock(side_effect=sa.exc.SQLAlchemyError('private database detail')))
    response=store.client.post(path,headers={**HEADERS,'Authorization':'Bearer '+access,'Cookie':f'{REFRESH_COOKIE}={refresh}'})
    assert response.status_code==503 and 'set-cookie' not in response.headers
    assert response.headers['cache-control']=='no-store'
    for value in ('private database detail',access,refresh): assert value not in response.text+caplog.text


def test_logout_all_commit_failure_rolls_back(store):
    access,_,claims=issued(store)
    def fail(connection): raise sa.exc.SQLAlchemyError('private commit detail')
    sa.event.listen(store.engine,'commit',fail)
    try: response=logout_all(store,access)
    finally: sa.event.remove(store.engine,'commit',fail)
    assert response.status_code==503 and 'set-cookie' not in response.headers
    with Session(store.engine) as db:
        assert db.get(AuthSession,claims.session_id).revoked_at is None


def test_logout_all_rechecks_revocation_and_expiry_after_locks(store,monkeypatch):
    access,_,claims=issued(store)
    newer,_,newer_claims=issued(store)
    original=VendorAuthorizationService._lock_user
    def revoked(db,user_id):
        user=original(db,user_id)
        db.execute(sa.update(AuthSession).where(AuthSession.id==claims.session_id).values(revoked_at=datetime.now(timezone.utc)))
        return user
    monkeypatch.setattr(VendorAuthorizationService,'_lock_user',staticmethod(revoked))
    assert logout_all(store,access).status_code==401
    with Session(store.engine) as db:
        assert db.get(AuthSession,newer_claims.session_id).revoked_at is None
    monkeypatch.setattr(VendorAuthorizationService,'_lock_user',staticmethod(original))
    statements=[]
    def observe(state): statements.append(str(state.statement.compile(dialect=postgresql.dialect())))
    def after_locks():
        assert 'UPDATE users' in statements[0]
        assert 'auth_sessions' in statements[1] and 'FOR UPDATE' in statements[1]
        assert 'vendors' in statements[2] and 'FOR SHARE' in statements[2]
        return newer_claims.expires_at+timedelta(seconds=1)
    sa.event.listen(Session,'do_orm_execute',observe)
    try:
        with pytest.raises(SessionAuthenticationError):
            service(store,clock=after_locks).revoke_all_vendor_sessions(newer_claims)
    finally: sa.event.remove(Session,'do_orm_execute',observe)
    with Session(store.engine) as db:
        assert db.get(AuthSession,newer_claims.session_id).revoked_at is None
