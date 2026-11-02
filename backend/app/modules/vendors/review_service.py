"""Locked, revision-bound verification submission, restricted review and audit."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy import select
from app.core.config import get_settings
from app.infrastructure.storage.private_documents import get_private_document_storage, VerificationInfrastructureUnavailable, sanitize_document
from app.modules.auth.models import User
from app.modules.auth.session_service import SessionAuthenticationError, _utc
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError
from app.modules.vendors.models import Vendor
from app.modules.vendors.evidence import load_evidence, evidence_revision, evidence_complete, document_digest, review_revision
from app.modules.vendors.review_models import VerificationReviewer, VerificationReviewAudit as Audit


class ReviewConflict(ValueError):
    def __init__(self):
        super().__init__('Verification case changed or transition is not permitted')


class ReviewCaseNotFound(ValueError):
    pass


@dataclass(frozen=True)
class ReviewCase:
    vendor_id: uuid.UUID
    status: str
    case_version: int
    evidence_revision: str
    submitted_revision: str | None
    submitted_at: datetime | None
    business_name: str = field(repr=False)
    shop_location: str | None = field(repr=False)
    shop_address: str | None = field(repr=False)
    full_name: str = field(repr=False)
    email: str = field(repr=False)
    phone_number: str | None = field(repr=False)
    identification_type: str | None
    document_submitted_at: datetime | None
    phone_verified: bool
    document_available: bool


class VerificationReviewService(VendorAuthorizationService):
    def __init__(self, engine, *, settings=None, clock=None, storage=None):
        super().__init__(engine, settings=settings, clock=clock)
        self._storage_override = storage

    def _storage(self):
        return self._storage_override if self._storage_override is not None else get_private_document_storage(self._settings or get_settings())

    def _live(self, db, claims, session):
        now = self._now(db)
        self._active_session(db, session, now)
        if claims.expires_at <= now:
            raise SessionAuthenticationError()
        return now

    def _reviewer(self, db, claims, *, owner_id=None):
        # Multiple User rows always lock in UUID order before any session or
        # Vendor locks. Provisioning/revocation uses the same reviewer User lock.
        users = {}
        for user_id in sorted({claims.user_id} | ({owner_id} if owner_id else set()), key=lambda v:v.int):
            users[user_id] = self._lock_user(db, user_id)
        self._active_user(users[claims.user_id])
        session = self._lock_session(db, claims.user_id, claims.session_id)
        permission = db.get(VerificationReviewer, claims.user_id)
        self._live(db, claims, session)
        if permission is None or permission.revoked_at is not None:
            raise VendorPermissionError()
        if owner_id == claims.user_id:
            raise VendorPermissionError()
        return session, users

    def _case(self, db, claims, vendor_id):
        owner_id = db.scalar(select(Vendor.user_id).where(Vendor.id == vendor_id))
        session, users = self._reviewer(db, claims, owner_id=owner_id)
        if owner_id is None:
            raise ReviewCaseNotFound()
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id).with_for_update())
        self._live(db, claims, session)
        if vendor is None or vendor.user_id != owner_id:
            raise ReviewConflict()
        evidence = load_evidence(db, owner_id, vendor.id)
        return vendor, users[owner_id], session, evidence

    def _digest(self, vendor, *, required=False):
        if not vendor.identity_document_key:
            return None
        try:
            storage = self._storage()
            return document_digest(storage, vendor.identity_document_key) if storage.exists(vendor.identity_document_key) else None
        except (VerificationInfrastructureUnavailable, OSError):
            if required:
                raise VerificationInfrastructureUnavailable() from None
            return None

    def _dto(self, db, vendor, user, evidence):
        from app.modules.auth.phone_service import current_phone
        digest = self._digest(vendor)
        return ReviewCase(vendor.id, vendor.verification_status, vendor.review_version,
                          review_revision(evidence, digest), vendor.verification_submission_revision,
                          _utc(vendor.verification_submitted_at, db) if vendor.verification_submitted_at else None, vendor.business_name,
                          vendor.shop_location, vendor.shop_address, user.full_name, user.email,
                          user.phone_number, vendor.identification_type,
                          _utc(vendor.identity_document_submitted_at, db) if vendor.identity_document_submitted_at else None,
                          bool(evidence.verified_at and current_phone(user.phone_number) and evidence.proof_phone == user.phone_number), digest is not None)

    @staticmethod
    def _record(db, vendor, actor, action, previous, revision, now, reason):
        vendor.review_version += 1
        audit = Audit(id=uuid.uuid4(), vendor_id=vendor.id, actor_user_id=actor,
                      reviewer_id=None if action == 'submit' else actor, action=action,
                      evidence_revision=revision, case_version=vendor.review_version,
                      previous_status=previous, new_status=vendor.verification_status,
                      decided_at=now, reason=reason)
        db.add(audit)
        db.flush()
        return audit

    def submit_for_review(self, claims):
        self._claims(claims)
        def operation(db):
            user = self._lock_user(db, claims.user_id)
            self._active_user(user)
            session = self._lock_session(db, claims.user_id, claims.session_id)
            vendor = db.scalar(select(Vendor).where(Vendor.user_id == user.id).with_for_update())
            self._live(db, claims, session)
            self._require_profile(None if vendor is None else vendor.id, None if vendor is None else vendor.verification_status)
            if vendor.verification_status not in {'pending','rejected'}:
                raise VendorPermissionError()
            evidence = load_evidence(db, user.id, vendor.id)
            if not evidence_complete(evidence, self._storage()):
                raise ReviewConflict()
            now = self._live(db, claims, session)
            digest = self._digest(vendor, required=True)
            if digest is None:
                raise ReviewConflict()
            revision = review_revision(evidence, digest)
            if vendor.verification_status == 'pending' and vendor.verification_submission_revision == revision:
                return vendor.review_version
            previous = vendor.verification_status
            vendor.verification_status, vendor.approval_review_id = 'pending', None
            vendor.verification_submission_revision, vendor.verification_submitted_at = revision, now
            self._record(db, vendor, user.id, 'submit', previous, revision, now, 'Vendor submitted verification')
            return vendor.review_version
        return self._transaction(operation)

    def list_cases(self, claims, *, status='pending', after=None, limit=25):
        self._claims(claims)
        if status not in {'pending','approved','rejected','suspended'} or not 1 <= limit <= 100:
            raise ValueError('Invalid case filter')
        def operation(db):
            session, _ = self._reviewer(db, claims)
            query = select(Vendor.id, Vendor.verification_status, Vendor.review_version,
                           Vendor.verification_submitted_at).where(
                Vendor.verification_submission_revision.is_not(None),
                Vendor.verification_status == status, Vendor.user_id != claims.user_id,
            ).order_by(Vendor.id).limit(limit)
            if after:
                query = query.where(Vendor.id > after)
            rows = db.execute(query).all()
            self._live(db, claims, session)
            return [{'vendor_id':r.id, 'status':r.verification_status, 'case_version':r.review_version,
                     'submitted_at':_utc(r.verification_submitted_at, db)} for r in rows]
        return self._transaction(operation)

    def get_case(self, claims, vendor_id):
        self._claims(claims)
        def operation(db):
            vendor, user, session, evidence = self._case(db, claims, vendor_id)
            result = self._dto(db, vendor, user, evidence)
            self._live(db, claims, session)
            return result
        return self._transaction(operation)

    def get_document(self, claims, vendor_id):
        self._claims(claims)
        def operation(db):
            vendor, user, session, evidence = self._case(db, claims, vendor_id)
            if not vendor.identity_document_key or vendor.identity_document_status != 'submitted':
                raise ReviewCaseNotFound()
            # Idempotent read under case locks; no caller-selected storage key.
            try:
                content = sanitize_document(self._storage().read(vendor.identity_document_key))
            except Exception:
                raise VerificationInfrastructureUnavailable() from None
            self._live(db, claims, session)
            return content
        return self._transaction(operation)

    def decide(self, claims, vendor_id, action, expected_version, expected_evidence_revision, reason):
        self._claims(claims)
        if action not in {'approve','reject','suspend','reopen'} or not isinstance(reason,str) or not reason.strip() or len(reason)>500:
            raise ValueError('Invalid review decision')
        transitions = {'approve':('pending','approved'), 'reject':('pending','rejected'),
                       'suspend':('approved','suspended'), 'reopen':('suspended','pending')}
        def operation(db):
            vendor, user, session, evidence = self._case(db, claims, vendor_id)
            digest = self._digest(vendor, required=action == 'approve')
            revision = review_revision(evidence, digest)
            previous, new = transitions[action]
            if vendor.review_version != expected_version or revision != expected_evidence_revision or vendor.verification_status != previous:
                raise ReviewConflict()
            if action in {'approve','reject'} and vendor.verification_submission_revision is None:
                raise ReviewConflict()
            if action == 'approve' and (revision != vendor.verification_submission_revision or not evidence_complete(evidence, self._storage())):
                raise ReviewConflict()
            if action == 'approve' and digest is None:
                raise ReviewConflict()
            now = self._live(db, claims, session)
            vendor.verification_status, vendor.approval_review_id = new, None
            if action == 'reopen':
                # Reopening is not an owner submission or an automatic approval.
                vendor.verification_submission_revision = None
                vendor.verification_submitted_at = None
            audit = self._record(db, vendor, claims.user_id, action, previous, revision, now, reason.strip())
            if action == 'approve':
                vendor.approval_review_id = audit.id
            db.flush()
            return {'status':new, 'case_version':vendor.review_version}
        return self._transaction(operation)

    def history(self, claims, vendor_id, *, after=0, limit=100):
        self._claims(claims)
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid audit filter')
        def operation(db):
            self._case(db, claims, vendor_id)
            rows = db.scalars(select(Audit).where(Audit.vendor_id == vendor_id, Audit.case_version > after).order_by(Audit.case_version).limit(limit)).all()
            return [{'reviewer_id':r.reviewer_id, 'actor_user_id':r.actor_user_id, 'action':r.action,
                     'evidence_revision':r.evidence_revision, 'case_version':r.case_version,
                     'previous_status':r.previous_status, 'new_status':r.new_status,
                     'decided_at':_utc(r.decided_at, db), 'reason':r.reason} for r in rows]
        return self._transaction(operation)
