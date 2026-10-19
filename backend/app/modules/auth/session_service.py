"""Database session services. No HTTP, JWT issuance, or profile permissions.

Each attempt constructs a NEW engine-bound SQLAlchemy Session/transaction.
Only a synchronous Engine is accepted; Sessions, Connections and factories are
rejected before any caller-owned resource is touched. Returned DTOs contain no
ORM objects. Mutations lock User,
then AuthSession, then RefreshToken; logout-all and session creation also lock
User, establishing an order across all session operations for that identity.
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.modules.auth.models import User
from app.modules.auth.security import (
    AccessTokenClaims,
    InvalidRefreshTokenError,
    SecurityConfigurationError,
    digest_refresh_token,
    generate_refresh_token,
)
from app.modules.auth.session_models import AuthSession, RefreshToken


class SessionAuthenticationError(ValueError):
    """A generic rejection, with no token values or account-existence details."""

    def __init__(self) -> None:
        super().__init__("Authentication session is invalid")


class SessionPersistenceError(RuntimeError):
    """A persistence operation failed; do not expose database error details."""

    def __init__(self) -> None:
        super().__init__("Authentication session operation could not be completed")


@dataclass(frozen=True)
class SessionIdentity:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime


@dataclass(frozen=True)
class SessionCredentials(SessionIdentity):
    # Only the trusted calling layer receives plaintext, after successful commit.
    refresh_token: str = field(repr=False)


_T = TypeVar("_T")
_REPLAY = object()


def _require_uuid(value: object) -> uuid.UUID:
    if not isinstance(value, uuid.UUID):
        raise SessionAuthenticationError()
    return value


def _utc(value: datetime, db: Session) -> datetime:
    if value.tzinfo is None:
        # SQLite loses tzinfo; production PostgreSQL must return aware values.
        if db.get_bind().dialect.name != "sqlite":
            raise SessionAuthenticationError()
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SessionService:
    def __init__(
        self, engine: Engine, *, settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(engine, Engine):
            raise TypeError("SessionService requires a synchronous Engine; no Sessions, Connections or factories")
        self._engine = engine
        self._settings = settings
        # Trusted injection for offline tests. Production defaults to DB time.
        self._clock = clock

    def _now(self, db: Session) -> datetime:
        if self._clock is not None:
            value = self._clock()
        elif db.get_bind().dialect.name == "postgresql":
            # Unlike now(), this advances while waiting for row locks.
            value = db.scalar(select(func.clock_timestamp()))
        else:
            value = datetime.now(timezone.utc)
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise SecurityConfigurationError("Session clock must return timezone-aware time")
        return value.astimezone(timezone.utc)

    def _transaction(self, operation: Callable[[Session], _T]) -> _T:
        for attempt in range(3):
            try:
                with Session(self._engine) as db:
                    with db.begin():
                        connection = db.connection()
                        # AUTOCOMMIT would make rollback/atomic rotation ineffective.
                        # Inspect the actual driver state, including engine defaults.
                        try:
                            autocommit = connection.dialect.detect_autocommit_setting(
                                connection.connection.dbapi_connection,
                            )
                        except NotImplementedError:
                            raise SecurityConfigurationError(
                                "SessionService requires a driver with autocommit detection"
                            ) from None
                        if autocommit:
                            raise SecurityConfigurationError("SessionService requires transactional isolation")
                        result = operation(db)
                    # Commit has completed, including deferred constraints.
                    return result
            except DBAPIError as error:
                if getattr(error.orig, "sqlstate", None) in {"40001", "40P01"} and attempt < 2:
                    continue
                raise SessionPersistenceError() from None
            except SQLAlchemyError:
                raise SessionPersistenceError() from None
        raise SessionPersistenceError()  # Defensive; every attempt returns/raises.

    @staticmethod
    def _lock_user(db: Session, user_id: uuid.UUID) -> User:
        # Preserve every field, including updated_at, but create a row version.
        # A lock-only SELECT does not invalidate a Repeatable Read snapshot:
        # logout-all could otherwise miss a session created while it waited.
        user = db.scalar(update(User).where(User.id == user_id).values(
            updated_at=User.updated_at,
        ).returning(User))
        if user is None:
            raise SessionAuthenticationError()
        return user

    @staticmethod
    def _active_user(user: User) -> None:
        if not user.is_active:
            raise SessionAuthenticationError()

    @staticmethod
    def _lock_session(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> AuthSession:
        session = db.scalar(select(AuthSession).where(
            AuthSession.id == session_id, AuthSession.user_id == user_id,
        ).with_for_update())
        if session is None:
            raise SessionAuthenticationError()
        return session

    @staticmethod
    def _active_session(db: Session, session: AuthSession, now: datetime) -> None:
        if (
            session.revoked_at is not None
            or _utc(session.created_at, db) > now
            or _utc(session.expires_at, db) <= now
        ):
            raise SessionAuthenticationError()

    def create_session(self, user_id: uuid.UUID) -> SessionCredentials:
        """Call only after authenticating the existing identity; never links by email."""
        user_id = _require_uuid(user_id)
        settings = self._settings if self._settings is not None else get_settings()
        days = settings.auth_session_expire_days
        if type(days) is not int or days <= 0:
            raise SecurityConfigurationError("Session lifetime must be a positive number of days")
        try:
            lifetime = timedelta(days=days)
        except OverflowError:
            raise SecurityConfigurationError("Session lifetime is outside the supported range") from None

        def operation(db: Session) -> SessionCredentials:
            self._active_user(self._lock_user(db, user_id))
            now = self._now(db)
            try:
                expiry = now + lifetime
            except OverflowError:
                raise SecurityConfigurationError("Session lifetime is outside the supported range") from None
            session = AuthSession(id=uuid.uuid4(), user_id=user_id, created_at=now, expires_at=expiry)
            plaintext = generate_refresh_token()
            token = RefreshToken(
                session=session, token_digest=digest_refresh_token(plaintext),
                created_at=now, expires_at=expiry,
            )
            db.add(token)
            return SessionCredentials(user_id, session.id, expiry, plaintext)

        return self._transaction(operation)

    def validate_access_session(self, claims: AccessTokenClaims) -> SessionIdentity:
        """Accept only Stage 2A-verified claims; no role/profile permission inference."""
        if not isinstance(claims, AccessTokenClaims):
            raise SessionAuthenticationError()
        user_id = _require_uuid(claims.user_id)
        session_id = _require_uuid(claims.session_id)

        def operation(db: Session) -> SessionIdentity:
            row = db.execute(select(User, AuthSession).join(
                AuthSession, AuthSession.user_id == User.id,
            ).where(User.id == user_id, AuthSession.id == session_id)).one_or_none()
            if row is None:
                raise SessionAuthenticationError()
            user, session = row
            self._active_user(user)
            self._active_session(db, session, self._now(db))
            return SessionIdentity(user_id, session_id, _utc(session.expires_at, db))

        return self._transaction(operation)

    def rotate_refresh_token(self, plaintext: str) -> SessionCredentials:
        try:
            digest = digest_refresh_token(plaintext)
        except InvalidRefreshTokenError:
            raise SessionAuthenticationError() from None

        def operation(db: Session) -> SessionCredentials | object:
            # Lookup scalar IDs only; lock/re-read mutable state in a fixed order.
            candidate = db.execute(select(RefreshToken.id, RefreshToken.session_id, AuthSession.user_id).join(
                AuthSession, AuthSession.id == RefreshToken.session_id,
            ).where(RefreshToken.token_digest == digest)).one_or_none()
            if candidate is None:
                raise SessionAuthenticationError()
            token_id, session_id, user_id = candidate
            user = self._lock_user(db, user_id)
            session = self._lock_session(db, user_id, session_id)
            token = db.scalar(select(RefreshToken).where(
                RefreshToken.id == token_id, RefreshToken.session_id == session_id,
                RefreshToken.token_digest == digest,
            ).with_for_update())
            if token is None:
                raise SessionAuthenticationError()
            now = self._now(db)
            # Reuse is checked even if expiry/inactivation occurred afterwards.
            if token.consumed_at is not None:
                if session.revoked_at is None:
                    session.revoked_at = now
                return _REPLAY
            self._active_user(user)
            self._active_session(db, session, now)
            expiry = _utc(session.expires_at, db)
            if (
                _utc(token.created_at, db) > now
                or _utc(token.expires_at, db) <= now
                or _utc(token.expires_at, db) > expiry
            ):
                raise SessionAuthenticationError()
            replacement = generate_refresh_token()
            token.consumed_at = now
            db.add(RefreshToken(
                session_id=session_id, token_digest=digest_refresh_token(replacement),
                created_at=now, expires_at=expiry,
            ))
            return SessionCredentials(user_id, session_id, expiry, replacement)

        result = self._transaction(operation)
        if result is _REPLAY:
            # This must be outside the transaction: do not roll back revocation.
            raise SessionAuthenticationError()
        return result

    def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        user_id, session_id = _require_uuid(user_id), _require_uuid(session_id)

        def operation(db: Session) -> bool:
            self._active_user(self._lock_user(db, user_id))
            session = self._lock_session(db, user_id, session_id)
            if session.revoked_at is not None:
                return False
            session.revoked_at = self._now(db)
            return True

        return self._transaction(operation)

    def revoke_all_sessions(self, user_id: uuid.UUID) -> int:
        user_id = _require_uuid(user_id)

        def operation(db: Session) -> int:
            self._active_user(self._lock_user(db, user_id))
            now = self._now(db)
            result = db.execute(update(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            ).values(revoked_at=now))
            return result.rowcount

        return self._transaction(operation)
