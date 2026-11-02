"""Store private, sanitized ID submissions; upload is never identity approval."""
from enum import Enum
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.infrastructure.storage.private_documents import sanitize_document, VerificationInfrastructureUnavailable
from app.modules.auth.session_service import SessionAuthenticationError
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError
from app.modules.vendors.models import Vendor


class IdentificationType(str, Enum):
    NATIONAL_ID = 'national_id'
    PASSPORT = 'passport'
    DRIVERS_LICENSE = 'drivers_license'
    VOTER_ID = 'voter_id'


class VendorDocumentService(VendorAuthorizationService):
    def _editable(self, db, claims):
        self._active_user(self._lock_user(db, claims.user_id))
        session = self._lock_session(db, claims.user_id, claims.session_id)
        vendor = db.scalar(select(Vendor).where(Vendor.user_id == claims.user_id).with_for_update())
        now = self._now(db)
        self._active_session(db, session, now)
        if claims.expires_at <= now:
            raise SessionAuthenticationError()
        self._require_profile(None if vendor is None else vendor.id,
                              None if vendor is None else vendor.verification_status)
        if vendor.verification_status not in {'pending', 'rejected'}:
            raise VendorPermissionError()
        return vendor, now

    def submit(self, claims, identification_type: IdentificationType, content: bytes, storage):
        self._claims(claims)
        if not isinstance(identification_type, IdentificationType):
            raise ValueError('Unsupported identification type')
        # Authorize before decoding/storing; recheck under locks after storage.
        self._transaction(lambda db: self._editable(db, claims) and None)
        sanitized = sanitize_document(content)
        key = secrets.token_hex(32)
        try:
            storage.put(key, sanitized)
        except Exception:
            try:
                storage.delete(key)
            except Exception:
                pass
            raise VerificationInfrastructureUnavailable() from None

        def operation(db):
            vendor, now = self._editable(db, claims)
            previous = vendor.identity_document_key
            vendor.identification_type = identification_type.value
            vendor.identity_document_key = key
            vendor.identity_document_submitted_at = now
            vendor.identity_document_status = 'submitted'
            db.flush()
            return previous
        try:
            previous = self._transaction(operation)
        except Exception:
            # A commit failure can be ambiguous: never delete a potentially
            # committed reference. If reconciliation itself fails, retain a
            # private orphan for operator cleanup, never a public object.
            try:
                with Session(self._engine) as db:
                    referenced = db.scalar(select(Vendor.identity_document_key).where(Vendor.user_id == claims.user_id))
                if referenced != key:
                    storage.delete(key)
            except Exception:
                pass
            raise
        if previous:
            try:
                storage.delete(previous)
            except Exception:
                # Retained obsolete objects remain private; retention cleanup
                # must reconcile keys against current database references.
                pass
