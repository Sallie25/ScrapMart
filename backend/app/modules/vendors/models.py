import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Vendor(Base):
    __tablename__ = "vendors"

    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('pending', 'approved', 'rejected', 'suspended')",
            name="ck_vendors_verification_status_valid",
        ),
        CheckConstraint("(identity_document_key IS NULL AND identification_type IS NULL AND identity_document_submitted_at IS NULL AND identity_document_status IS NULL) OR (identity_document_key IS NOT NULL AND length(identity_document_key) = 64 AND identification_type IS NOT NULL AND identification_type IN ('national_id', 'passport', 'drivers_license', 'voter_id') AND identity_document_submitted_at IS NOT NULL AND identity_document_status IS NOT NULL AND identity_document_status = 'submitted')", name="ck_vendor_identity_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    business_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Private onboarding information; never infer public location consent.
    shop_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    shop_address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    identification_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    identity_document_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    identity_document_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    identity_document_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    verification_submission_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Logical reference: authorization joins audit id AND vendor id AND action.
    # Keeping this one-way avoids a Vendor/audit creation/deletion FK cycle.
    approval_review_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    verification_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
