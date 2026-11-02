import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.modules.categories.models import Category
    from app.modules.vendors.models import Vendor


class Listing(Base):
    """Listing locations contain vendor-approved PUBLIC data only.

    Approximation/consent must be handled before writing coordinates here.
    Private vendor addresses belong in separate future persistence.
    The migration enforces the active-listing image minimum with triggers.
    """

    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint('length(trim(title)) > 0', name="ck_listings_title_nonblank"),
        CheckConstraint('description IS NULL OR length(trim(description)) > 0', name="ck_listings_description_nonblank"),
        CheckConstraint('price IS NULL OR (price >= 0 AND price < 1000000000000)', name="ck_listings_price_valid"),
        CheckConstraint("currency = 'NGN'", name="ck_listings_currency_valid"),
        CheckConstraint("price_type IN ('total', 'per_unit')", name="ck_listings_price_type_valid"),
        CheckConstraint('quantity IS NULL OR (quantity > 0 AND quantity < 100000000000)', name="ck_listings_quantity_valid"),
        CheckConstraint("quantity_unit IS NULL OR quantity_unit IN ('pieces', 'kilograms', 'tonnes', 'bundles')", name="ck_listings_quantity_unit_valid"),
        CheckConstraint("quantity_unit IS DISTINCT FROM 'pieces' OR quantity IS NULL OR quantity = trunc(quantity)", name="ck_listings_pieces_whole"),
        CheckConstraint("condition IS NULL OR condition IN ('good_condition', 'used', 'faulty', 'damaged', 'for_parts')", name="ck_listings_condition_valid"),
        CheckConstraint("status IN ('draft', 'active', 'inactive', 'sold', 'removed')", name="ck_listings_status_valid"),
        CheckConstraint('latitude IS NULL OR latitude BETWEEN -90 AND 90', name="ck_listings_latitude_valid"),
        CheckConstraint('longitude IS NULL OR longitude BETWEEN -180 AND 180', name="ck_listings_longitude_valid"),
        CheckConstraint('(latitude IS NULL) = (longitude IS NULL)', name="ck_listings_coordinates_paired"),
        CheckConstraint("location_visibility IN ('hidden', 'approximate', 'public_site')", name="ck_listings_visibility_valid"),
        CheckConstraint("location_visibility <> 'hidden' OR latitude IS NULL", name="ck_listings_hidden_coordinates"),
        CheckConstraint("NOT directions_allowed OR (location_visibility = 'public_site' AND latitude IS NOT NULL AND longitude IS NOT NULL)", name="ck_listings_directions_public"),
        CheckConstraint('location_summary IS NULL OR length(trim(location_summary)) > 0', name="ck_listings_summary_nonblank"),
        CheckConstraint("status <> 'active' OR (category_id IS NOT NULL AND description IS NOT NULL AND price IS NOT NULL AND quantity IS NOT NULL AND quantity_unit IS NOT NULL AND condition IS NOT NULL AND location_summary IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL AND location_visibility <> 'hidden' AND published_at IS NOT NULL)", name="ck_listings_active_complete"),
        Index("ix_listings_status_published_at", "status", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN", server_default="NGN")
    price_type: Mapped[str] = mapped_column(String(20), nullable=False, default="total", server_default="total")
    is_negotiable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    location_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lga: Mapped[str | None] = mapped_column(String(100), nullable=True)
    area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    location_visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="approximate", server_default="approximate")
    directions_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    vendor: Mapped["Vendor"] = relationship()
    category: Mapped["Category | None"] = relationship(back_populates="listings")
    images: Mapped[list["ListingImage"]] = relationship(
        back_populates="listing", order_by="ListingImage.position",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class ListingImage(Base):
    __tablename__ = "listing_images"
    __table_args__ = (
        UniqueConstraint("listing_id", "position", name="uq_listing_images_listing_position", deferrable=True, initially="DEFERRED"),
        CheckConstraint("position BETWEEN 0 AND 4", name="ck_listing_images_position_valid"),
        CheckConstraint("length(trim(object_key)) > 0", name="ck_listing_images_object_key_nonblank"),
        CheckConstraint("length(trim(content_type)) > 0", name="ck_listing_images_content_type_nonblank"),
        CheckConstraint("size_bytes > 0", name="ck_listing_images_size_positive"),
        CheckConstraint("width IS NULL OR width > 0", name="ck_listing_images_width_positive"),
        CheckConstraint("height IS NULL OR height > 0", name="ck_listing_images_height_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    listing: Mapped["Listing"] = relationship(back_populates="images")
