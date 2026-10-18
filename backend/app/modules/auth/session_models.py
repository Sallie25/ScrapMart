import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User


class AuthSession(Base):
    """One revocable login session and its family of rotating refresh tokens.

    Stage 2 must check session expiry/revocation on every authenticated request,
    including access JWT validation. Revoke all sessions by user_id for global
    logout. This model does not issue tokens or infer account capabilities.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at", name="ck_auth_sessions_expiry_valid",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_auth_sessions_revocation_valid",
        ),
        Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    user: Mapped["User"] = relationship()
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="session", passive_deletes="all",
    )


class RefreshToken(Base):
    """Digest-only refresh-token history, retained to identify token reuse.

    token_digest stores SHA-256 digest bytes, never a bearer token or hex text.
    Stage 2 must atomically lock/consume a token and insert its replacement in
    the same session. Reuse of a consumed token revokes that session. Session
    state and token expiry relative to session expiry are cross-record service
    checks; database row constraints alone cannot enforce them.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(token_digest) = 32",
            name="ck_refresh_tokens_digest_length",
        ),
        CheckConstraint(
            "expires_at > created_at", name="ck_refresh_tokens_expiry_valid",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR "
            "(consumed_at >= created_at AND consumed_at < expires_at)",
            name="ck_refresh_tokens_consumption_valid",
        ),
        Index("ix_refresh_tokens_session_id", "session_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    token_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32), nullable=False, unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    session: Mapped["AuthSession"] = relationship(back_populates="refresh_tokens")
