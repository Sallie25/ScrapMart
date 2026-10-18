"""Create categories, listings, and listing images.

Revision ID: a7c92e4b610f
Revises: 029a88ec1d86

Publication's image minimum is deferred until transaction end. Parent-row
updates serialize image mutations, preventing concurrent removals from leaving
an active listing without images. No existing tables are altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7c92e4b610f"
down_revision: Union[str, Sequence[str], None] = "029a88ec1d86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('categories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name='ck_categories_name_nonblank'),
    sa.CheckConstraint('length(trim(slug)) > 0 AND slug = lower(slug)', name='ck_categories_slug_valid'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('listings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vendor_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='NGN', nullable=False),
    sa.Column('price_type', sa.String(length=20), server_default='total', nullable=False),
    sa.Column('is_negotiable', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('quantity_unit', sa.String(length=30), nullable=True),
    sa.Column('condition', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('location_summary', sa.String(length=255), nullable=True),
    sa.Column('lga', sa.String(length=100), nullable=True),
    sa.Column('area', sa.String(length=100), nullable=True),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('location_visibility', sa.String(length=20), server_default='approximate', nullable=False),
    sa.Column('directions_allowed', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("NOT directions_allowed OR (location_visibility = 'public_site' AND latitude IS NOT NULL AND longitude IS NOT NULL)", name='ck_listings_directions_public'),
    sa.CheckConstraint("condition IS NULL OR condition IN ('good_condition', 'used', 'faulty', 'damaged', 'for_parts')", name='ck_listings_condition_valid'),
    sa.CheckConstraint("currency = 'NGN'", name='ck_listings_currency_valid'),
    sa.CheckConstraint("location_visibility <> 'hidden' OR latitude IS NULL", name='ck_listings_hidden_coordinates'),
    sa.CheckConstraint("location_visibility IN ('hidden', 'approximate', 'public_site')", name='ck_listings_visibility_valid'),
    sa.CheckConstraint("price_type IN ('total', 'per_unit')", name='ck_listings_price_type_valid'),
    sa.CheckConstraint("quantity_unit IS DISTINCT FROM 'pieces' OR quantity IS NULL OR quantity = trunc(quantity)", name='ck_listings_pieces_whole'),
    sa.CheckConstraint("quantity_unit IS NULL OR quantity_unit IN ('pieces', 'kilograms', 'tonnes', 'bundles')", name='ck_listings_quantity_unit_valid'),
    sa.CheckConstraint("status <> 'active' OR (category_id IS NOT NULL AND description IS NOT NULL AND price IS NOT NULL AND quantity IS NOT NULL AND quantity_unit IS NOT NULL AND condition IS NOT NULL AND location_summary IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL AND location_visibility <> 'hidden' AND published_at IS NOT NULL)", name='ck_listings_active_complete'),
    sa.CheckConstraint("status IN ('draft', 'active', 'inactive', 'sold', 'removed')", name='ck_listings_status_valid'),
    sa.CheckConstraint('(latitude IS NULL) = (longitude IS NULL)', name='ck_listings_coordinates_paired'),
    sa.CheckConstraint('description IS NULL OR length(trim(description)) > 0', name='ck_listings_description_nonblank'),
    sa.CheckConstraint('latitude IS NULL OR latitude BETWEEN -90 AND 90', name='ck_listings_latitude_valid'),
    sa.CheckConstraint('length(trim(title)) > 0', name='ck_listings_title_nonblank'),
    sa.CheckConstraint('location_summary IS NULL OR length(trim(location_summary)) > 0', name='ck_listings_summary_nonblank'),
    sa.CheckConstraint('longitude IS NULL OR longitude BETWEEN -180 AND 180', name='ck_listings_longitude_valid'),
    sa.CheckConstraint('price IS NULL OR (price >= 0 AND price < 1000000000000)', name='ck_listings_price_valid'),
    sa.CheckConstraint('quantity IS NULL OR (quantity > 0 AND quantity < 100000000000)', name='ck_listings_quantity_valid'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_listings_category_id'), 'listings', ['category_id'], unique=False)
    op.create_index('ix_listings_status_published_at', 'listings', ['status', 'published_at'], unique=False)
    op.create_index(op.f('ix_listings_vendor_id'), 'listings', ['vendor_id'], unique=False)
    op.create_table('listing_images',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('listing_id', sa.UUID(), nullable=False),
    sa.Column('object_key', sa.Text(), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('height IS NULL OR height > 0', name='ck_listing_images_height_positive'),
    sa.CheckConstraint('length(trim(content_type)) > 0', name='ck_listing_images_content_type_nonblank'),
    sa.CheckConstraint('length(trim(object_key)) > 0', name='ck_listing_images_object_key_nonblank'),
    sa.CheckConstraint('position BETWEEN 0 AND 4', name='ck_listing_images_position_valid'),
    sa.CheckConstraint('size_bytes > 0', name='ck_listing_images_size_positive'),
    sa.CheckConstraint('width IS NULL OR width > 0', name='ck_listing_images_width_positive'),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('listing_id', 'position', deferrable=True, initially='DEFERRED', name='uq_listing_images_listing_position')
    )
    op.execute("""
        CREATE FUNCTION scrapmart_lock_image_listing() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE parent_id uuid;
        BEGIN
            -- A real update also prevents stale-snapshot write skew at
            -- REPEATABLE READ (PostgreSQL raises a serialization error).
            FOR parent_id IN
                SELECT DISTINCT id FROM unnest(ARRAY[
                    CASE WHEN TG_OP <> 'INSERT' THEN OLD.listing_id END,
                    CASE WHEN TG_OP <> 'DELETE' THEN NEW.listing_id END
                ]) AS parents(id) WHERE id IS NOT NULL ORDER BY id
            LOOP
                UPDATE listings SET id = id WHERE id = parent_id;
            END LOOP;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_listing_images_lock_parent
        BEFORE INSERT OR UPDATE OR DELETE ON listing_images
        FOR EACH ROW EXECUTE FUNCTION scrapmart_lock_image_listing()
    """)
    op.execute("""
        CREATE FUNCTION scrapmart_check_listing_images() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE parent_id uuid; parent_ids uuid[];
        BEGIN
            IF TG_TABLE_NAME = 'listings' THEN
                parent_ids := ARRAY[NEW.id];
            ELSE
                parent_ids := ARRAY[
                    CASE WHEN TG_OP <> 'INSERT' THEN OLD.listing_id END,
                    CASE WHEN TG_OP <> 'DELETE' THEN NEW.listing_id END
                ];
            END IF;
            FOREACH parent_id IN ARRAY parent_ids LOOP
                IF EXISTS (SELECT 1 FROM listings WHERE id = parent_id AND status = 'active')
                   AND NOT EXISTS (SELECT 1 FROM listing_images WHERE listing_id = parent_id)
                THEN
                    RAISE EXCEPTION 'Active listings require at least one image'
                        USING ERRCODE = '23514', CONSTRAINT = 'ck_listings_active_has_image';
                END IF;
            END LOOP;
            RETURN NULL;
        END;
        $$
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_listings_require_image
        AFTER INSERT OR UPDATE ON listings
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION scrapmart_check_listing_images()
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_listing_images_require_image
        AFTER INSERT OR UPDATE OR DELETE ON listing_images
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION scrapmart_check_listing_images()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_listing_images_require_image ON listing_images")
    op.execute("DROP TRIGGER trg_listings_require_image ON listings")
    op.execute("DROP TRIGGER trg_listing_images_lock_parent ON listing_images")
    op.execute("DROP FUNCTION scrapmart_check_listing_images()")
    op.execute("DROP FUNCTION scrapmart_lock_image_listing()")
    op.drop_table("listing_images")
    op.drop_index("ix_listings_status_published_at", table_name="listings")
    op.drop_index("ix_listings_category_id", table_name="listings")
    op.drop_index("ix_listings_vendor_id", table_name="listings")
    op.drop_table("listings")
    op.drop_table("categories")
