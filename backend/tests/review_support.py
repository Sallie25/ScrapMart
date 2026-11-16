"""Trusted offline evidence/reviewer setup using the real review lifecycle."""
import io
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from PIL import Image
import sqlalchemy as sa
from sqlalchemy.orm import Session
from app.modules.auth.models import User
from app.modules.auth.phone_models import PhoneVerification
from app.modules.auth.security import create_access_token, verify_access_token
from app.modules.auth.session_service import SessionService
from app.modules.vendors.models import Vendor
from app.modules.vendors.review_models import VerificationReviewer, VerificationReviewAudit
from app.modules.vendors.reviewer_provisioning import provision_reviewer
from app.modules.vendors.review_service import VerificationReviewService


class ReviewStorage:
    def __init__(self): self.objects={}
    def exists(self,key): return key in self.objects
    def read(self,key): return self.objects[key]
    def delete(self,key): self.objects.pop(key,None)
    def put(self,key,data): self.objects[key]=data


def prepare_case(store,claims,monkeypatch,*,approve=False):
    VerificationReviewer.__table__.create(store.engine,checkfirst=True)
    VerificationReviewAudit.__table__.create(store.engine,checkfirst=True)
    PhoneVerification.__table__.create(store.engine,checkfirst=True)
    storage=ReviewStorage()
    output=io.BytesIO(); Image.new('RGB',(10,10),'white').save(output,format='JPEG')
    key='a'*64; storage.objects[key]=output.getvalue()
    now=datetime.now(timezone.utc)
    reviewer_id=uuid.uuid4()
    with Session(store.engine) as db,db.begin():
        user=db.get(User,claims.user_id); user.phone_number='+2348012345678'
        vendor=db.scalar(sa.select(Vendor).where(Vendor.user_id==claims.user_id))
        vendor.business_name='Shop'; vendor.shop_location='Lagos'; vendor.shop_address='Private address'
        vendor.identification_type='passport'; vendor.identity_document_key=key
        vendor.identity_document_status='submitted'; vendor.identity_document_submitted_at=now
        vendor.verification_status='pending'
        vendor_id=vendor.id
        proof=db.get(PhoneVerification,claims.user_id)
        if proof is None:
            proof=PhoneVerification(user_id=claims.user_id); db.add(proof)
        proof.phone_number=user.phone_number; proof.verified_at=now; proof.code_digest=None; proof.nonce=uuid.uuid4()
        db.add(User(id=reviewer_id,email=f'{reviewer_id.hex}@example.test',password_hash='test-only-no-login',full_name='Reviewer',role='buyer'))
    provision_reviewer(store.engine,reviewer_id,'isolated-test-ticket')
    credentials=SessionService(store.engine,settings=store.settings).create_session(reviewer_id)
    access=create_access_token(reviewer_id,credentials.session_id,settings=store.settings)
    reviewer=verify_access_token(access,settings=store.settings)
    service=VerificationReviewService(store.engine,settings=store.settings,storage=storage)
    service.submit_for_review(claims)
    case=service.get_case(reviewer,vendor_id)
    if approve:
        service.decide(reviewer,case.vendor_id,'approve',case.case_version,case.evidence_revision,'Evidence reviewed')
    monkeypatch.setattr('app.modules.vendors.evidence.get_private_document_storage',lambda settings:storage)
    return SimpleNamespace(storage=storage,reviewer=reviewer,reviewer_access=access,
                           owner=claims,vendor_id=case.vendor_id,service=service,case=case)
