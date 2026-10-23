"""Reusable Buyer credential verification; no HTTP, cookies, or JWT issuance."""
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.email_identity_models import EmailIdentityReservation as Reservation
from app.modules.auth.email_identity_policy import InvalidRegistrationEmail, PolicyVersionMismatch, canonical_registration_key
from app.modules.auth.login_policy import (
    BuyerLoginUnavailableError, InvalidBuyerCredentials, require_ready_registry,
    stored_email_matches,
)
from app.modules.auth.login_schemas import BuyerLoginRequest
from app.modules.auth.models import User
from app.modules.auth.security import SecurityConfigurationError, verify_password
from app.modules.auth.session_service import (
    SessionAuthenticationError, SessionCredentials, SessionPersistenceError, SessionService,
)
from app.modules.buyers.models import BuyerProfile

# Valid Argon2id, same work factors as Stage 2A. This is not an account credential.
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=1$IAJZ6xC2CUbfi80GxiFtmA$l72KpPktzDjCcZcLV+8dhuR+iYCzVXICbgyce8LeJOA"


class BuyerLoginService:
    def __init__(self, engine: Engine, *, settings: Settings | None = None) -> None:
        self._sessions = SessionService(engine, settings=settings)
        self._engine = engine

    def login(self, request: BuyerLoginRequest) -> SessionCredentials:
        if not isinstance(request, BuyerLoginRequest):
            raise TypeError("BuyerLoginService requires BuyerLoginRequest")
        try:
            key = canonical_registration_key(request.email)
            # Short read transaction ends before expensive Argon2 verification.
            # No mutable ORM objects escape; admission rechecks every condition.
            with Session(self._engine) as db, db.begin():
                connection = db.connection()
                if connection.dialect.detect_autocommit_setting(connection.connection.dbapi_connection):
                    raise BuyerLoginUnavailableError()
                require_ready_registry(db)
                candidate = db.execute(select(User.id, User.email, User.password_hash, User.is_active).join(
                    Reservation, Reservation.user_id == User.id,
                ).join(BuyerProfile, BuyerProfile.user_id == User.id).where(
                    Reservation.lookup_key == key, Reservation.state == "owned",
                    Reservation.policy_version == 1,
                )).one_or_none()
                eligible = (
                    candidate is not None and candidate.is_active
                    and stored_email_matches(candidate.email, key)
                )
            password = request.password.get_secret_value()
            if eligible:
                verified = verify_password(password, candidate.password_hash, dummy_hash=_DUMMY_HASH)
            else:
                verify_password(password, _DUMMY_HASH)
                verified = False
            if not eligible or not verified:
                raise InvalidBuyerCredentials()
            return self._sessions.admit_buyer_session(candidate.id, key, candidate.password_hash)
        except (SessionAuthenticationError, InvalidRegistrationEmail):
            raise InvalidBuyerCredentials() from None
        except (SQLAlchemyError, OSError, NotImplementedError, SessionPersistenceError, SecurityConfigurationError, PolicyVersionMismatch):
            raise BuyerLoginUnavailableError() from None
