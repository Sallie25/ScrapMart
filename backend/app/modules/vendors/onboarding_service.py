"""Private shop drafts and fail-closed verification readiness, without uploads/SMS."""
from dataclasses import dataclass, field
from sqlalchemy import select, update
from app.modules.auth.models import User
from app.modules.auth.security import AccessTokenClaims
from app.modules.auth.session_models import AuthSession
from app.modules.auth.session_service import SessionAuthenticationError
from app.modules.auth.vendor_authorization import VendorAuthorizationService, VendorPermissionError
from app.modules.vendors.models import Vendor
from app.modules.vendors.onboarding_schemas import ShopInformationPatch


@dataclass(frozen=True)
class ShopInformation:
    business_name: str = field(repr=False)
    shop_location: str | None = field(repr=False)
    shop_address: str | None = field(repr=False)
    verification_status: str


@dataclass(frozen=True)
class VerificationReadiness:
    shop_information_complete: bool
    can_submit: bool
    outstanding_requirements: tuple[str, ...]


class VerificationNotReadyError(ValueError):
    def __init__(self):
        super().__init__("Verification submission is not available")


class VendorOnboardingService(VendorAuthorizationService):
    def _read_shop(self, db, claims):
        row = db.execute(select(
            User.is_active, AuthSession, Vendor.id, Vendor.business_name,
            Vendor.shop_location, Vendor.shop_address, Vendor.verification_status,
        ).select_from(User).join(AuthSession, AuthSession.user_id == User.id).outerjoin(
            Vendor, Vendor.user_id == User.id,
        ).where(User.id == claims.user_id, AuthSession.id == claims.session_id)).one_or_none()
        if row is None or not row.is_active:
            raise SessionAuthenticationError()
        now = self._now(db)
        self._active_session(db, row.AuthSession, now)
        if claims.expires_at <= now:
            raise SessionAuthenticationError()
        self._require_profile(row.id, row.verification_status)
        return ShopInformation(row.business_name, row.shop_location, row.shop_address, row.verification_status)

    def get_shop_information(self, claims: AccessTokenClaims) -> ShopInformation:
        self._claims(claims)
        return self._transaction(lambda db: self._read_shop(db, claims))

    def update_shop_information(self, claims: AccessTokenClaims, patch: ShopInformationPatch) -> ShopInformation:
        self._claims(claims)
        if not isinstance(patch, ShopInformationPatch):
            raise TypeError("ShopInformationPatch required")

        def operation(db):
            self._active_user(self._lock_user(db, claims.user_id))
            session = self._lock_session(db, claims.user_id, claims.session_id)
            vendor = db.scalar(select(Vendor).where(Vendor.user_id == claims.user_id).with_for_update())
            now = self._now(db)
            self._active_session(db, session, now)
            if claims.expires_at <= now:
                raise SessionAuthenticationError()
            self._require_profile(None if vendor is None else vendor.id,
                                  None if vendor is None else vendor.verification_status)
            # Approved information is immutable until audited re-review exists.
            # Suspension is operator-controlled: read only, no owner correction.
            if vendor.verification_status not in {"pending", "rejected"}:
                raise VendorPermissionError()
            values = patch.model_dump(exclude_unset=True)
            db.execute(update(Vendor).where(Vendor.id == vendor.id).values(**values))
            return ShopInformation(values.get("business_name", vendor.business_name),
                                   values.get("shop_location", vendor.shop_location),
                                   values.get("shop_address", vendor.shop_address), vendor.verification_status)
        return self._transaction(operation)

    def get_verification_readiness(self, claims: AccessTokenClaims, *, storage=None) -> VerificationReadiness:
        """Current readiness snapshot, never selling permission or approval."""
        from app.modules.auth.phone_models import PhoneVerification
        from app.modules.auth.phone_service import current_phone
        from app.infrastructure.storage.private_documents import get_private_document_storage
        from app.core.config import get_settings
        self._claims(claims)

        def operation(db):
            row = db.execute(select(
                User.is_active, User.phone_number, AuthSession, Vendor.id,
                Vendor.business_name, Vendor.shop_location, Vendor.shop_address,
                Vendor.verification_status, Vendor.identity_document_key,
                Vendor.identity_document_status, Vendor.identity_document_submitted_at,
                PhoneVerification.phone_number.label("verified_phone"), PhoneVerification.verified_at,
            ).select_from(User).join(AuthSession, AuthSession.user_id == User.id).outerjoin(
                Vendor, Vendor.user_id == User.id,
            ).outerjoin(PhoneVerification, PhoneVerification.user_id == User.id).where(
                User.id == claims.user_id, AuthSession.id == claims.session_id,
            )).one_or_none()
            if row is None or not row.is_active:
                raise SessionAuthenticationError()
            now = self._now(db)
            self._active_session(db, row.AuthSession, now)
            if claims.expires_at <= now:
                raise SessionAuthenticationError()
            self._require_profile(row.id, row.verification_status)
            complete = all(value and value.strip() for value in
                           (row.business_name, row.shop_location, row.shop_address))
            requirements = [] if complete else ["shop_information"]
            document = False
            if row.identity_document_key and row.identity_document_status == "submitted" and row.identity_document_submitted_at:
                backend = storage if storage is not None else get_private_document_storage(self._settings or get_settings())
                document = backend.exists(row.identity_document_key)
            if not document:
                requirements.append("secure_government_id_document")
            if not (row.verified_at and current_phone(row.phone_number) and row.verified_phone == row.phone_number):
                requirements.append("verified_phone_ownership")
            if row.verification_status not in {"pending", "rejected"}:
                requirements.append("account_status")
            return VerificationReadiness(bool(complete), not requirements, tuple(requirements))
        return self._transaction(operation)

    def require_verification_submission(self, claims: AccessTokenClaims, *, storage=None) -> None:
        """Readiness check only. Future submission must recheck in its own locked
        transaction, snapshot the evidence revision, and await authorized review.
        This method never changes Vendor status or grants approval.
        """
        if not self.get_verification_readiness(claims, storage=storage).can_submit:
            raise VerificationNotReadyError()
