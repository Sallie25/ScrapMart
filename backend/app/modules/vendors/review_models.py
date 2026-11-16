"""Explicit operator-granted reviewer permission and append-only review history."""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class VerificationReviewer(Base):
    __tablename__ = 'verification_reviewers'
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provisioning_reference: Mapped[str] = mapped_column(String(200), nullable=False)


class VerificationReviewAudit(Base):
    __tablename__ = 'verification_review_audit'
    __table_args__ = (
        CheckConstraint("action IN ('submit','approve','reject','suspend','reopen')", name='ck_review_action'),
        CheckConstraint("previous_status IN ('pending','approved','rejected','suspended') AND new_status IN ('pending','approved','rejected','suspended')", name='ck_review_status'),
        CheckConstraint("(action = 'submit' AND reviewer_id IS NULL) OR (action <> 'submit' AND reviewer_id IS NOT NULL AND actor_user_id = reviewer_id)", name='ck_review_actor'),
        CheckConstraint('length(evidence_revision) = 64 AND case_version > 0', name='ck_review_revision'),
        Index('ix_review_vendor_version', 'vendor_id', 'case_version', unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('vendors.id', ondelete='RESTRICT'), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
