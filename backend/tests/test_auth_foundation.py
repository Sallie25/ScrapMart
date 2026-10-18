"""Stage 1 persistence tests: in-memory SQLite and offline PostgreSQL DDL.

Never import application settings or connect to an external database. SQLite
checks are not a substitute for authorized PostgreSQL migration/concurrency tests.
"""
import hashlib
import importlib.util
import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.buyers.models import BuyerProfile
from app.modules.categories.models import Category
from app.modules.listings.models import Listing, ListingImage
from app.modules.vendors.models import Vendor


ROOT = Path(__file__).parents[1]
REVISION = "b81d4f2a9c06"
NEW_TABLES = {"buyer_profiles", "auth_sessions", "refresh_tokens"}
CREATED = datetime(2026, 10, 18, tzinfo=timezone.utc)
EXPIRES = CREATED + timedelta(days=7)


def load_migration():
    path = ROOT / "alembic/versions/b81d4f2a9c06_add_buyer_profiles_and_auth_sessions.py"
    spec = importlib.util.spec_from_file_location("auth_foundation_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_database():
    engine = sa.create_engine("sqlite://")

    @sa.event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("now", 0, lambda: "2026-10-18 00:00:00")

    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in NEW_TABLES:
            clone = table.to_metadata(metadata)
            # Existing marketplace UNIQUE is deferred only on PostgreSQL.
            for constraint in clone.constraints:
                if isinstance(constraint, sa.UniqueConstraint):
                    constraint.deferrable = None
                    constraint.initially = None
    metadata.create_all(engine)
    user_id, vendor_id, category_id, listing_id = [uuid.uuid4() for _ in range(4)]
    with engine.begin() as connection:
        connection.execute(User.__table__.insert().values(
            id=user_id, email="existing@example.test", password_hash="test-only",
            full_name="Existing Vendor", role="vendor",
        ))
        connection.execute(Vendor.__table__.insert().values(
            id=vendor_id, user_id=user_id, business_name="Existing Shop",
        ))
        connection.execute(Category.__table__.insert().values(
            id=category_id, name="Metal", slug="metal",
        ))
        connection.execute(Listing.__table__.insert().values(
            id=listing_id, vendor_id=vendor_id, category_id=category_id,
            title="Existing material",
        ))
        connection.execute(ListingImage.__table__.insert().values(
            id=uuid.uuid4(), listing_id=listing_id, object_key="test/existing.jpg",
            position=0, content_type="image/jpeg", size_bytes=100,
        ))
    yield engine, user_id
    engine.dispose()


@pytest.fixture
def database(legacy_database):
    engine, user_id = legacy_database
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        load_migration().upgrade()
    return engine, user_id


def session_values(user_id, /, **changes):
    values = dict(id=uuid.uuid4(), user_id=user_id, created_at=CREATED, expires_at=EXPIRES)
    values.update(changes)
    return values


def token_values(session_id, /, **changes):
    values = dict(
        id=uuid.uuid4(), session_id=session_id,
        token_digest=hashlib.sha256(uuid.uuid4().bytes).digest(),
        created_at=CREATED, expires_at=EXPIRES,
    )
    values.update(changes)
    return values


def insert_session(database, **changes):
    engine, user_id = database
    values = session_values(user_id, **changes)
    with engine.begin() as connection:
        connection.execute(AuthSession.__table__.insert().values(**values))
    return values["id"]


def test_profile_creation_is_explicit_and_vendor_can_have_both_profiles(database):
    engine, user_id = database
    with Session(engine) as session:
        assert session.query(BuyerProfile).count() == 0
        # Creating a User, Vendor, or authentication session grants no profile.
        session.add(User(email="buyer-role@example.test", role="buyer",
                         password_hash="test-only", full_name="No profile yet"))
        session.add(AuthSession(user_id=user_id, created_at=CREATED, expires_at=EXPIRES))
        session.commit()
        assert session.query(BuyerProfile).count() == 0
        profile = BuyerProfile(user_id=user_id, created_at=CREATED,
                               signup_completed_at=CREATED)
        session.add(profile)
        session.commit()
        assert isinstance(profile.id, uuid.UUID)
        assert profile.user.id == user_id
        assert profile.user.role == "vendor"
        assert session.query(Vendor).filter_by(user_id=user_id).one().business_name == "Existing Shop"


@pytest.mark.parametrize("changes", [
    {"signup_completed_at": None},
    {"signup_completed_at": CREATED - timedelta(seconds=1)},
    {"user_id": uuid.uuid4()},
    {"user_id": None},
])
def test_invalid_buyer_profile_rejected(database, changes):
    values = dict(user_id=database[1], created_at=CREATED, signup_completed_at=CREATED)
    values.update(changes)
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(BuyerProfile.__table__.insert().values(**values))


def test_profile_completion_has_no_implicit_default(database):
    assert BuyerProfile.__table__.c.signup_completed_at.default is None
    assert BuyerProfile.__table__.c.signup_completed_at.server_default is None
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(BuyerProfile.__table__.insert().values(user_id=database[1]))


def test_buyer_profile_user_is_unique(database):
    values = dict(user_id=database[1], created_at=CREATED, signup_completed_at=CREATED)
    with database[0].begin() as connection:
        connection.execute(BuyerProfile.__table__.insert().values(**values))
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(BuyerProfile.__table__.insert().values(**values))


@pytest.mark.parametrize("changes", [
    {"expires_at": CREATED},
    {"expires_at": CREATED - timedelta(seconds=1)},
    {"expires_at": None},
    {"revoked_at": CREATED - timedelta(seconds=1)},
    {"user_id": uuid.uuid4()},
    {"user_id": None},
])
def test_invalid_session_rejected(database, changes):
    with pytest.raises(IntegrityError):
        insert_session(database, **changes)


@pytest.mark.parametrize("changes", [
    {"token_digest": b"short"},
    {"token_digest": b"x" * 33},
    {"token_digest": None},
    {"expires_at": CREATED},
    {"expires_at": None},
    {"consumed_at": CREATED - timedelta(seconds=1)},
    {"consumed_at": EXPIRES},
    {"consumed_at": EXPIRES + timedelta(seconds=1)},
    {"session_id": uuid.uuid4()},
    {"session_id": None},
])
def test_invalid_refresh_token_rejected(database, changes):
    session_id = insert_session(database)
    values = token_values(session_id, **changes)
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(RefreshToken.__table__.insert().values(**values))


def test_digest_unique_across_sessions(database):
    first, second = insert_session(database), insert_session(database)
    digest = hashlib.sha256(b"disposable-test-secret").digest()
    with database[0].begin() as connection:
        connection.execute(RefreshToken.__table__.insert().values(**token_values(first, token_digest=digest)))
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(RefreshToken.__table__.insert().values(**token_values(second, token_digest=digest)))


def test_rotation_history_and_relationships(database):
    with Session(database[0]) as session:
        auth_session = AuthSession(user_id=database[1], created_at=CREATED, expires_at=EXPIRES)
        previous = RefreshToken(**{k: v for k, v in token_values(uuid.uuid4()).items() if k != "session_id"})
        auth_session.refresh_tokens.append(previous)
        session.add(auth_session)
        session.commit()
        assert previous.session_id == auth_session.id
        assert isinstance(previous.id, uuid.UUID)
        assert auth_session.user.id == database[1]

        previous.consumed_at = CREATED + timedelta(minutes=10)
        replacement_values = token_values(auth_session.id, created_at=CREATED + timedelta(minutes=10))
        replacement = RefreshToken(**replacement_values)
        session.add(replacement)
        session.commit()
        session.expire(auth_session, ["refresh_tokens"])
        assert len(auth_session.refresh_tokens) == 2
        # Consumed digest remains resolvable to its session for Stage 2 reuse detection.
        found = session.query(RefreshToken).filter_by(token_digest=previous.token_digest).one()
        assert found.consumed_at is not None
        assert found.session.id == replacement.session.id


def test_session_and_all_session_revocation_storage(database):
    engine, user_id = database
    first, second = insert_session(database), insert_session(database)
    with engine.begin() as connection:
        other = User.__table__.insert().values(email="other@example.test", role="buyer",
                    password_hash="test-only", full_name="Other User").returning(User.id)
        other_id = connection.execute(other).scalar_one()
        third_values = session_values(other_id)
        connection.execute(AuthSession.__table__.insert().values(**third_values))
        connection.execute(sa.update(AuthSession).where(AuthSession.id == first).values(revoked_at=CREATED))
    with Session(engine) as session:
        assert session.get(AuthSession, first).revoked_at is not None
        assert session.get(AuthSession, second).revoked_at is None
    with engine.begin() as connection:
        connection.execute(sa.update(AuthSession).where(
            AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None),
        ).values(revoked_at=CREATED + timedelta(minutes=1)))
    with Session(engine) as session:
        assert session.get(AuthSession, second).revoked_at is not None
        assert session.get(AuthSession, third_values["id"]).revoked_at is None


@pytest.mark.parametrize("loaded", [False, True])
def test_session_deletion_cannot_cascade_token_history(database, loaded):
    sid = insert_session(database)
    with database[0].begin() as connection:
        connection.execute(RefreshToken.__table__.insert().values(**token_values(sid)))
    with Session(database[0]) as session:
        auth_session = session.get(AuthSession, sid)
        if loaded:
            assert len(auth_session.refresh_tokens) == 1
        session.delete(auth_session)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.parametrize("child", ["buyer", "session"])
def test_user_deletion_restricted_with_foundation_records(database, child):
    with database[0].begin() as connection:
        # Use an otherwise unreferenced identity so marketplace FKs cannot mask
        # a missing Buyer/session FK restriction.
        user_id = connection.execute(User.__table__.insert().values(
            email="foundation-only@example.test", role="buyer",
            password_hash="test-only", full_name="Foundation User",
        ).returning(User.id)).scalar_one()
        if child == "buyer":
            connection.execute(BuyerProfile.__table__.insert().values(
                user_id=user_id, created_at=CREATED, signup_completed_at=CREATED,
            ))
        else:
            connection.execute(AuthSession.__table__.insert().values(**session_values(user_id)))
    with pytest.raises(IntegrityError), database[0].begin() as connection:
        connection.execute(sa.delete(User).where(User.id == user_id))


def legacy_rows(connection):
    return {
        model.__tablename__: connection.execute(sa.select(model.__table__)).all()
        for model in (User, Vendor, Category, Listing, ListingImage)
    }


def test_migration_upgrade_downgrade_preserves_existing_records(legacy_database):
    engine, user_id = legacy_database
    migration = load_migration()
    assert migration.revision == REVISION
    assert migration.down_revision == "a7c92e4b610f"
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        before = legacy_rows(connection)
        migration.upgrade()
        assert legacy_rows(connection) == before
        assert connection.execute(sa.select(sa.func.count()).select_from(BuyerProfile)).scalar_one() == 0
        connection.execute(BuyerProfile.__table__.insert().values(
            user_id=user_id, created_at=CREATED, signup_completed_at=CREATED,
        ))
        values = session_values(user_id)
        connection.execute(AuthSession.__table__.insert().values(**values))
        connection.execute(RefreshToken.__table__.insert().values(**token_values(values["id"])))
        migration.downgrade()
        assert NEW_TABLES.isdisjoint(sa.inspect(connection).get_table_names())
        assert legacy_rows(connection) == before
        migration.upgrade()
        assert NEW_TABLES <= set(sa.inspect(connection).get_table_names())
        assert legacy_rows(connection) == before


def test_migrated_schema_matches_models(database):
    def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
        # SQLite reflects the migration's native UUID spelling as NUMERIC.
        # Actual PostgreSQL UUID types are checked by offline DDL below.
        if isinstance(metadata_type, sa.Uuid):
            return False
        return None

    with database[0].connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": compare_type})
        assert compare_metadata(context, Base.metadata) == []
        inspector = sa.inspect(connection)
        for model in (BuyerProfile, AuthSession, RefreshToken):
            expected_checks = {c.name for c in model.__table__.constraints if isinstance(c, sa.CheckConstraint)}
            assert {c["name"] for c in inspector.get_check_constraints(model.__tablename__)} == expected_checks


def test_metadata_registration_uuid_defaults_and_digest_only_storage():
    configure_mappers()
    for model in (BuyerProfile, AuthSession, RefreshToken):
        assert model.__tablename__ in Base.metadata.tables
        assert model.__table__.c.id.default is not None
        for column in model.__table__.columns:
            if column.primary_key or column.foreign_keys:
                assert isinstance(column.type, sa.Uuid)
            if isinstance(column.type, sa.DateTime):
                assert column.type.timezone is True
        sa.schema.CreateTable(model.__table__).compile(dialect=postgresql.dialect())
    assert isinstance(RefreshToken.__table__.c.token_digest.type, sa.LargeBinary)
    assert set(RefreshToken.__table__.c.keys()) == {
        "id", "session_id", "token_digest", "created_at", "expires_at", "consumed_at",
    }
    assert set(BuyerProfile.__table__.c.keys()) == {"id", "user_id", "created_at", "signup_completed_at"}


def test_offline_postgresql_migration_and_chain():
    scripts = ScriptDirectory(str(ROOT / "alembic"))
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == "a7c92e4b610f"
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        load_migration().upgrade()
        load_migration().downgrade()
    sql = output.getvalue()
    for table in NEW_TABLES:
        assert f"CREATE TABLE {table}" in sql
        assert f"DROP TABLE {table}" in sql
    assert "BYTEA" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "ALTER TABLE" not in sql
    assert "INSERT INTO" not in sql
    assert "UPDATE " not in sql
    assert sql.index("DROP TABLE refresh_tokens") < sql.index("DROP TABLE auth_sessions")
