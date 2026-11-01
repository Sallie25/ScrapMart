"""D3 only: new labelled disposable Docker instance; never use configurable URLs."""
import importlib.util
import io
import json
import os
import secrets
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from PIL import Image

from app.operations.runtime_role import provision, audit, RuntimeRoleRejected, ROLE, HEAD
from app.operations.staging_bootstrap import activate_empty
from app.core.config import Settings
from app.modules.auth.registration_service import BuyerRegistrationService
from app.modules.auth.registration_schemas import BuyerSignupRequest
from app.modules.auth.vendor_service import VendorRegistrationService
from app.modules.auth.vendor_schemas import VendorSignupRequest
from app.modules.auth.login_schemas import BuyerLoginRequest
from app.modules.auth.login_service import BuyerLoginService
from app.modules.auth.vendor_login_service import VendorLoginService
from app.modules.auth.security import create_access_token, verify_access_token
from app.modules.auth.session_service import SessionService
from app.modules.auth.models import User
from app.modules.vendors.models import Vendor
from app.modules.vendors.reviewer_provisioning import provision_reviewer
from app.modules.vendors.review_service import VerificationReviewService
from app.modules.vendors.onboarding_service import VendorOnboardingService
from app.modules.vendors.onboarding_schemas import ShopInformationPatch
from app.modules.vendors.document_service import VendorDocumentService, IdentificationType
from app.modules.auth.phone_service import PhoneVerificationService
from app.modules.categories.models import Category
from app.modules.listings.service import MarketplaceService
from app.modules.listings.schemas import ListingCreate
from app.modules.orders.service import OrderService, OrderConflict
from app.modules.orders.schemas import PlaceOrderRequest
from app.modules.messaging.service import MessagingService, ConversationNotFound
from app.modules.messaging.schemas import StartConversation, SendMessage, ReadMessage

pytestmark=pytest.mark.skipif(os.environ.get('SCRAPMART_RUN_D3_POSTGRES_TESTS')!='1',reason='Explicit D3 disposable PostgreSQL opt-in required')


class Storage:
    def __init__(self): self.objects={}
    def put(self,key,content): self.objects[key]=content
    def exists(self,key): return key in self.objects
    def read(self,key): return self.objects[key]
    def delete(self,key): self.objects.pop(key,None)
    def public_url(self,key): return 'https://photos.example.test/'+key


def url(user):
    return sa.URL.create('postgresql+psycopg',username=user,host='127.0.0.1',port=55439,database='scrapmart_staging')


@pytest.fixture(scope='module')
def database():
    raw=subprocess.run(['docker','inspect','scrapmart-d3-postgres','--format',
        '{{json .Config.Labels}}\n{{json .NetworkSettings.Ports}}\n{{json .Config.Image}}'],capture_output=True,text=True,check=True,timeout=10)
    labels,ports,image=map(json.loads,raw.stdout.splitlines())
    if labels.get('scrapmart.disposable')!='d3' or ports!={'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'55439'}]} or image!='postgres:16':
        raise RuntimeError('Not the approved disposable instance')
    admin=sa.create_engine(url('postgres'),hide_parameters=True)
    with admin.begin() as db:
        if db.scalar(sa.text('SELECT current_database()'))!='scrapmart_staging': raise RuntimeError('Wrong database')
        tables=sa.inspect(db).get_table_names(schema='public')
        if tables: raise RuntimeError('Disposable database must start empty; never reset an unverified database')
        config=Config('alembic.ini');config.attributes['connection']=db
        command.upgrade(config,HEAD)
        activate_empty(db)
        provision(db,harden_public=True)
        db.exec_driver_sql(f'ALTER ROLE {ROLE} LOGIN')  # Localhost-only trust auth; no embedded password.
    runtime=sa.create_engine(url(ROLE),hide_parameters=True)
    yield SimpleNamespace(admin=admin,runtime=runtime)
    runtime.dispose();admin.dispose()
    # Container is operator-removable; no destructive automatic cleanup.


@pytest.fixture(scope='module')
def store(database):
    settings=Settings(_env_file=None,_secrets_dir=None,jwt_signing_secret=secrets.token_urlsafe(32),phone_otp_secret=secrets.token_urlsafe(32))
    result=SimpleNamespace(**vars(database),settings=settings,storage=Storage(),photos=Storage())
    def account(vendor=False):
        email=uuid.uuid4().hex+'@example.test';password=secrets.token_urlsafe(24)
        fields=dict(email=email,password=password,full_name='D3 Test',phone_number='+2348012345678')
        if vendor:
            VendorRegistrationService(result.runtime).register(VendorSignupRequest(**fields,business_name='D3 Shop'))
            credentials=VendorLoginService(result.runtime,settings=settings).login(BuyerLoginRequest(email=email,password=password))
        else:
            BuyerRegistrationService(result.runtime).register(BuyerSignupRequest(**fields))
            credentials=BuyerLoginService(result.runtime,settings=settings).login(BuyerLoginRequest(email=email,password=password))
        access=create_access_token(credentials.user_id,credentials.session_id,settings=settings)
        return verify_access_token(access,settings=settings),credentials
    result.account=account
    result.buyer,result.buyer_credentials=account()
    result.vendor,result.vendor_credentials=account(True)
    result.reviewer,_=account()
    result.outsider,_=account()
    provision_reviewer(result.admin,result.reviewer.user_id,'D3 disposable fixture')
    with Session(result.admin) as db,db.begin():
        row=Category(name='D3 Metal',slug='d3-metal');db.add(row);db.flush();result.category=row.id
    return result


@pytest.fixture
def approved(store,monkeypatch):
    monkeypatch.setattr('app.modules.vendors.evidence.get_private_document_storage',lambda _:store.storage)
    monkeypatch.setattr('app.modules.listings.service.get_listing_photo_storage',lambda _:store.photos)
    with Session(store.admin) as db:
        vendor=db.scalar(sa.select(Vendor).where(Vendor.user_id==store.vendor.user_id))
        already=vendor.verification_status=='approved';vendor_id=vendor.id
    if not already:
        VendorOnboardingService(store.runtime,settings=store.settings).update_shop_information(store.vendor,
            ShopInformationPatch(shop_location='Ikeja',shop_address='D3 Test Address'))
        image=io.BytesIO();Image.new('RGB',(20,20),'white').save(image,format='PNG')
        VendorDocumentService(store.runtime,settings=store.settings).submit(store.vendor,IdentificationType.NATIONAL_ID,image.getvalue(),store.storage)
        sms=SimpleNamespace(send_code=lambda phone,code,**kw:setattr(store,'code',code))
        phone=PhoneVerificationService(store.runtime,settings=store.settings)
        phone.send_code(store.vendor,sms,store.settings)
        assert phone.verify_code(store.vendor,store.code,store.settings)
        del store.code
        review=VerificationReviewService(store.runtime,settings=store.settings,storage=store.storage)
        review.submit_for_review(store.vendor)
        case=review.get_case(store.reviewer,vendor_id)
        review.decide(store.reviewer,vendor_id,'approve',case.case_version,case.evidence_revision,'D3 fixture approval')
    return store


def listing(store):
    service=MarketplaceService(store.runtime,settings=store.settings)
    value=ListingCreate(title='D3 stock',category_id=store.category,price='20',description='D3 metal',condition='used',
        quantity='2',quantity_unit='kilograms',price_type='per_unit',location_summary='Ikeja',latitude='6.6',longitude='3.3',location_visibility='approximate')
    row=service.create(store.vendor,value);key=row['id']
    from app.modules.listings.models import ListingImage
    photo_key='listings/'+uuid.uuid4().hex+'.jpg';store.photos.put(photo_key,b'fixture-only')
    with Session(store.runtime) as db,db.begin():
        db.add(ListingImage(listing_id=key,object_key=photo_key,position=0,content_type='image/jpeg',size_bytes=12))
    service.transition(store.vendor,key,'publish',consent=True)
    return key


def test_real_login_signup_and_session_returning(store):
    with store.runtime.connect() as db: assert db.scalar(sa.text('SELECT current_user'))==ROLE
    sessions=SessionService(store.runtime,settings=store.settings)
    assert sessions.get_buyer_profile(store.buyer).email
    rotated=sessions.rotate_refresh_token(store.buyer_credentials.refresh_token)
    assert rotated.user_id==store.buyer.user_id
    assert sessions.revoke_refresh_session(rotated.refresh_token)
    # Replace revoked fixture session for the remaining tests.
    credentials=sessions.create_session(store.buyer.user_id)
    store.buyer=verify_access_token(create_access_token(credentials.user_id,credentials.session_id,settings=store.settings),settings=store.settings)


def test_vendor_verification_and_photo_trigger_orm(approved):
    key=listing(approved)
    with approved.runtime.begin() as db:
        db.execute(sa.text('UPDATE public.listings SET id=id WHERE id=:id'),{'id':key})
        db.execute(sa.text('SELECT id FROM public.categories FOR SHARE'))
        db.execute(sa.text('SELECT id FROM public.buyer_profiles FOR SHARE'))
    with pytest.raises(sa.exc.DBAPIError),approved.runtime.begin() as db:
        db.execute(sa.text('DELETE FROM public.listing_images WHERE listing_id=:id'),{'id':key})
    # Last-photo deletion fails at commit; record and photo survive.
    with approved.runtime.connect() as db:
        assert db.scalar(sa.text('SELECT count(*) FROM public.listing_images WHERE listing_id=:id'),{'id':key})==1


def test_orders_concurrent_inventory_and_returning(approved):
    key=listing(approved);barrier=threading.Barrier(2)
    def place(claims):
        barrier.wait(timeout=10)
        try:
            return OrderService(approved.runtime,settings=approved.settings).place(claims,
                PlaceOrderRequest(listing_id=key,quantity='2',request_id=uuid.uuid4()))
        except OrderConflict: return None
    with ThreadPoolExecutor(2) as pool: rows=list(pool.map(place,[approved.buyer,approved.outsider]))
    assert sum(row is not None for row in rows)==1
    order=next(row for row in rows if row)
    service=OrderService(approved.runtime,settings=approved.settings)
    service.vendor_transition(approved.vendor,order['id'],'accept')
    service.vendor_transition(approved.vendor,order['id'],'prepare')
    service.vendor_transition(approved.vendor,order['id'],'deliver')
    # Identify the Buyer through its scoped history, not an administrator shortcut.
    buyer=next(c for c in (approved.buyer,approved.outsider) if service.read(c)['orders'])
    assert service.buyer_transition(buyer,order['id'],'complete')['status']=='completed'


def test_messaging_isolation_and_retry_concurrency(approved):
    key=listing(approved);service=MessagingService(approved.runtime,settings=approved.settings)
    with ThreadPoolExecutor(2) as pool:
        rows=list(pool.map(lambda _:service.start(approved.buyer,StartConversation(listing_id=key)),range(2)))
    assert rows[0]['id']==rows[1]['id'];conversation=rows[0]['id']
    value=SendMessage(content='D3 hello',request_id=uuid.uuid4())
    with ThreadPoolExecutor(2) as pool:
        messages=list(pool.map(lambda _:service.run(approved.buyer,'send',key=conversation,value=value),range(2)))
    assert messages[0]['id']==messages[1]['id']
    with pytest.raises(ConversationNotFound): service.run(approved.outsider,'history',key=conversation)
    assert service.run(approved.vendor,'unread')['unread_count']>=1
    assert service.run(approved.vendor,'read',key=conversation,value=ReadMessage(message_id=messages[0]['id']))['read_at']


@pytest.mark.parametrize('sql',[
    "UPDATE public.email_identity_policy_state SET status='building'",
    'UPDATE public.email_identity_policy_state SET users_processed=0',
    'UPDATE public.verification_reviewers SET revoked_at=now()',
    'INSERT INTO public.verification_reviewers SELECT * FROM public.verification_reviewers',
    'UPDATE public.alembic_version SET version_num=version_num',
    'CREATE TABLE public.runtime_forbidden (id int)',
    'ALTER TABLE public.users DISABLE TRIGGER ALL',
    'DROP TABLE public.messages',
    'TRUNCATE public.users CASCADE',
    "SET session_replication_role='replica'",
    'SET ROLE postgres',
    'CREATE TEMP TABLE runtime_forbidden (id int)',
    'UPDATE public.users SET is_active=true',
    'UPDATE public.verification_review_audit SET reason=reason',
    'DELETE FROM public.orders',
])
def test_denied_permissions(store,sql):
    with pytest.raises(sa.exc.DBAPIError) as error,store.runtime.begin() as db: db.exec_driver_sql(sql)
    assert error.value.orig.sqlstate=='42501'


@pytest.mark.parametrize('table',['buyer_profiles','categories','listings'])
def test_identifier_changes_rejected(approved,table):
    if table=='listings': listing(approved)
    with pytest.raises(sa.exc.DBAPIError) as error,approved.runtime.begin() as db:
        db.execute(sa.text(f'UPDATE public.{table} SET id=:id'),{'id':uuid.uuid4()})
    assert error.value.orig.sqlstate=='23514'


def test_provision_idempotency_and_excess_grant_rejection(store):
    with store.admin.begin() as db: provision(db);provision(db)
    with store.admin.begin() as db: db.exec_driver_sql(f'GRANT UPDATE (status) ON public.email_identity_policy_state TO {ROLE}')
    try:
        with pytest.raises(RuntimeRoleRejected),store.admin.begin() as db: provision(db)
    finally:
        with store.admin.begin() as db: db.exec_driver_sql(f'REVOKE UPDATE (status) ON public.email_identity_policy_state FROM {ROLE}')
    with store.admin.begin() as db: audit(db)


def test_photo_guard_cannot_be_redirected_to_temp_relations(approved):
    key=listing(approved)
    # Maintenance can create temporary tables; even its altered search path must
    # not redirect the hardened invoker trigger to fake public-photo metadata.
    with pytest.raises(sa.exc.DBAPIError) as error,approved.admin.begin() as db:
        db.exec_driver_sql('CREATE TEMP TABLE listing_images (listing_id uuid)')
        db.execute(sa.text('INSERT INTO pg_temp.listing_images VALUES (:id)'),{'id':key})
        db.exec_driver_sql('SET LOCAL search_path=pg_temp,public,pg_catalog')
        db.execute(sa.text('DELETE FROM public.listing_images WHERE listing_id=:id'),{'id':key})
    assert error.value.orig.sqlstate=='23514'


def test_database_setting_drift_and_grant_options_rejected(store):
    with store.admin.begin() as db:
        db.exec_driver_sql(f'ALTER ROLE {ROLE} IN DATABASE scrapmart_staging SET statement_timeout=0')
    try:
        with pytest.raises(RuntimeRoleRejected),store.admin.begin() as db: provision(db)
    finally:
        with store.admin.begin() as db:
            db.exec_driver_sql(f'ALTER ROLE {ROLE} IN DATABASE scrapmart_staging RESET statement_timeout')
    with store.admin.begin() as db:
        db.exec_driver_sql(f'GRANT CONNECT ON DATABASE scrapmart_staging TO {ROLE} WITH GRANT OPTION')
    try:
        with pytest.raises(RuntimeRoleRejected),store.admin.begin() as db: provision(db)
    finally:
        with store.admin.begin() as db:
            db.exec_driver_sql(f'REVOKE GRANT OPTION FOR CONNECT ON DATABASE scrapmart_staging FROM {ROLE}')
    with store.admin.begin() as db: audit(db)


def test_public_privilege_drift_fails_without_repair_flag(store):
    with store.admin.begin() as db: db.exec_driver_sql('GRANT TEMPORARY ON DATABASE scrapmart_staging TO PUBLIC')
    try:
        with pytest.raises(RuntimeRoleRejected),store.admin.begin() as db: provision(db)
    finally:
        with store.admin.begin() as db: db.exec_driver_sql('REVOKE TEMPORARY ON DATABASE scrapmart_staging FROM PUBLIC')


def test_membership_and_ownership_drift_rejected(store):
    with store.admin.begin() as db:
        db.exec_driver_sql('CREATE ROLE d3_unexpected_group NOLOGIN')
        db.exec_driver_sql(f'GRANT d3_unexpected_group TO {ROLE}')
    try:
        with pytest.raises(RuntimeRoleRejected),store.admin.begin() as db: provision(db)
    finally:
        with store.admin.begin() as db: db.exec_driver_sql(f'REVOKE d3_unexpected_group FROM {ROLE}')
    with store.admin.begin() as db: db.exec_driver_sql(f'ALTER TABLE public.categories OWNER TO {ROLE}')
    try:
        with pytest.raises(RuntimeRoleRejected),store.admin.begin() as db: provision(db)
    finally:
        with store.admin.begin() as db: db.exec_driver_sql('ALTER TABLE public.categories OWNER TO postgres')
        # Ownership transfer strips former-owner ACLs; restore the approved
        # missing column grants after restoring the fixture owner.
        with store.admin.begin() as db: provision(db)
    with store.admin.begin() as db: audit(db)


def test_guards_and_constraints_survive_role_change(store):
    for table in ('email_identity_policy_state','email_identity_reservations'):
        with pytest.raises(sa.exc.DBAPIError) as error,store.runtime.begin() as db:
            db.execute(sa.text(f'UPDATE public.{table} SET id=:id WHERE id=(SELECT id FROM public.{table} LIMIT 1)'),{'id':uuid.uuid4()})
        assert error.value.orig.sqlstate=='23514'


def test_schema_drift_is_rejected_without_expanding_acl(store):
    with store.admin.begin() as db: db.exec_driver_sql('ALTER TABLE public.messages ADD COLUMN d3_unexpected text')
    try:
        with pytest.raises(RuntimeRoleRejected),store.admin.begin() as db: provision(db)
    finally:
        with store.admin.begin() as db: db.exec_driver_sql('ALTER TABLE public.messages DROP COLUMN d3_unexpected')


def test_photo_removal_orm_succeeds_for_inactive_listing(approved):
    from app.modules.listings.models import ListingImage
    key=listing(approved)
    MarketplaceService(approved.runtime,settings=approved.settings).transition(approved.vendor,key,'pause')
    with Session(approved.runtime) as db,db.begin():
        row=db.scalar(sa.select(ListingImage).where(ListingImage.listing_id==key))
        db.delete(row)
    with approved.runtime.connect() as db:
        assert db.scalar(sa.text('SELECT count(*) FROM public.listing_images WHERE listing_id=:id'),{'id':key})==0


def test_restricted_order_insert_rollback_does_not_reserve_stock(approved):
    key=listing(approved)
    def failure(connection,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO order_items'): raise sa.exc.SQLAlchemyError('isolated fixture failure')
    sa.event.listen(approved.runtime,'before_cursor_execute',failure)
    from app.modules.auth.session_service import SessionPersistenceError
    try:
        with pytest.raises(SessionPersistenceError):
            OrderService(approved.runtime,settings=approved.settings).place(approved.buyer,
                PlaceOrderRequest(listing_id=key,quantity='2',request_id=uuid.uuid4()))
    finally: sa.event.remove(approved.runtime,'before_cursor_execute',failure)
    row=OrderService(approved.runtime,settings=approved.settings).place(approved.buyer,
        PlaceOrderRequest(listing_id=key,quantity='2',request_id=uuid.uuid4()))
    assert row['status']=='pending'


def test_safe_operator_reverse_membership_is_not_runtime_elevation(store):
    with store.admin.begin() as db:
        db.exec_driver_sql(f'GRANT {ROLE} TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE')
    try:
        with store.admin.begin() as db: provision(db)
        with store.runtime.connect() as db:
            assert not db.scalar(sa.text("SELECT pg_has_role(current_user,'postgres','MEMBER')"))
    finally:
        with store.admin.begin() as db: db.exec_driver_sql(f'REVOKE {ROLE} FROM postgres')
