"""Vendor credentials and locked admission; shared session/token infrastructure."""
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.email_identity_models import EmailIdentityReservation as Reservation
from app.modules.auth.email_identity_policy import InvalidRegistrationEmail, PolicyVersionMismatch, canonical_registration_key
from app.modules.auth.login_policy import (
    BuyerLoginUnavailableError, require_ready_registry,
    stored_email_matches,
)
from app.modules.auth.login_schemas import BuyerLoginRequest
from app.modules.auth.models import User
from app.modules.auth.security import SecurityConfigurationError, verify_password
from app.modules.auth.session_service import (
    SessionAuthenticationError, SessionCredentials, SessionPersistenceError, SessionService,
)
from app.modules.vendors.models import Vendor
from app.modules.auth.session_service import _require_uuid

from app.modules.auth.login_service import _DUMMY_HASH

VENDOR_LOGIN_STATUSES = frozenset({"pending", "approved", "rejected", "suspended"})


class InvalidVendorCredentials(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class VendorLoginUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Vendor login is temporarily unavailable")


class VendorSessionAdmission(SessionService):
    def admit_vendor_session(self, user_id, key, verified_password_hash) -> SessionCredentials:
        """Trusted verifier only. Login grants identity, never selling permissions.

        Policy SHARE -> reservation SHARE -> User version update -> Vendor SHARE.
        All admission checks and session inserts share one committed transaction.
        """
        user_id = _require_uuid(user_id)
        if canonical_registration_key(key) != key or not isinstance(verified_password_hash, str):
            raise SessionAuthenticationError()
        lifetime = self._session_lifetime()

        def operation(db):
            require_ready_registry(db)
            reservation = db.scalar(select(Reservation.id).where(
                Reservation.lookup_key == key, Reservation.state == "owned",
                Reservation.policy_version == 1, Reservation.user_id == user_id,
            ).with_for_update(read=True))
            if reservation is None:
                raise SessionAuthenticationError()
            user = self._lock_user(db, user_id)
            self._active_user(user)
            if user.password_hash != verified_password_hash or not stored_email_matches(user.email, key):
                raise SessionAuthenticationError()
            status = db.scalar(select(Vendor.verification_status).where(
                Vendor.user_id == user_id,
            ).with_for_update(read=True))
            if status not in VENDOR_LOGIN_STATUSES:
                raise SessionAuthenticationError()
            # Shared creation samples fresh DB time after all lock waits.
            return self._create_session_records(db, user_id, lifetime)

        return self._transaction(operation)


class VendorLoginService:
    def __init__(self, engine: Engine, *, settings: Settings | None = None) -> None:
        self._sessions = VendorSessionAdmission(engine, settings=settings)
        self._engine = engine

    def login(self, request: BuyerLoginRequest) -> SessionCredentials:
        if not isinstance(request, BuyerLoginRequest):
            raise TypeError("VendorLoginService requires BuyerLoginRequest")
        try:
            key = canonical_registration_key(request.email)
            # Short read transaction ends before expensive Argon2 verification.
            # No mutable ORM objects escape; admission rechecks every condition.
            with Session(self._engine) as db, db.begin():
                connection = db.connection()
                if connection.dialect.detect_autocommit_setting(connection.connection.dbapi_connection):
                    raise VendorLoginUnavailableError()
                require_ready_registry(db)
                candidate = db.execute(select(User.id, User.email, User.password_hash, User.is_active, Vendor.verification_status).join(
                    Reservation, Reservation.user_id == User.id,
                ).join(Vendor, Vendor.user_id == User.id).where(
                    Reservation.lookup_key == key, Reservation.state == "owned",
                    Reservation.policy_version == 1,
                )).one_or_none()
                eligible = (
                    candidate is not None and candidate.is_active
                    and candidate.verification_status in VENDOR_LOGIN_STATUSES
                    and stored_email_matches(candidate.email, key)
                )
            password = request.password.get_secret_value()
            if eligible:
                verified = verify_password(password, candidate.password_hash, dummy_hash=_DUMMY_HASH)
            else:
                verify_password(password, _DUMMY_HASH)
                verified = False
            if not eligible or not verified:
                raise InvalidVendorCredentials()
            return self._sessions.admit_vendor_session(candidate.id, key, candidate.password_hash)
        except (SessionAuthenticationError, InvalidRegistrationEmail):
            raise InvalidVendorCredentials() from None
        except (SQLAlchemyError, OSError, NotImplementedError, SessionPersistenceError, SecurityConfigurationError, PolicyVersionMismatch, BuyerLoginUnavailableError):
            raise VendorLoginUnavailableError() from None
