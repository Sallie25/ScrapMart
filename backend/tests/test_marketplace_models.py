"""Offline model checks; SQLite tests do not validate PostgreSQL triggers.

No application/settings imports or external database connections are used.
"""
import importlib.util
import io
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.categories.models import Category
from app.modules.listings.models import Listing, ListingImage
from app.modules.vendors.models import Vendor


@pytest.fixture
def database():
    engine = sa.create_engine("sqlite://")

    @sa.event.listens_for(engine, "connect")
    def setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("now", 0, lambda: "2026-10-18 00:00:00")
        connection.create_function("trunc", 1, math.trunc)

    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        clone = table.to_metadata(metadata)
        # SQLite cannot express deferred UNIQUE constraints. Only the clone
        # is changed; PostgreSQL DDL is checked separately below.
        for constraint in clone.constraints:
            if isinstance(constraint, sa.UniqueConstraint):
                constraint.deferrable = None
                constraint.initially = None
    metadata.create_all(engine)
    with engine.begin() as connection:
        user_id, vendor_id, category_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        connection.execute(User.__table__.insert().values(
            id=user_id, email="vendor@example.test", password_hash="test-only",
            full_name="Test Vendor", role="vendor",
        ))
        connection.execute(Vendor.__table__.insert().values(
            id=vendor_id, user_id=user_id, business_name="Test Shop",
        ))
        connection.execute(Category.__table__.insert().values(
            id=category_id, name="Metal", slug="metal",
        ))
    yield engine, vendor_id, category_id
    engine.dispose()


def insert_listing(database, **changes):
    engine, vendor_id, _ = database
    values = dict(id=uuid.uuid4(), vendor_id=vendor_id, title="Aluminium")
    values.update(changes)
    with engine.begin() as connection:
        connection.execute(Listing.__table__.insert().values(**values))
    return values["id"]


def active_fields(database):
    return dict(
        status="active", category_id=database[2], description="Clean scrap",
        price=100, quantity=2, quantity_unit="kilograms", condition="used",
        location_summary="Ikeja", latitude=6.6018, longitude=3.3515,
        published_at=datetime.now(timezone.utc),
    )


def test_defaults_and_draft_without_location(database):
    listing_id = insert_listing(database)
    with database[0].connect() as connection:
        row = connection.execute(sa.select(Listing.__table__).where(Listing.id == listing_id)).one()
    assert row.status == "draft"
    assert row.currency == "NGN"
    assert row.price_type == "total"
    assert row.is_negotiable is False
    assert row.location_visibility == "approximate"
    assert row.latitude is row.longitude is None


@pytest.mark.parametrize("changes", [
    {"latitude": 6}, {"longitude": 3}, {"latitude": 91, "longitude": 3},
    {"latitude": 6, "longitude": -181},
    {"latitude": 6, "longitude": 3, "location_visibility": "hidden"},
    {"location_visibility": "private"}, {"directions_allowed": True},
    {"status": "published"}, {"condition": "new"}, {"price_type": "negotiable"},
    {"price": -1}, {"currency": "USD"}, {"quantity": 0},
    {"quantity_unit": "unknown"}, {"quantity": 1.5, "quantity_unit": "pieces"},
    {"title": " "}, {"description": " "}, {"status": "active"},
])
def test_invalid_listing_rejected(database, changes):
    with pytest.raises(IntegrityError):
        insert_listing(database, **changes)


@pytest.mark.parametrize("field", [
    "category_id", "description", "price", "quantity", "quantity_unit",
    "condition", "latitude", "longitude", "location_summary", "published_at",
])
def test_active_requires_content_and_coordinates(database, field):
    values = active_fields(database)
    values[field] = None
    with pytest.raises(IntegrityError):
        insert_listing(database, **values)


@pytest.mark.parametrize("price_type", ["total", "per_unit"])
@pytest.mark.parametrize("negotiable", [False, True])
def test_pricing_and_public_site_directions(database, price_type, negotiable):
    insert_listing(database, **active_fields(database), price_type=price_type,
                   is_negotiable=negotiable, location_visibility="public_site",
                   directions_allowed=True)


def image_values(listing_id, position):
    return dict(id=uuid.uuid4(), listing_id=listing_id, position=position,
                object_key=f"listings/test/{position}.jpg", content_type="image/jpeg",
                size_bytes=100)


def test_five_images_ordering_and_constraints(database):
    listing_id = insert_listing(database)
    with database[0].begin() as connection:
        for position in reversed(range(5)):
            connection.execute(ListingImage.__table__.insert().values(**image_values(listing_id, position)))
    with Session(database[0]) as session:
        listing = session.get(Listing, listing_id)
        assert [image.position for image in listing.images] == list(range(5))
        assert listing.vendor.business_name == "Test Shop"
    for position in [0, 5, -1]:
        with pytest.raises(IntegrityError), database[0].begin() as connection:
            connection.execute(ListingImage.__table__.insert().values(**image_values(listing_id, position)))


@pytest.mark.parametrize("changes", [
    {"size_bytes": 0}, {"width": 0}, {"height": -1},
    {"object_key": " "}, {"content_type": " "}, {"listing_id": uuid.uuid4()},
])
def test_invalid_image_rejected(database, changes):
    values = image_values(insert_listing(database), 0)
    values.update(changes)
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(ListingImage.__table__.insert().values(**values))


@pytest.mark.parametrize("model,key", [(Vendor, 1), (Category, 2)])
def test_parent_deletion_restricted(database, model, key):
    insert_listing(database, category_id=database[2])
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(sa.delete(model).where(model.id == database[key]))


def test_uuid_foreign_keys_and_mapper_configuration():
    configure_mappers()
    for model in (Category, Listing, ListingImage):
        for column in model.__table__.columns:
            if column.primary_key or column.foreign_keys:
                assert isinstance(column.type, sa.Uuid)
        sa.schema.CreateTable(model.__table__).compile(dialect=postgresql.dialect())
    assert Listing.__table__.c.id.default.arg is not None
    assert "private_address" not in Listing.__table__.c


def test_migration_offline_upgrade_and_downgrade():
    path = Path(__file__).parents[1] / "alembic/versions/a7c92e4b610f_create_categories_listings_and_listing_images.py"
    spec = importlib.util.spec_from_file_location("marketplace_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "029a88ec1d86"
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration.upgrade()
        migration.downgrade()
    sql = output.getvalue()
    for table in ("categories", "listings", "listing_images"):
        assert f"CREATE TABLE {table}" in sql
        assert f"DROP TABLE {table}" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "ck_listings_active_has_image" in sql
    assert "BEFORE INSERT OR UPDATE OR DELETE ON listing_images" in sql
    assert "ALTER TABLE users" not in sql
    assert "ALTER TABLE vendors" not in sql


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"slug": " "}, {"slug": "Metal"}, {"slug": "metal"},
])
def test_category_validation_and_unique_slug(database, changes):
    values = dict(name="Plastic", slug="plastic")
    values.update(changes)
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(Category.__table__.insert().values(**values))


@pytest.mark.parametrize("unit", ["pieces", "kilograms", "tonnes", "bundles"])
def test_supported_units(database, unit):
    insert_listing(database, quantity=2, quantity_unit=unit)


@pytest.mark.parametrize("condition", ["good_condition", "used", "faulty", "damaged", "for_parts"])
def test_supported_conditions(database, condition):
    insert_listing(database, condition=condition)


@pytest.mark.parametrize("latitude,longitude", [(-90, -180), (90, 180), (0, 0)])
def test_coordinate_boundaries(database, latitude, longitude):
    insert_listing(database, latitude=latitude, longitude=longitude)


def test_listing_cannot_reference_missing_parent(database):
    with pytest.raises(IntegrityError):
        insert_listing(database, vendor_id=uuid.uuid4())
    with pytest.raises(IntegrityError):
        insert_listing(database, category_id=uuid.uuid4())
