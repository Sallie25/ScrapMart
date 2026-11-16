"""Live evidence checks. A stored approved status alone is never a selling grant."""
import hashlib
import json
from datetime import timezone
from sqlalchemy import select
from app.core.config import get_settings
from app.infrastructure.storage.private_documents import get_private_document_storage, sanitize_document, InvalidDocument, VerificationInfrastructureUnavailable
from app.modules.auth.models import User
from app.modules.auth.phone_models import PhoneVerification
from app.modules.auth.phone_service import current_phone
from app.modules.vendors.models import Vendor


def timestamp(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


def load_evidence(db, user_id, vendor_id):
    return db.execute(select(
        User.is_active, User.full_name, User.phone_number, Vendor.business_name, Vendor.shop_location,
        Vendor.shop_address, Vendor.identification_type, Vendor.identity_document_key,
        Vendor.identity_document_status, Vendor.identity_document_submitted_at,
        PhoneVerification.phone_number.label('proof_phone'), PhoneVerification.verified_at, PhoneVerification.nonce.label('proof_nonce'),
    ).select_from(Vendor).join(User, User.id == Vendor.user_id).outerjoin(
        PhoneVerification, PhoneVerification.user_id == User.id,
    ).where(Vendor.id == vendor_id, Vendor.user_id == user_id)).one_or_none()


def evidence_revision(row):
    if row is None:
        return None
    values = [row.full_name, row.business_name, row.shop_location, row.shop_address, row.identification_type,
              row.identity_document_key, row.identity_document_status, timestamp(row.identity_document_submitted_at),
              row.phone_number, row.proof_phone, timestamp(row.verified_at), str(row.proof_nonce) if row.proof_nonce else None, row.is_active]
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def evidence_complete(row, storage):
    return bool(row and row.is_active and all(v and v.strip() for v in (
        row.business_name, row.shop_location, row.shop_address,
    )) and row.identity_document_status == 'submitted' and row.identity_document_key
        and row.identification_type and row.identity_document_submitted_at
        and current_phone(row.phone_number) and row.proof_phone == row.phone_number
        and row.verified_at and storage.exists(row.identity_document_key))


def document_digest(storage, key):
    try:
        # Canonicalize even custom adapters; limit bytes/pixels and reject corrupt
        # objects before they can count as reviewed identity evidence.
        content = storage.read(key)
    except Exception:
        raise VerificationInfrastructureUnavailable() from None
    try:
        return hashlib.sha256(sanitize_document(content)).hexdigest()
    except InvalidDocument:
        return None


def review_revision(row, digest):
    return hashlib.sha256(json.dumps([evidence_revision(row), digest], separators=(',', ':')).encode()).hexdigest()


def require_approved_evidence(db, user_id, vendor_id, settings):
    from app.modules.auth.vendor_authorization import VendorPermissionError
    from app.modules.vendors.review_models import VerificationReviewAudit as Audit
    row = load_evidence(db, user_id, vendor_id)
    approval = db.execute(select(Audit.evidence_revision).join(
        Vendor, Vendor.approval_review_id == Audit.id,
    ).where(Vendor.id == vendor_id, Audit.vendor_id == vendor_id,
            Audit.action == 'approve', Audit.new_status == 'approved', Vendor.verification_status == 'approved')).scalar_one_or_none()
    if approval is None:
        raise VendorPermissionError()
    storage = get_private_document_storage(settings or get_settings())
    if not evidence_complete(row, storage):
        raise VendorPermissionError()
    digest = document_digest(storage, row.identity_document_key)
    if digest is None or review_revision(row, digest) != approval:
        raise VendorPermissionError()
