"""Atomic reservation-first Buyer registration, never login or account linking.

Each attempt owns a fresh engine-bound Session. Policy SHARE lock precedes all
reservation access. Unknown commit outcomes never cause an automatic retry.
"""
import uuid

from sqlalchemy import Engine, func, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.auth.email_identity_models import EmailIdentityPolicyState as Policy, EmailIdentityReservation as Reservation, POLICY_STATE_ID
from app.modules.auth.email_identity_policy import (
    AliasDisposition, InvalidRegistrationEmail, PolicyVersionMismatch,
    canonical_registration_key, legacy_email_identity, policy_fingerprint,
)
from app.modules.auth.models import User, UserRole
from app.modules.auth.registration_schemas import BuyerSignupRequest
from app.modules.auth.security import hash_password
from app.modules.buyers.models import BuyerProfile

APPROVED_FINGERPRINT = "cbdc5198ab2b1c3f23062e5318c97f0ab4e403023a69035e355bc8e8c431e59f"


class RegistrationUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Registration is temporarily unavailable")


class BuyerRegistrationService:
    def __init__(self, engine: Engine) -> None:
        if not isinstance(engine, Engine):
            raise TypeError("BuyerRegistrationService requires a synchronous Engine")
        self._engine = engine

    @staticmethod
    def _ready(db):
        if policy_fingerprint() != APPROVED_FINGERPRINT:
            raise RegistrationUnavailableError()
        state = db.execute(select(Policy.status, Policy.policy_version).where(
            Policy.id == POLICY_STATE_ID,
        ).with_for_update(read=True)).one_or_none()
        if state is None or state.status != "ready" or state.policy_version != 1:
            raise RegistrationUnavailableError()

    @staticmethod
    def _reservation_conflict(error):
        orig = error.orig
        return (
            getattr(orig, "sqlstate", None) == "23505"
            and getattr(getattr(orig, "diag", None), "constraint_name", None) == "uq_eir_lookup_key"
            and getattr(getattr(orig, "diag", None), "table_name", None) == "email_identity_reservations"
        ) or (
            getattr(orig, "sqlite_errorcode", None) == 2067
            and str(orig) == "UNIQUE constraint failed: email_identity_reservations.lookup_key"
        )

    _new_user_role = UserRole.BUYER.value

    def _add_profile(self, db, user_id, signup):
        now = db.scalar(select(func.current_timestamp()))
        db.add(BuyerProfile(user_id=user_id, created_at=now, signup_completed_at=now))

    def register(self, signup: BuyerSignupRequest) -> None:
        try:
            key = canonical_registration_key(signup.email)
            identity = legacy_email_identity(key)
            if identity.blocks_readiness or identity.fingerprint != APPROVED_FINGERPRINT or identity.policy_version != 1:
                raise RegistrationUnavailableError()
            if not any(a.key == key and a.disposition is AliasDisposition.OWNED for a in identity.aliases):
                raise RegistrationUnavailableError()
            keys = tuple(a.key for a in identity.aliases)  # V1 sorted, bounded bundle.
            password_hash = hash_password(signup.password.get_secret_value())  # Outside locks; also for duplicates.
            confirm_only = False
            for attempt in range(3):
                committing = False
                try:
                    with Session(self._engine) as db:
                        try:
                            with db.begin():
                                connection = db.connection()
                                if connection.dialect.detect_autocommit_setting(connection.connection.dbapi_connection):
                                    raise RegistrationUnavailableError()
                                if connection.dialect.name == "postgresql":
                                    db.execute(text("SET LOCAL statement_timeout='15s'"))
                                    db.execute(text("SET LOCAL lock_timeout='2s'"))
                                    db.execute(text("SET LOCAL synchronous_commit=on"))
                                self._ready(db)
                                existing = db.scalar(select(Reservation.id).where(
                                    Reservation.lookup_key.in_(keys),
                                ).limit(1))
                                if existing is None:
                                    if confirm_only:
                                        raise RegistrationUnavailableError()
                                    user_id = uuid.uuid4()
                                    # Explicit Core inserts avoid ORM sorting User before reservations.
                                    for alias in identity.aliases:
                                        db.execute(insert(Reservation.__table__).values(
                                            id=uuid.uuid4(), lookup_key=alias.key, state=alias.disposition.value,
                                            user_id=user_id if alias.disposition is AliasDisposition.OWNED else None,
                                        ))
                                    db.flush()
                                    db.add(User(id=user_id, email=key, password_hash=password_hash,
                                                full_name=signup.full_name, phone_number=signup.phone_number,
                                                role=self._new_user_role))
                                    db.flush()
                                    self._add_profile(db, user_id, signup)
                                    db.flush()
                                committing = True
                            return  # Includes successful deferred-constraint commit.
                        except BaseException:
                            if committing:
                                db.invalidate()  # Discard ambiguous driver state.
                            raise
                except IntegrityError as error:
                    if not committing and self._reservation_conflict(error) and attempt < 2:
                        confirm_only = True
                        continue  # Fresh readiness check + authoritative conflict lookup.
                    raise RegistrationUnavailableError() from None
                except DBAPIError as error:
                    if getattr(error.orig, "sqlstate", None) in {"40001", "40P01"} and attempt < 2:
                        continue
                    raise RegistrationUnavailableError() from None
            raise RegistrationUnavailableError()
        except (SQLAlchemyError, OSError, NotImplementedError, PolicyVersionMismatch, InvalidRegistrationEmail):
            raise RegistrationUnavailableError() from None
