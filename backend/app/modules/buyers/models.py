import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User


class BuyerProfile(Base):
    """An explicitly registered Buyer profile; never inferred from User.role.

    Registration must supply completion using the database clock, or explicitly
    supply both timestamps from one clock, to satisfy the chronology check.
    """

    __tablename__ = "buyer_profiles"
    __table_args__ = (
        CheckConstraint(
            "signup_completed_at >= created_at",
            name="ck_buyer_profiles_signup_completion_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    # Deliberately no default: registration must explicitly record completion.
    signup_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    user: Mapped["User"] = relationship()
