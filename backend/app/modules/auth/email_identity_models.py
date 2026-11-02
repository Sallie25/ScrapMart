"""Reservation registry schema only; readiness/backfill are maintenance operations.

These tables do not authorize authentication. PostgreSQL migration-installed
triggers, not metadata.create_all(), enforce the User writer contract.
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base

POLICY_STATE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
POLICY_VERSION = 1
KEY_CHECK = (
    "char_length(lookup_key) BETWEEN 3 AND 255 "
    "AND lookup_key COLLATE \"C\" ~ '^[!-~]+$' "
    "AND lookup_key = translate(lookup_key, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') "
    "AND char_length(lookup_key) - char_length(replace(lookup_key, '@', '')) = 1 "
    "AND position('@' in lookup_key) > 1 "
    "AND position('@' in lookup_key) < char_length(lookup_key)"
)


class EmailIdentityReservation(Base):
    __tablename__ = "email_identity_reservations"
    __table_args__ = (
        sa.UniqueConstraint("lookup_key", name="uq_eir_lookup_key"),
        sa.CheckConstraint(KEY_CHECK, name="ck_eir_ascii_key").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("policy_version = 1", name="ck_eir_policy_version"),
        sa.CheckConstraint(
            "(state = 'owned' AND user_id IS NOT NULL) OR "
            "(state = 'blocked' AND user_id IS NULL)", name="ck_eir_ownership",
        ),
        sa.Index("ix_eir_user_id", "user_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    lookup_key: Mapped[str] = mapped_column(
        sa.String(255, collation="C").with_variant(sa.String(255, collation="BINARY"), "sqlite"), nullable=False,
    )
    state: Mapped[str] = mapped_column(sa.String(7), nullable=False, server_default="owned")
    user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey(
        "users.id", name="fk_eir_user", ondelete="NO ACTION", onupdate="NO ACTION",
        deferrable=True, initially="DEFERRED",
    ), nullable=True)
    policy_version: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class EmailIdentityPolicyState(Base):
    __tablename__ = "email_identity_policy_state"
    __table_args__ = (
        sa.CheckConstraint(f"id = '{POLICY_STATE_ID}'", name="ck_eips_singleton"),
        sa.CheckConstraint("policy_version = 1", name="ck_eips_policy_version"),
        sa.CheckConstraint("status IN ('building', 'ready')", name="ck_eips_status"),
        sa.CheckConstraint("users_processed >= 0 AND source_count >= 0", name="ck_eips_counts"),
        sa.CheckConstraint("manifest_sha256 IS NULL OR length(manifest_sha256) = 32", name="ck_eips_manifest"),
        sa.CheckConstraint("status <> 'ready' OR (users_processed = source_count AND manifest_sha256 IS NOT NULL)", name="ck_eips_ready"),
    )
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True)
    policy_version: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(sa.String(8), nullable=False, server_default="building")
    last_user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    users_processed: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default="0")
    source_count: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default="0")
    manifest_sha256: Mapped[bytes | None] = mapped_column(sa.LargeBinary(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
