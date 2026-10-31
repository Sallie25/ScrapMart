"""Vendor registration and authenticated enrollment using shared transactions."""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.modules.auth.vendor_schemas import VendorSignupRequest, VendorEnrollmentRequest
from app.modules.auth.models import User, UserRole
from app.modules.auth.registration_service import BuyerRegistrationService
from app.modules.auth.security import AccessTokenClaims, verify_password
from app.modules.auth.login_service import _DUMMY_HASH
from app.modules.auth.session_service import SessionService, SessionAuthenticationError, SessionPersistenceError
from app.modules.buyers.models import BuyerProfile
from app.modules.vendors.models import Vendor


class VendorRegistrationService(BuyerRegistrationService):
    _new_user_role = UserRole.VENDOR.value

    def register(self, signup: VendorSignupRequest) -> None:
        if not isinstance(signup, VendorSignupRequest):
            raise TypeError("Vendor registration requires VendorSignupRequest")
        super().register(signup)

    def _add_profile(self, db, user_id, signup):
        db.add(Vendor(user_id=user_id, business_name=signup.business_name,
                      verification_status="pending"))


class VendorEnrollmentService(SessionService):
    def enroll(self, claims: AccessTokenClaims, request: VendorEnrollmentRequest) -> None:
        if not isinstance(request, VendorEnrollmentRequest):
            raise TypeError("Vendor enrollment requires VendorEnrollmentRequest")
        # Establish live authentication before loading credentials. Expensive
        # verification holds no row locks; admission rechecks all mutable state.
        self.validate_access_session(claims)
        try:
            with Session(self._engine) as db, db.begin():
                candidate = db.scalar(select(User.password_hash).where(User.id == claims.user_id))
        except (SQLAlchemyError, OSError):
            raise SessionPersistenceError() from None
        if not verify_password(request.current_password.get_secret_value(), candidate, dummy_hash=_DUMMY_HASH):
            raise SessionAuthenticationError()

        def operation(db):
            user = self._lock_user(db, claims.user_id)
            self._active_user(user)
            session = self._lock_session(db, claims.user_id, claims.session_id)
            buyer = db.scalar(select(BuyerProfile.id).where(
                BuyerProfile.user_id == user.id).with_for_update(read=True))
            now = self._now(db)
            self._active_session(db, session, now)
            if claims.expires_at <= now or user.password_hash != candidate or buyer is None:
                raise SessionAuthenticationError()
            vendor = db.scalar(select(Vendor.id).where(Vendor.user_id == user.id))
            if vendor is None:
                db.add(Vendor(user_id=user.id, business_name=request.business_name,
                              verification_status="pending"))
                db.flush()
        self._transaction(operation)
