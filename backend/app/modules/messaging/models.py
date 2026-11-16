"""Persistent listing conversations and plain text messages."""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class Conversation(Base):
    __tablename__ = 'conversations'
    __table_args__ = (
        UniqueConstraint('buyer_profile_id', 'listing_id', name='uq_conversation_buyer_listing'),
        Index('ix_conversation_vendor_created', 'vendor_id', 'created_at', 'id'),
        Index('ix_conversation_buyer_created', 'buyer_profile_id', 'created_at', 'id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('listings.id', ondelete='RESTRICT'), nullable=False)
    buyer_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('buyer_profiles.id', ondelete='RESTRICT'), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('vendors.id', ondelete='RESTRICT'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        UniqueConstraint('conversation_id', 'sender_side', 'request_id', name='uq_message_request'),
        CheckConstraint("sender_side IN ('buyer', 'vendor')", name='ck_message_sender'),
        CheckConstraint('length(trim(content)) BETWEEN 1 AND 4000', name='ck_message_content'),
        Index('ix_message_history', 'conversation_id', 'created_at', 'id'),
        Index('ix_message_unread', 'conversation_id', 'sender_side', 'read_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='RESTRICT'), nullable=False)
    sender_side: Mapped[str] = mapped_column(String(6), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
