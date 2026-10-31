"""Offline reviewer permissions, immutable audit and revision-bound decisions."""
import importlib.util
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.modules.auth.models import User
from app.modules.auth.phone_models import PhoneVerification
from app.modules.auth.session_models import AuthSession
from app.modules.auth.session_service import SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.vendors.models import Vendor
from app.modules.vendors.review_models import VerificationReviewer, VerificationReviewAudit as Audit
from app.modules.vendors.reviewer_provisioning import provision_reviewer
from app.modules.vendors.review_service import VerificationReviewService, ReviewConflict
from tests.test_private_verification import store as private_store, onboarding_store, account_store, login_store, http_store, encoded_password
from tests.test_vendor_account import issue, service as selling_service, get, ME
from tests.test_buyer_login_http import HEADERS
from tests.review_support import prepare_case

ROOT='/api/v1/auth/verification/cases'
SUBMIT='/api/v1/auth/vendor/verification/submit'


def migration():
    path=Path(__file__).parents[1]/'alembic/versions/f95c7e1234ab_add_verification_review.py'
    spec=importlib.util.spec_from_file_location('review_migration',path)
    result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


@pytest.fixture
def store(private_store,monkeypatch):
    token,claims=issue(private_store)
    case=prepare_case(private_store,claims,monkeypatch)
    private_store.owner_access=token
    private_store.review=case
    private_store.storage=case.storage
    monkeypatch.setattr('app.api.v1.verification_review.get_engine',lambda:private_store.engine)
    monkeypatch.setattr('app.modules.vendors.review_service.get_private_document_storage',lambda settings:case.storage)
    with private_store.engine.begin() as connection,Operations.context(MigrationContext.configure(connection)):
        migration().install_audit_guard()
    return private_store


def read(store,path='',token=None):
    return store.client.get(ROOT+path,headers={'Authorization':'Bearer '+(store.review.reviewer_access if token is None else token)})


def decide(store,action,body=None,token=None):
    case=store.review.service.get_case(store.review.reviewer,store.review.vendor_id)
    data={'expected_version':case.case_version,'expected_evidence_revision':case.evidence_revision,'reason':'Reviewed evidence'} if body is None else body
    return store.client.post(ROOT+f'/{case.vendor_id}/{action}',json=data,
                             headers={**HEADERS,'Authorization':'Bearer '+(store.review.reviewer_access if token is None else token)})


def approved(store):
    response=decide(store,'approve'); assert response.status_code==200
    return response


def count_audit(store):
    with Session(store.engine) as db: return db.scalar(sa.select(sa.func.count()).select_from(Audit))


@pytest.mark.parametrize('role',['buyer','vendor','admin'])
def test_roles_without_permission_cannot_review(store,role):
    token,claims=issue(store,'missing')
    with Session(store.engine) as db,db.begin(): db.get(User,claims.user_id).role=role
    assert read(store,token=token).status_code==403
    assert read(store,f'/{store.review.vendor_id}',token).status_code==403
    assert read(store,f'/{store.review.vendor_id}/document',token).status_code==403
    assert decide(store,'approve',token=token).status_code==403
    assert count_audit(store)==1


def test_permission_revocation_provisioning_and_active_session(store):
    reviewer=store.review.reviewer
    provision_reviewer(store.engine,reviewer.user_id,'test-revoke',revoke=True)
    assert read(store).status_code==403
    provision_reviewer(store.engine,reviewer.user_id,'test-regrant')
    assert read(store).status_code==200
    with Session(store.engine) as db,db.begin(): db.get(User,reviewer.user_id).is_active=False
    assert read(store).status_code==401
    # Revocation is still possible after deactivation, with trusted credentials.
    provision_reviewer(store.engine,reviewer.user_id,'revoke-inactive',revoke=True)
    assert read(store,token='invalid').status_code==401
    assert store.client.post('/api/v1/auth/reviewer/signup',json={}).status_code==404


def test_self_review_is_denied_for_explicit_reviewer(store):
    provision_reviewer(store.engine,store.review.owner.user_id,'test-owner-grant')
    token=store.owner_access
    assert read(store,token=token).json()=={'cases':[]}
    assert read(store,f'/{store.review.vendor_id}',token).status_code==403
    assert read(store,f'/{store.review.vendor_id}/document',token).status_code==403
    assert decide(store,'approve',token=token).status_code==403


def test_private_document_access_is_bound_to_case_and_never_exposes_key(store,caplog):
    response=read(store,f'/{store.review.vendor_id}/document')
    assert response.status_code==200
    from app.infrastructure.storage.private_documents import sanitize_document
    assert response.content==sanitize_document(store.storage.read('a'*64))
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-content-type-options']=='nosniff'
    assert 'attachment' in response.headers['content-disposition']
    case=read(store,f'/{store.review.vendor_id}')
    assert case.status_code==200 and 'identity_document_key' not in case.text
    assert 'a'*64 not in case.text+caplog.text
    assert read(store,'/../document').status_code in (404,422)
    assert read(store,'/'+'a'*64+'/document').status_code==422
    assert store.client.get(ROOT+f'/{store.review.vendor_id}/document').status_code==401


def test_complete_approval_and_suspension_keep_buyer_access(store):
    assert read(store).json()['cases'][0]['vendor_id']==str(store.review.vendor_id)
    approved(store)
    identity=selling_service(store).require_approved_vendor(store.review.owner)
    assert identity.vendor_id==store.review.vendor_id
    assert decide(store,'suspend').status_code==200
    with pytest.raises(VendorPermissionError): selling_service(store).require_approved_vendor(store.review.owner)
    assert get(store,ME,store.owner_access).status_code==200
    assert get(store,'/api/v1/auth/me',store.owner_access).status_code==200
    assert decide(store,'reopen').status_code==200
    # Reopened cases must be explicitly submitted again, not directly approved.
    assert decide(store,'approve').status_code==409
    response=store.client.post(SUBMIT,json={},headers={**HEADERS,'Authorization':'Bearer '+store.owner_access})
    assert response.status_code==202
    assert decide(store,'approve').status_code==200
    history=read(store,f'/{store.review.vendor_id}/history').json()['history']
    assert [r['action'] for r in history]==['submit','approve','suspend','reopen','submit','approve']
    assert all(r['reviewer_id']==str(store.review.reviewer.user_id) for r in history if r['action']!='submit')


def test_rejection_reason_resubmission_and_invalid_transitions(store):
    assert decide(store,'suspend').status_code==409
    assert decide(store,'reject').status_code==200
    assert decide(store,'approve').status_code==409
    assert decide(store,'reopen').status_code==409
    response=store.client.post(SUBMIT,json={},headers={**HEADERS,'Authorization':'Bearer '+store.owner_access})
    assert response.status_code==202 and response.json()['status']=='pending'
    assert decide(store,'approve').status_code==200
    assert decide(store,'reject').status_code==409
    history=read(store,f'/{store.review.vendor_id}/history').json()['history']
    assert history[1]['reason']=='Reviewed evidence'


@pytest.mark.parametrize('missing',['shop','phone','document','document_metadata','active_user'])
def test_incomplete_or_changed_evidence_cannot_be_approved(store,missing):
    with Session(store.engine) as db,db.begin():
        if missing=='shop': db.get(Vendor,store.review.vendor_id).shop_address=None
        if missing=='phone': db.get(PhoneVerification,store.review.owner.user_id).verified_at=None
        if missing=='document_metadata':
            vendor=db.get(Vendor,store.review.vendor_id)
            vendor.identification_type=vendor.identity_document_key=vendor.identity_document_status=vendor.identity_document_submitted_at=None
        if missing=='active_user': db.get(User,store.review.owner.user_id).is_active=False
    if missing=='document': store.storage.objects.clear()
    assert decide(store,'approve').status_code==409
    with Session(store.engine) as db: assert db.get(Vendor,store.review.vendor_id).verification_status=='pending'
    assert count_audit(store)==1


def test_stale_case_version_and_evidence_revision_are_rejected(store):
    case=store.review.case
    stale={'expected_version':case.case_version,'expected_evidence_revision':case.evidence_revision,'reason':'Old decision'}
    assert decide(store,'reject').status_code==200
    assert decide(store,'approve',stale).status_code==409
    store.client.post(SUBMIT,json={},headers={**HEADERS,'Authorization':'Bearer '+store.owner_access})
    with Session(store.engine) as db,db.begin(): db.get(Vendor,case.vendor_id).shop_location='Changed'
    assert decide(store,'approve',stale).status_code==409
    # Even a current case read cannot approve evidence changed since submission.
    assert decide(store,'approve').status_code==409


@pytest.mark.parametrize('invalid',['phone','shop','document','name','legacy_status'])
def test_approved_status_is_not_a_stale_selling_grant(store,invalid):
    approved(store)
    selling_service(store).require_approved_vendor(store.review.owner)
    with Session(store.engine) as db,db.begin():
        if invalid=='phone': db.get(User,store.review.owner.user_id).phone_number='+2348099999999'
        if invalid=='shop': db.get(Vendor,store.review.vendor_id).business_name='Changed'
        if invalid=='name': db.get(User,store.review.owner.user_id).full_name='Changed'
        if invalid=='legacy_status': db.get(Vendor,store.review.vendor_id).approval_review_id=None
    if invalid=='document': store.storage.objects.clear()
    with pytest.raises(VendorPermissionError): selling_service(store).require_approved_vendor(store.review.owner)
    callback=Mock()
    with pytest.raises(VendorPermissionError): selling_service(store).run_approved_vendor_operation(store.review.owner,callback)
    callback.assert_not_called()
    assert get(store,'/api/v1/auth/me',store.owner_access).status_code==200


@pytest.mark.parametrize('failure',['audit_insert','commit'])
def test_audit_and_status_rollback_atomically(store,failure):
    def fail_sql(connection,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO verification_review_audit'): raise sa.exc.SQLAlchemyError('private audit detail')
    def fail_commit(connection): raise sa.exc.SQLAlchemyError('private commit detail')
    # Read request/version first, before installing the commit failure hook.
    body={'expected_version':store.review.case.case_version,'expected_evidence_revision':store.review.case.evidence_revision,'reason':'Review'}
    name='commit' if failure=='commit' else 'before_cursor_execute'; handler=fail_commit if failure=='commit' else fail_sql
    sa.event.listen(store.engine,name,handler)
    try:
        response=store.client.post(ROOT+f'/{store.review.vendor_id}/approve',json=body,headers={**HEADERS,'Authorization':'Bearer '+store.review.reviewer_access})
    finally: sa.event.remove(store.engine,name,handler)
    assert response.status_code==503 and 'private' not in response.text
    with Session(store.engine) as db:
        vendor=db.get(Vendor,store.review.vendor_id)
        assert vendor.verification_status=='pending' and vendor.approval_review_id is None
    assert count_audit(store)==1


def test_audit_database_guard_is_append_only(store):
    approved(store)
    for statement in (sa.update(Audit).values(reason='tampered'),sa.delete(Audit)):
        with pytest.raises(sa.exc.DBAPIError),store.engine.begin() as db: db.execute(statement)
    assert count_audit(store)==2


def test_concurrent_decisions_have_one_winner(store):
    engine=sa.create_engine(store.engine.url,connect_args={'check_same_thread':False,'timeout':10})
    barrier=threading.Barrier(2); local=threading.local()
    def sync(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE users') and not getattr(local,'started',False):
            local.started=True; barrier.wait(timeout=10)
    sa.event.listen(engine,'before_cursor_execute',sync)
    def decision(action):
        svc=VerificationReviewService(engine,settings=store.settings,storage=store.storage)
        try:
            svc.decide(store.review.reviewer,store.review.vendor_id,action,store.review.case.case_version,store.review.case.evidence_revision,'Concurrent review')
            return 'committed'
        except ReviewConflict: return 'conflict'
    try:
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(decision,['approve','reject']))
        assert sorted(results)==['committed','conflict']
    finally: sa.event.remove(engine,'before_cursor_execute',sync); engine.dispose()
    assert count_audit(store)==2


def test_guard_validation_storage_failure_and_no_owner_approval(store,monkeypatch):
    token=store.review.reviewer_access
    assert store.client.post(ROOT+f'/{store.review.vendor_id}/approve',json={}).status_code==403
    assert store.client.post(ROOT+f'/{store.review.vendor_id}/approve',content='x'*16385,headers=HEADERS).status_code==413
    data={'expected_version':1,'expected_evidence_revision':'0'*64,'reason':'test','reviewer_id':str(store.review.reviewer.user_id)}
    assert decide(store,'approve',data).status_code==422
    monkeypatch.setattr(store.storage,'read',Mock(side_effect=OSError('private storage detail')))
    response=read(store,f'/{store.review.vendor_id}/document')
    assert response.status_code==503 and 'private storage detail' not in response.text
    assert store.client.patch('/api/v1/auth/vendor/onboarding',json={'verification_status':'approved'},headers={**HEADERS,'Authorization':'Bearer '+store.owner_access}).status_code==422


def test_review_migration_offline_and_no_default_grants():
    output=io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})):
        migration().upgrade(); migration().downgrade()
    sql=output.getvalue()
    assert 'verification_reviewers' in sql and 'immutable_verification_review' in sql
    assert 'BEFORE UPDATE OR DELETE' in sql and 'case_version' in sql
    assert 'INSERT INTO' not in sql and 'UPDATE users' not in sql
    assert migration().down_revision=='e84b6d0123fa'


def test_owner_submission_is_complete_explicit_and_never_approval(store):
    with Session(store.engine) as db,db.begin():
        db.get(PhoneVerification,store.review.owner.user_id).verified_at=None
    response=store.client.post(SUBMIT,json={},headers={**HEADERS,'Authorization':'Bearer '+store.owner_access})
    assert response.status_code==409
    assert count_audit(store)==1
    with Session(store.engine) as db:
        assert db.get(Vendor,store.review.vendor_id).verification_status=='pending'
    assert store.client.post(SUBMIT,json={'verification_status':'approved'},headers={**HEADERS,'Authorization':'Bearer '+store.owner_access}).status_code==422


def test_selling_fails_closed_on_storage_configuration_loss(store,monkeypatch):
    from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable
    approved(store)
    monkeypatch.setattr('app.modules.vendors.evidence.get_private_document_storage',Mock(side_effect=VerificationInfrastructureUnavailable()))
    callback=Mock()
    with pytest.raises(VerificationInfrastructureUnavailable):
        selling_service(store).run_approved_vendor_operation(store.review.owner,callback)
    callback.assert_not_called()
    assert get(store,'/api/v1/auth/me',store.owner_access).status_code==200


def test_revoked_session_and_permission_cannot_reuse_viewed_case(store):
    reviewer=store.review.reviewer
    with Session(store.engine) as db,db.begin():
        from datetime import datetime,timezone
        db.get(AuthSession,reviewer.session_id).revoked_at=datetime.now(timezone.utc)
    assert read(store,f'/{store.review.vendor_id}/document').status_code==401
    response=store.client.post(ROOT+f'/{store.review.vendor_id}/approve',json={
        'expected_version':store.review.case.case_version,'expected_evidence_revision':store.review.case.evidence_revision,'reason':'Old case'},
        headers={**HEADERS,'Authorization':'Bearer '+store.review.reviewer_access})
    assert response.status_code==401 and count_audit(store)==1


def test_review_migration_roundtrip_preserves_existing_rows():
    engine=sa.create_engine('sqlite://')
    User.__table__.create(engine)
    import uuid
    user_id=uuid.uuid4()
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE vendors (id CHAR(32) PRIMARY KEY, user_id CHAR(32), business_name TEXT, verification_status TEXT)')
        connection.execute(User.__table__.insert().values(id=user_id,email='legacy-review@example.test',password_hash='test-only',full_name='Legacy'))
        connection.exec_driver_sql("INSERT INTO vendors VALUES ('vendor', ?, 'Existing', 'approved')",(user_id.hex,))
        before=connection.exec_driver_sql('SELECT * FROM vendors').one()
        with Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()
            after=connection.exec_driver_sql('SELECT * FROM vendors').one()
            assert after[:4]==before and after[4:]==(None,None,0,None)
            assert connection.exec_driver_sql('SELECT count(*) FROM verification_reviewers').scalar()==0
            assert connection.exec_driver_sql('SELECT count(*) FROM verification_review_audit').scalar()==0
            migration().downgrade()
            assert connection.exec_driver_sql('SELECT * FROM vendors').one()==before
    engine.dispose()


def test_private_audit_pagination_and_document_unavailability(store):
    approved(store)
    first=read(store,f'/{store.review.vendor_id}/history?limit=1').json()['history']
    assert len(first)==1 and first[0]['action']=='submit'
    second=read(store,f'/{store.review.vendor_id}/history?after=1&limit=1').json()['history']
    assert len(second)==1 and second[0]['action']=='approve'
    assert read(store,f'/{store.review.vendor_id}/history?limit=101').status_code==422
    store.storage.objects.clear()
    assert read(store,f'/{store.review.vendor_id}/document').status_code==503


@pytest.mark.parametrize('content',[b'corrupt private image',None])
def test_approved_document_content_is_bound_to_audit(store,content):
    approved(store)
    if content is None:
        from PIL import Image
        output=io.BytesIO(); Image.new('RGB',(10,10),'black').save(output,format='JPEG')
        content=output.getvalue()
    store.storage.objects['a'*64]=content
    with pytest.raises(VendorPermissionError): selling_service(store).require_approved_vendor(store.review.owner)
    callback=Mock()
    with pytest.raises(VendorPermissionError): selling_service(store).run_approved_vendor_operation(store.review.owner,callback)
    callback.assert_not_called()


def test_document_replacement_after_case_view_prevents_stale_approval(store):
    case=store.review.case
    from PIL import Image
    output=io.BytesIO(); Image.new('RGB',(10,10),'black').save(output,format='JPEG')
    store.storage.objects['a'*64]=output.getvalue()
    stale={'expected_version':case.case_version,'expected_evidence_revision':case.evidence_revision,'reason':'Old document view'}
    assert decide(store,'approve',stale).status_code==409
    # A new read also cannot approve a different object than the owner submitted.
    assert decide(store,'approve').status_code==409
    assert count_audit(store)==1
