"""Private shop drafts, fail-closed verification, and additive migration checks."""
import importlib.util
import io
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.auth.session_service import SessionAuthenticationError
from app.modules.vendors.models import Vendor
from app.modules.vendors.onboarding_service import VendorOnboardingService, VerificationNotReadyError
from app.modules.vendors.onboarding_schemas import ShopInformationPatch
from tests.test_vendor_account import store as account_store, login_store, http_store, encoded_password, issue, get, ME
from tests.test_buyer_login_http import HEADERS

URL='/api/v1/auth/vendor/onboarding'


@pytest.fixture
def store(account_store,monkeypatch):
    monkeypatch.setattr('app.api.v1.vendor_onboarding.get_engine',lambda:account_store.engine)
    return account_store


def patch(store,token,body=None,headers=None):
    return store.client.patch(URL,json={'business_name':'  New   Shop  ','shop_location':' Ikeja  Lagos ',
        'shop_address':'  12   Test Road  '} if body is None else body,
        headers={**(HEADERS if headers is None else headers),'Authorization':'Bearer '+token})


def service(store):
    return VendorOnboardingService(store.engine,settings=store.settings)


@pytest.mark.parametrize('name',['buyer','missing'])
def test_private_shop_read_update_and_normalization(store,name,caplog):
    token,claims=issue(store,name)
    initial=get(store,URL,token)
    assert initial.status_code==200 and initial.json()=={'business_name':'Shop','shop_location':None,'shop_address':None,'verification_status':'pending'}
    response=patch(store,token)
    assert response.status_code==200
    assert response.json()=={'business_name':'New Shop','shop_location':'Ikeja Lagos','shop_address':'12 Test Road','verification_status':'pending'}
    assert get(store,URL,token).json()==response.json()
    assert response.headers['cache-control']=='no-store' and 'set-cookie' not in response.headers
    assert '12 Test Road' not in get(store,ME,token).text
    assert token not in caplog.text and '12 Test Road' not in caplog.text
    assert patch(store,token,{'shop_location':'Cafe\u0301'}).json()['shop_location']=='Café'
    with Session(store.engine) as db:
        vendor=db.scalar(sa.select(Vendor).where(Vendor.user_id==claims.user_id))
        assert vendor.business_name=='New Shop' and vendor.verification_status=='pending'


@pytest.mark.parametrize('status',['approved','suspended','rejected','pending'])
def test_edit_policy_and_status_preservation(store,status):
    token,claims=issue(store)
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status=status))
    assert get(store,URL,token).status_code==200
    response=patch(store,token)
    assert response.status_code==(200 if status in ('pending','rejected') else 403)
    with Session(store.engine) as db:
        vendor=db.scalar(sa.select(Vendor).where(Vendor.user_id==claims.user_id))
        assert vendor.verification_status==status
        if status in ('approved','suspended'): assert vendor.shop_address is None and vendor.business_name=='Shop'


def test_buyer_only_and_missing_bearer_denied(store):
    token,_=issue(store,'legacy')
    assert get(store,URL,token).status_code==403
    assert patch(store,token).status_code==403
    assert store.client.get(URL).status_code==401


@pytest.mark.parametrize('state',['revoked','expired','inactive'])
def test_live_authentication(store,state):
    token,claims=issue(store)
    with Session(store.engine) as db,db.begin():
        row=db.get(AuthSession,claims.session_id)
        if state=='revoked': row.revoked_at=datetime.now(timezone.utc)
        if state=='inactive': db.get(User,claims.user_id).is_active=False
        if state=='expired':
            row.created_at=datetime.now(timezone.utc)-timedelta(days=2)
            row.expires_at=datetime.now(timezone.utc)-timedelta(days=1)
    assert get(store,URL,token).status_code==401
    assert patch(store,token).status_code==401


@pytest.mark.parametrize('body',[{}, {'shop_address':None},{'shop_location':' '},{'shop_address':'x'*501},
    {'business_name':'x'*201},{'shop_location':False},{'shop_address':'secret\x00address'},
    {'verification_status':'approved'},{'is_verified':True},{'reviewer_id':'attacker'},
    {'approved_at':'2026-01-01'},{'phone_verified':True},{'government_id_document':'fake'}])
def test_validation_and_verification_injection(store,body):
    token,_=issue(store)
    response=patch(store,token,body)
    assert response.status_code==422
    assert response.json()['detail']['message']=='Invalid shop information'
    assert get(store,URL,token).json()['business_name']=='Shop'


def test_origin_csrf_size_content_type_and_cors(store):
    token,_=issue(store)
    assert patch(store,token,headers={}).status_code==403
    assert patch(store,token,headers={'Origin':HEADERS['Origin']}).status_code==403
    assert store.client.patch(URL,content='x'*16385,headers=HEADERS).status_code==413
    assert store.client.patch(URL,content='{}',headers={**HEADERS,'Authorization':'Bearer '+token,'Content-Type':'text/plain'}).status_code==415
    preflight=store.client.options(URL,headers={'Origin':HEADERS['Origin'],'Access-Control-Request-Method':'PATCH','Access-Control-Request-Headers':'Authorization, X-ScrapMart-CSRF, Content-Type'})
    assert preflight.status_code==200 and preflight.headers['cache-control']=='no-store'


@pytest.mark.parametrize('failure',['update','commit'])
def test_database_failure_rolls_back_and_redacts(store,failure):
    token,claims=issue(store)
    def fail_sql(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE vendors'): raise sa.exc.SQLAlchemyError('private address error')
    def fail_commit(connection): raise sa.exc.SQLAlchemyError('private commit error')
    event='before_cursor_execute' if failure=='update' else 'commit'
    handler=fail_sql if failure=='update' else fail_commit
    sa.event.listen(store.engine,event,handler)
    try: response=patch(store,token)
    finally: sa.event.remove(store.engine,event,handler)
    assert response.status_code==503 and 'private' not in response.text
    assert get(store,URL,token).json()=={'business_name':'Shop','shop_location':None,'shop_address':None,'verification_status':'pending'}


def test_readiness_never_substitutes_phone_number_status_or_shop_for_evidence(store):
    token,claims=issue(store)
    readiness=service(store).get_verification_readiness(claims)
    assert not readiness.shop_information_complete and not readiness.can_submit
    assert 'shop_information' in readiness.outstanding_requirements
    assert patch(store,token).status_code==200
    with Session(store.engine) as db,db.begin():
        db.get(User,claims.user_id).phone_number='+2348000000000'
    ready=service(store).get_verification_readiness(claims)
    assert ready.shop_information_complete and not ready.can_submit
    assert ready.outstanding_requirements==('secure_government_id_document','verified_phone_ownership')
    with pytest.raises(VerificationNotReadyError): service(store).require_verification_submission(claims)
    with pytest.raises(VendorPermissionError): service(store).require_approved_vendor(claims)
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status='approved'))
    # No fabricated document/phone ownership evidence, even for legacy approval.
    assert not service(store).get_verification_readiness(claims).can_submit


def test_update_locks_and_expiry_after_vendor_lock(store):
    _,claims=issue(store)
    statements=[]
    def observe(state): statements.append(str(state.statement.compile(dialect=postgresql.dialect())))
    def after_locks():
        assert statements[0].startswith('UPDATE users')
        assert 'auth_sessions' in statements[1] and 'FOR UPDATE' in statements[1]
        assert 'vendors' in statements[2] and 'FOR UPDATE' in statements[2]
        return claims.expires_at+timedelta(seconds=1)
    sa.event.listen(Session,'do_orm_execute',observe)
    try:
        with pytest.raises(SessionAuthenticationError):
            VendorOnboardingService(store.engine,clock=after_locks).update_shop_information(claims,ShopInformationPatch(shop_address='New address'))
    finally: sa.event.remove(Session,'do_orm_execute',observe)


def load_migration():
    path=Path(__file__).parents[1]/'alembic/versions/d73a5c9012ef_add_vendor_shop_information.py'
    spec=importlib.util.spec_from_file_location('vendor_shop_migration',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_additive_sql_and_existing_records():
    migration=load_migration()
    assert migration.down_revision=='c42f7d18a903'
    output=io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output,'version_table_schema':'test_schema'})):
        migration.upgrade()
    sql=output.getvalue()
    assert 'ALTER TABLE test_schema.vendors ADD COLUMN shop_location VARCHAR(200)' in sql
    assert 'ALTER TABLE test_schema.vendors ADD COLUMN shop_address VARCHAR(500)' in sql
    assert 'NOT NULL' not in sql and 'UPDATE ' not in sql and 'CREATE TABLE' not in sql
    # Disposable SQLite only: exercise migration, preserving historical data.
    engine=sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE vendors (id INTEGER PRIMARY KEY, business_name VARCHAR(200), verification_status VARCHAR(20))")
        connection.exec_driver_sql("INSERT INTO vendors VALUES (1, 'Existing shop', 'approved')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.exec_driver_sql('SELECT * FROM vendors').one()==(1,'Existing shop','approved',None,None)
            migration.downgrade()
            assert connection.exec_driver_sql('SELECT * FROM vendors').one()==(1,'Existing shop','approved')
    engine.dispose()
