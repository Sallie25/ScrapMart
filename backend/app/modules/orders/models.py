"""Single-listing pay-on-delivery orders; receipts never imply payment collection."""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class Order(Base):
    __tablename__='orders'
    __table_args__=(
        CheckConstraint("status IN ('pending','accepted','preparing','delivered','completed','cancelled','rejected')",name='ck_orders_status'),
        CheckConstraint("currency = 'NGN' AND payment_method = 'pay_on_delivery'",name='ck_orders_payment_method'),
        CheckConstraint('total_amount >= 0 AND total_amount < 1000000000000000000000000',name='ck_orders_total'),
        CheckConstraint("status <> 'accepted' OR accepted_at IS NOT NULL",name='ck_orders_accepted'),
        CheckConstraint("status NOT IN ('preparing','delivered','completed') OR (accepted_at IS NOT NULL AND preparing_at IS NOT NULL)",name='ck_orders_preparing'),
        CheckConstraint("status NOT IN ('delivered','completed') OR delivered_at IS NOT NULL",name='ck_orders_delivered'),
        CheckConstraint("status <> 'completed' OR completed_at IS NOT NULL",name='ck_orders_completed'),
        CheckConstraint("status <> 'cancelled' OR cancelled_at IS NOT NULL",name='ck_orders_cancelled'),
        CheckConstraint("status <> 'rejected' OR rejected_at IS NOT NULL",name='ck_orders_rejected'),
        Index('uq_orders_buyer_request','buyer_profile_id','request_id',unique=True),
        Index('ix_orders_buyer_created','buyer_profile_id','created_at','id'),
        Index('ix_orders_vendor_created','vendor_id','created_at','id'),
    )
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    buyer_profile_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey('buyer_profiles.id',ondelete='RESTRICT'),nullable=False)
    vendor_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey('vendors.id',ondelete='RESTRICT'),nullable=False)
    request_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),nullable=False)
    vendor_business_name: Mapped[str]=mapped_column(String(200),nullable=False)
    status: Mapped[str]=mapped_column(String(20),nullable=False,default='pending',server_default='pending')
    currency: Mapped[str]=mapped_column(String(3),nullable=False,default='NGN',server_default='NGN')
    payment_method: Mapped[str]=mapped_column(String(30),nullable=False,default='pay_on_delivery',server_default='pay_on_delivery')
    total_amount: Mapped[Decimal]=mapped_column(Numeric(26,2),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now(),onupdate=func.now())
    accepted_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    preparing_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    delivered_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    completed_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    cancelled_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    rejected_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)


class OrderItem(Base):
    __tablename__='order_items'
    __table_args__=(
        CheckConstraint('quantity > 0 AND quantity < 100000000000',name='ck_order_items_quantity'),
        CheckConstraint("quantity_unit IN ('pieces','kilograms','tonnes','bundles')",name='ck_order_items_unit'),
        CheckConstraint("quantity_unit <> 'pieces' OR quantity = trunc(quantity)",name='ck_order_items_pieces'),
        CheckConstraint('listing_price >= 0 AND listing_price < 1000000000000',name='ck_order_items_price'),
        CheckConstraint("price_type IN ('total','per_unit')",name='ck_order_items_price_type'),
        CheckConstraint('line_total >= 0 AND line_total < 1000000000000000000000000',name='ck_order_items_total'),
        Index('ix_order_items_listing','listing_id'),
    )
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    order_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey('orders.id',ondelete='RESTRICT'),nullable=False,unique=True)
    listing_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey('listings.id',ondelete='RESTRICT'),nullable=False)
    listing_title: Mapped[str]=mapped_column(String(200),nullable=False)
    quantity: Mapped[Decimal]=mapped_column(Numeric(14,3),nullable=False)
    quantity_unit: Mapped[str]=mapped_column(String(30),nullable=False)
    listing_price: Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False)
    price_type: Mapped[str]=mapped_column(String(20),nullable=False)
    line_total: Mapped[Decimal]=mapped_column(Numeric(26,2),nullable=False)
