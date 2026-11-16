"""One rotating, digest-only phone challenge and current ownership evidence per User."""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class PhoneVerification(Base):
    __tablename__ = 'phone_verifications'
    __table_args__ = (
        CheckConstraint('attempts BETWEEN 0 AND 5', name='ck_phone_attempts'),
        CheckConstraint('sends BETWEEN 0 AND 6', name='ck_phone_sends'),
        CheckConstraint('code_digest IS NULL OR length(code_digest) = 32', name='ck_phone_digest'),
        CheckConstraint('code_digest IS NULL OR (phone_number IS NOT NULL AND nonce IS NOT NULL AND expires_at IS NOT NULL)', name='ck_phone_challenge'),
        CheckConstraint('verified_at IS NULL OR (phone_number IS NOT NULL AND code_digest IS NULL)', name='ck_phone_verified'),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nonce: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    code_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0', default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sends: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0', default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
