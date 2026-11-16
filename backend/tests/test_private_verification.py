"""Isolated document/SMS doubles; no live storage, SMS, PostgreSQL or Redis."""
import base64
import importlib.util
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from PIL import Image
from pydantic import SecretStr

from app.api.v1.verification import phone_limit as actual_phone_limit
from app.modules.auth.phone_models import PhoneVerification
from app.modules.auth.phone_service import PhoneVerificationService, PhoneRateLimited, phone_is_verified
from app.modules.auth.models import User
from app.modules.auth.session_service import SessionPersistenceError
from app.modules.vendors.models import Vendor
from app.modules.vendors.document_service import VendorDocumentService, IdentificationType
from app.modules.vendors.onboarding_service import VendorOnboardingService
from app.infrastructure.storage.private_documents import (
    MAX_DOCUMENT_BYTES, VerificationInfrastructureUnavailable, DurableVolumeDocumentStorage,
    get_private_document_storage, sanitize_document, InvalidDocument,
)
from tests.test_vendor_onboarding import store as onboarding_store, account_store, login_store, http_store, encoded_password
from tests.test_vendor_account import issue, get, ME
from tests.test_buyer_login_http import HEADERS

DOCUMENT='/api/v1/auth/vendor/identity-document'
SEND='/api/v1/auth/phone/send-code'
VERIFY='/api/v1/auth/phone/verify-code'


class MemoryStorage:
    def __init__(self): self.objects={}
    def put(self,key,content):
        assert len(key)==64 and key not in self.objects
        self.objects[key]=content
    def exists(self,key): return key in self.objects
    def delete(self,key): self.objects.pop(key,None)


class CapturingSms:
    def __init__(self): self.messages=[]
    def send_code(self,phone_number,code,*,idempotency_key): self.messages.append((phone_number,code,idempotency_key))


def migration():
    path=Path(__file__).parents[1]/'alembic/versions/e84b6d0123fa_add_private_id_and_phone_verification.py'
    spec=importlib.util.spec_from_file_location('private_verification_migration',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def store(onboarding_store,monkeypatch):
    monkeypatch.setattr('app.api.v1.verification.get_engine',lambda:onboarding_store.engine)
    onboarding_store.storage=MemoryStorage()
    onboarding_store.sms=CapturingSms()
    onboarding_store.settings.phone_otp_secret=SecretStr(base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip('='))
    monkeypatch.setattr('app.api.v1.verification.get_private_document_storage',lambda settings:onboarding_store.storage)
    monkeypatch.setattr('app.api.v1.verification.get_sms_delivery',lambda:onboarding_store.sms)
    monkeypatch.setattr('app.api.v1.verification.phone_limit',lambda *args,**kwargs:None)
    with onboarding_store.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration().install_phone_change_trigger()
    return onboarding_store


def image_bytes(format='PNG'):
    output=io.BytesIO(); Image.new('RGB',(20,20),'white').save(output,format=format)
    return output.getvalue()


def upload(store,token,content=None,kind='national_id',**kwargs):
    return store.client.post(DOCUMENT,params={'identification_type':kind},
        content=image_bytes() if content is None else content,
        headers={**HEADERS,'Authorization':'Bearer '+token,'Content-Type':'image/png'},**kwargs)


def phone_request(store,path,token,body=None):
    return store.client.post(path,json={} if body is None else body,headers={**HEADERS,'Authorization':'Bearer '+token})


def set_phone(store,user_id,phone='+2348012345678'):
    with Session(store.engine) as db,db.begin(): db.get(User,user_id).phone_number=phone


def phone_service(store,clock=None,engine=None):
    return PhoneVerificationService(engine or store.engine,settings=store.settings,clock=clock)


@pytest.mark.parametrize('kind',[v.value for v in IdentificationType])
def test_document_private_metadata_no_approval(store,kind,caplog):
    token,claims=issue(store,'missing')
    response=upload(store,token,kind=kind)
    assert response.status_code==202 and set(response.json())=={'message'}
    assert response.headers['cache-control']=='no-store'
    with Session(store.engine) as db:
        row=db.scalar(sa.select(Vendor).where(Vendor.user_id==claims.user_id))
        assert row.identification_type==kind and row.identity_document_status=='submitted'
        assert row.identity_document_submitted_at is not None and row.verification_status=='pending'
        key=row.identity_document_key
    assert key in store.storage.objects and key not in response.text+caplog.text
    assert 'identity_document' not in get(store,ME,token).text
    assert store.client.get('/media/'+key).status_code==404
    with Image.open(io.BytesIO(store.storage.objects[key])) as image: assert image.format=='JPEG'


@pytest.mark.parametrize('state',['buyer_only','approved','suspended'])
def test_document_restrictions(store,state):
    token,claims=issue(store,'legacy' if state=='buyer_only' else 'buyer')
    if state!='buyer_only':
        with Session(store.engine) as db,db.begin():
            db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status=state))
    assert upload(store,token).status_code==403
    assert not store.storage.objects


@pytest.mark.parametrize('content',[b'<svg/>', b'%PDF-1.4 fake', b'\x89PNG\r\n\x1a\ncorrupt', b'', image_bytes('GIF')])
def test_content_validation_not_mime(store,content):
    token,_=issue(store)
    assert upload(store,token,content).status_code==422
    assert not store.storage.objects


def test_limits_injection_and_origin(store):
    token,_=issue(store)
    assert upload(store,token,b'x'*(MAX_DOCUMENT_BYTES+1)).status_code==413
    assert upload(store,token,kind='approved').status_code==422
    response=store.client.post(DOCUMENT+'?identification_type=passport&verification_status=approved',content=image_bytes(),headers={**HEADERS,'Authorization':'Bearer '+token,'Content-Type':'image/png'})
    assert response.status_code==422
    assert store.client.post(DOCUMENT,content=image_bytes()).status_code==403
    assert not store.storage.objects


def test_document_replacement_and_failures(store,monkeypatch):
    token,claims=issue(store)
    assert upload(store,token).status_code==202
    old=set(store.storage.objects)
    assert upload(store,token).status_code==202
    assert len(store.storage.objects)==1 and old.isdisjoint(store.storage.objects)
    old=set(store.storage.objects)
    def fail(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE vendors'): raise sa.exc.SQLAlchemyError('private database detail')
    sa.event.listen(store.engine,'before_cursor_execute',fail)
    try: response=upload(store,token)
    finally: sa.event.remove(store.engine,'before_cursor_execute',fail)
    assert response.status_code==503 and set(store.storage.objects)==old
    monkeypatch.setattr(store.storage,'put',Mock(side_effect=VerificationInfrastructureUnavailable()))
    assert upload(store,token).status_code==503
    assert set(store.storage.objects)==old


def test_default_provider_configuration_fails_closed(store,monkeypatch):
    from app.infrastructure.sms import get_sms_delivery
    token,claims=issue(store); set_phone(store,claims.user_id)
    monkeypatch.setattr('app.api.v1.verification.get_private_document_storage',get_private_document_storage)
    assert upload(store,token).status_code==503
    monkeypatch.setattr('app.api.v1.verification.get_sms_delivery',get_sms_delivery)
    assert phone_request(store,SEND,token).status_code==503
    with Session(store.engine) as db: assert db.get(PhoneVerification,claims.user_id) is None


@pytest.mark.parametrize('name',['buyer','missing','legacy'])
def test_shared_otp_digest_one_time_and_no_echo(store,name,caplog):
    token,claims=issue(store,name); set_phone(store,claims.user_id)
    response=phone_request(store,SEND,token)
    assert response.status_code==202
    phone,code,_=store.sms.messages[-1]
    assert len(code)==6 and code.isascii() and code.isdigit()
    assert code not in response.text+caplog.text
    with Session(store.engine) as db:
        row=db.get(PhoneVerification,claims.user_id)
        assert len(row.code_digest)==32 and row.code_digest!=code.encode() and row.verified_at is None
    assert phone_request(store,VERIFY,token,{'code':code}).status_code==204
    assert phone_request(store,VERIFY,token,{'code':code}).status_code==400
    with Session(store.engine) as db:
        assert phone_is_verified(db,claims.user_id,phone)
        assert db.get(PhoneVerification,claims.user_id).code_digest is None


def test_wrong_attempts_commit_and_lockout(store):
    token,claims=issue(store); set_phone(store,claims.user_id)
    phone_request(store,SEND,token)
    code=store.sms.messages[-1][1]
    wrong='000000' if code!='000000' else '111111'
    for _ in range(5): assert phone_request(store,VERIFY,token,{'code':wrong}).status_code==400
    assert phone_request(store,VERIFY,token,{'code':code}).status_code==400
    with Session(store.engine) as db:
        row=db.get(PhoneVerification,claims.user_id)
        assert row.attempts==5 and row.verified_at is None and row.code_digest is None


def test_expiry_cooldown_resend_and_hour_budget(store):
    token,claims=issue(store); set_phone(store,claims.user_id)
    now=datetime.now(timezone.utc)
    svc=phone_service(store,clock=lambda:now)
    svc.send_code(claims,store.sms,store.settings)
    first=store.sms.messages[-1][1]
    with pytest.raises(PhoneRateLimited): svc.send_code(claims,store.sms,store.settings)
    assert not phone_service(store,clock=lambda:now+timedelta(seconds=301)).verify_code(claims,first,store.settings)
    for i in range(1,6): phone_service(store,clock=lambda i=i:now+timedelta(seconds=61*i)).send_code(claims,store.sms,store.settings)
    with pytest.raises(PhoneRateLimited):
        phone_service(store,clock=lambda:now+timedelta(seconds=61*6)).send_code(claims,store.sms,store.settings)
    assert not phone_service(store,clock=lambda:now+timedelta(seconds=61*5+1)).verify_code(claims,first,store.settings)


def test_phone_change_even_away_and_back_invalidates(store):
    token,claims=issue(store); set_phone(store,claims.user_id)
    phone_request(store,SEND,token); code=store.sms.messages[-1][1]
    assert phone_request(store,VERIFY,token,{'code':code}).status_code==204
    set_phone(store,claims.user_id,'+2348099999999'); set_phone(store,claims.user_id)
    with Session(store.engine) as db:
        assert not phone_is_verified(db,claims.user_id,'+2348012345678')
        assert db.get(PhoneVerification,claims.user_id).verified_at is None
    assert phone_request(store,VERIFY,token,{'code':code}).status_code==400


def test_concurrent_code_consumption(store):
    _,claims=issue(store); set_phone(store,claims.user_id)
    phone_service(store).send_code(claims,store.sms,store.settings)
    code=store.sms.messages[-1][1]
    engine=sa.create_engine(store.engine.url,connect_args={'check_same_thread':False,'timeout':10})
    barrier=threading.Barrier(2)
    def wait(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE users'): barrier.wait(timeout=10)
    sa.event.listen(engine,'before_cursor_execute',wait)
    try:
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(phone_service(store,engine=engine).verify_code,claims,code,store.settings) for _ in range(2)]
            assert sorted(f.result(timeout=30) for f in futures)==[False,True]
    finally:
        sa.event.remove(engine,'before_cursor_execute',wait); engine.dispose()


def test_delivery_and_database_failures_never_verify(store):
    token,claims=issue(store); set_phone(store,claims.user_id)
    delivery=Mock(send_code=Mock(side_effect=RuntimeError('private provider error')))
    with pytest.raises(VerificationInfrastructureUnavailable): phone_service(store).send_code(claims,delivery,store.settings)
    with Session(store.engine) as db:
        row=db.get(PhoneVerification,claims.user_id)
        assert row.verified_at is None and row.code_digest is None
    # A database failure before commit must not send any SMS.
    def fail(connection): raise sa.exc.SQLAlchemyError('private commit error')
    sa.event.listen(store.engine,'commit',fail)
    before=len(store.sms.messages)
    try:
        with pytest.raises(SessionPersistenceError):
            phone_service(store,clock=lambda:datetime.now(timezone.utc)+timedelta(seconds=61)).send_code(claims,store.sms,store.settings)
    finally: sa.event.remove(store.engine,'commit',fail)
    assert len(store.sms.messages)==before


def test_readiness_requires_actual_private_document_and_current_phone(store):
    token,claims=issue(store)
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(shop_location='Ikeja',shop_address='Private address'))
    set_phone(store,claims.user_id)
    assert upload(store,token).status_code==202
    svc=VendorOnboardingService(store.engine,settings=store.settings)
    ready=svc.get_verification_readiness(claims,storage=store.storage)
    assert not ready.can_submit and ready.outstanding_requirements==('verified_phone_ownership',)
    phone_request(store,SEND,token)
    phone_request(store,VERIFY,token,{'code':store.sms.messages[-1][1]})
    assert svc.get_verification_readiness(claims,storage=store.storage).can_submit
    svc.require_verification_submission(claims,storage=store.storage)
    with Session(store.engine) as db:
        assert db.scalar(sa.select(Vendor.verification_status).where(Vendor.user_id==claims.user_id))=='pending'
    store.storage.objects.clear()
    assert not svc.get_verification_readiness(claims,storage=store.storage).can_submit


def test_otp_validation_guards_and_account_binding(store):
    token,claims=issue(store); set_phone(store,claims.user_id)
    phone_request(store,SEND,token); code=store.sms.messages[-1][1]
    other,other_claims=issue(store,'missing'); set_phone(store,other_claims.user_id)
    assert phone_request(store,VERIFY,other,{'code':code}).status_code==400
    assert phone_request(store,VERIFY,token,{'code':'not-a-code'}).status_code==422
    assert phone_request(store,SEND,token,{'phone_number':'+2348000000000'}).status_code==422
    assert store.client.post(SEND,json={}).status_code==403
    assert store.client.post(VERIFY,content='x'*16385,headers=HEADERS).status_code==413


def test_metadata_stripping_and_volume_configuration(tmp_path):
    encoded=sanitize_document(image_bytes()+b'<script>private payload</script>')
    assert b'<script>' not in encoded
    with pytest.raises(VerificationInfrastructureUnavailable): DurableVolumeDocumentStorage(str(tmp_path))
    # Exercise fd permissions/opaque keys on an isolated directory, explicitly
    # bypassing the production constructor's rejection of temporary storage.
    root=tmp_path/'objects'; root.mkdir(mode=0o700)
    storage=DurableVolumeDocumentStorage.__new__(DurableVolumeDocumentStorage); storage._root=root
    key='a'*64; storage.put(key,encoded)
    assert storage.exists(key) and (root/key).stat().st_mode & 0o777==0o600
    assert storage.read(key).startswith(b'\xff\xd8')
    with pytest.raises(VerificationInfrastructureUnavailable): storage.read('../escape')
    with pytest.raises(VerificationInfrastructureUnavailable): storage.put('../escape',encoded)
    storage.delete(key); assert not storage.exists(key)


def test_migration_offline_and_phone_change_trigger():
    output=io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})):
        migration().upgrade(); migration().downgrade()
    sql=output.getvalue()
    assert 'phone_verifications' in sql and 'IS DISTINCT FROM' in sql
    assert 'code_digest BYTEA' in sql and 'ck_vendor_identity_document' in sql
    assert 'SET search_path = pg_catalog' in sql
    assert migration().down_revision=='d73a5c9012ef'


def test_document_admission_rechecks_status_after_storage(store,monkeypatch):
    token,claims=issue(store)
    original=store.storage.put
    def changed(key,content):
        original(key,content)
        with Session(store.engine) as db,db.begin():
            db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status='approved'))
    monkeypatch.setattr(store.storage,'put',changed)
    assert upload(store,token).status_code==403
    assert not store.storage.objects
    with Session(store.engine) as db:
        vendor=db.scalar(sa.select(Vendor).where(Vendor.user_id==claims.user_id))
        assert vendor.identity_document_key is None and vendor.verification_status=='approved'


def test_rejected_upload_preserves_status_and_phone_guard_denies_revoked_session(store):
    token,claims=issue(store)
    with Session(store.engine) as db,db.begin():
        db.execute(sa.update(Vendor).where(Vendor.user_id==claims.user_id).values(verification_status='rejected'))
    assert upload(store,token).status_code==202
    assert get(store,ME,token).json()['verification_status']=='rejected'
    from app.modules.auth.session_models import AuthSession
    with Session(store.engine) as db,db.begin():
        db.get(AuthSession,claims.session_id).revoked_at=datetime.now(timezone.utc)
    before=len(store.sms.messages)
    assert phone_request(store,SEND,token).status_code==401
    assert phone_request(store,VERIFY,token,{'code':'000000'}).status_code==401
    assert len(store.sms.messages)==before


def test_redis_phone_limit_is_fail_closed(store,monkeypatch):
    from app.modules.auth.signup_rate_limit import SignupRateLimitedError,RateLimitUnavailableError
    token,claims=issue(store); set_phone(store,claims.user_id)
    monkeypatch.setattr('app.api.v1.verification.phone_limit',actual_phone_limit)
    for error,status in ((SignupRateLimitedError(60),429),(RateLimitUnavailableError(),503)):
        monkeypatch.setattr('app.api.v1.verification.configured_rate_limiter',lambda *args:Mock(check=Mock(side_effect=error)))
        response=phone_request(store,SEND,token)
        assert response.status_code==status
    assert not store.sms.messages


def test_migration_preserves_historical_vendor_and_installs_phone_invalidation():
    engine=sa.create_engine('sqlite://')
    User.__table__.create(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE vendors (id CHAR(32) PRIMARY KEY, user_id CHAR(32), business_name VARCHAR(200), shop_location VARCHAR(200), shop_address VARCHAR(500), verification_status VARCHAR(20))')
        import uuid
        user_id=uuid.uuid4()
        connection.execute(User.__table__.insert().values(id=user_id,email='historical@example.test',password_hash='test-only',full_name='Historical',phone_number='+2348012345678'))
        connection.exec_driver_sql("INSERT INTO vendors VALUES ('vendor', ?, 'Existing shop', 'Lagos', 'Private address', 'approved')",(user_id.hex,))
        before=connection.exec_driver_sql('SELECT * FROM vendors').one()
        with Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()
            after=connection.exec_driver_sql('SELECT * FROM vendors').one()
            assert after[:6]==before and after[6:]==(None,None,None,None)
            assert connection.exec_driver_sql('SELECT count(*) FROM phone_verifications').scalar()==0
            connection.execute(PhoneVerification.__table__.insert().values(user_id=user_id,phone_number='+2348012345678',verified_at=datetime.now(timezone.utc)))
            connection.execute(sa.update(User).where(User.id==user_id).values(phone_number='+2348099999999'))
            assert connection.exec_driver_sql('SELECT verified_at, phone_number FROM phone_verifications').one()==(None,None)
            migration().downgrade()
            assert connection.exec_driver_sql('SELECT * FROM vendors').one()==before
    engine.dispose()
