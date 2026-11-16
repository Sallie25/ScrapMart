"""Phase 1 migration validation, exclusively in verified disposable local schemas.

Synthetic readiness exists only inside these throwaway fixtures. This module
implements neither a backfill nor a readiness finalizer.
"""
import os
import threading
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import DBAPIError

from app.modules.auth.email_identity_models import EmailIdentityPolicyState, EmailIdentityReservation
from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionService
from app.modules.buyers.models import BuyerProfile
from tests.test_auth_sessions_postgresql import local_postgres, run_threads
from tests.test_email_identity_schema import migration
from app.core.config import Settings

pytestmark = pytest.mark.skipif(os.environ.get("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS") != "1", reason="Explicit disposable local PostgreSQL opt-in required")
R = EmailIdentityReservation.__table__
P = EmailIdentityPolicyState.__table__


@pytest.fixture
def registry(local_postgres):
    with local_postgres.connect() as db:
        assert set(db.execute(sa.text("SELECT datname FROM pg_database")).scalars()) == {"postgres", "template0", "template1", "scrapmart_test"}
    schema = "email_registry_" + uuid.uuid4().hex
    with local_postgres.begin() as db:
        db.exec_driver_sql("CREATE SCHEMA " + schema)
    engine = sa.create_engine(local_postgres.url, hide_parameters=True, connect_args={
        "connect_timeout": 5,
        "options": f"-c search_path={schema} -c statement_timeout=10000 -c lock_timeout=3000",
    })
    legacy = uuid.uuid4()
    try:
        User.metadata.create_all(engine, tables=[User.__table__, BuyerProfile.__table__, AuthSession.__table__, RefreshToken.__table__])
        with engine.begin() as db:
            db.execute(User.__table__.insert().values(id=legacy, email="Σ@παράδειγμα.test", full_name="Legacy 名", password_hash="test-only"))
            with Operations.context(MigrationContext.configure(db, opts={"version_table_schema": schema})):
                migration().upgrade()
        yield SimpleNamespace(engine=engine, schema=schema, legacy=legacy)
    finally:
        engine.dispose()
        with local_postgres.begin() as db:
            db.exec_driver_sql("DROP SCHEMA " + schema + " CASCADE")
            assert db.scalar(sa.text("SELECT count(*) FROM pg_namespace WHERE nspname=:schema"), {"schema": schema}) == 0


def ready(db):
    db.execute(P.update().values(status="ready", manifest_sha256=b"x" * 32))


def reserve(db, user_id, email="new@example.test", **changes):
    values = dict(id=uuid.uuid4(), lookup_key=email, user_id=user_id)
    values.update(changes)
    db.execute(R.insert().values(**values))


def user(db, user_id, email="new@example.test"):
    db.execute(User.__table__.insert().values(id=user_id, email=email, full_name="Buyer 名", password_hash="test-only"))


def test_migration_constraints_metadata_and_downgrade(registry):
    engine, schema = registry.engine, registry.schema
    with engine.begin() as db:
        assert db.execute(sa.select(P.c.status, P.c.policy_version)).one() == ("building", 1)
        inspector = sa.inspect(db)
        fk = inspector.get_foreign_keys(R.name)[0]
        assert fk["options"]["deferrable"] and fk["options"]["initially"] == "DEFERRED"
        assert "uq_eir_lookup_key" in {c["name"] for c in inspector.get_unique_constraints(R.name)}
        assert "ix_eir_user_id" in {i["name"] for i in inspector.get_indexes(R.name)}
        checks = {c["name"] for c in inspector.get_check_constraints(R.name)}
        assert checks == {"ck_eir_ascii_key", "ck_eir_policy_version", "ck_eir_ownership"}
        functions = db.execute(sa.text("SELECT provolatile, prosecdef, proconfig FROM pg_proc JOIN pg_namespace n ON n.oid=pronamespace WHERE n.nspname=:s AND proname='verify_user_email_reservation'"), {"s": schema}).one()
        assert functions[0] == "v" and not functions[1] and functions[2] == ["search_path=pg_catalog"]
        triggers = db.execute(sa.text("SELECT tgdeferrable, tginitdeferred FROM pg_trigger WHERE tgrelid='users'::regclass AND tgname='ct_users_email_reservation'")).one()
        assert triggers == (False, False)
        # Compare only these tables: existing Stage 1 tables are validated elsewhere.
        metadata = sa.MetaData()
        User.__table__.to_metadata(metadata)
        for model in (EmailIdentityReservation, EmailIdentityPolicyState):
            model.__table__.to_metadata(metadata)
        context = MigrationContext.configure(db, opts={"include_object": lambda obj, name, type_, reflected, compare_to: type_ != "table" or name in metadata.tables})
        assert compare_metadata(context, metadata) == []
        before = db.execute(sa.select(User.__table__)).all()
        with Operations.context(MigrationContext.configure(db, opts={"version_table_schema": schema})):
            migration().downgrade()
            assert db.execute(sa.select(User.__table__)).all() == before
            assert R.name not in sa.inspect(db).get_table_names()
            migration().upgrade()
        assert db.scalar(sa.select(P.c.status)) == "building"


@pytest.mark.parametrize("state", ["missing", "building", "wrong_version"])
def test_readiness_fails_closed(registry, state):
    with registry.engine.begin() as db:
        if state == "missing":
            db.execute(P.delete())
        elif state == "wrong_version":
            # Simulate damaged/misconfigured registry independently of CHECK.
            db.exec_driver_sql("ALTER TABLE email_identity_policy_state DROP CONSTRAINT ck_eips_policy_version")
            ready(db)
            db.execute(P.update().values(policy_version=2))
    with pytest.raises(DBAPIError) as error, registry.engine.begin() as db:
        identifier = uuid.uuid4()
        reserve(db, identifier)
        user(db, identifier)
    assert error.value.orig.sqlstate == "55000"
    with registry.engine.connect() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(R)) == 0


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_reservation_first_immediate_visibility_and_commit(registry, isolation):
    identifier = uuid.uuid4()
    with registry.engine.begin() as db:
        ready(db)
    with registry.engine.connect().execution_options(isolation_level=isolation) as db, db.begin():
        reserve(db, identifier)
        assert db.scalar(sa.select(sa.func.count()).select_from(User).where(User.id == identifier)) == 0
        user(db, identifier)
        db.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        db.execute(BuyerProfile.__table__.insert().values(id=uuid.uuid4(), user_id=identifier, signup_completed_at=sa.func.now()))
    with registry.engine.connect() as db:
        assert db.scalar(sa.select(User.email).where(User.id == identifier)) == "new@example.test"


@pytest.mark.parametrize("failure", ["missing_reservation", "wrong_owner", "blocked", "uppercase", "unicode", "orphan", "partial"])
def test_atomic_failure_and_immediate_guard(registry, failure):
    with registry.engine.begin() as db:
        ready(db)
    with pytest.raises((DBAPIError, RuntimeError)), registry.engine.begin() as db:
        db.exec_driver_sql("SET CONSTRAINTS ALL DEFERRED")
        identifier = uuid.uuid4()
        email = {"uppercase": "UPPER@example.test", "unicode": "K@example.test"}.get(failure, "new@example.test")
        if failure != "missing_reservation":
            owner = registry.legacy if failure == "wrong_owner" else identifier
            if failure == "blocked":
                reserve(db, None, state="blocked")
            else:
                reserve(db, owner)
        if failure != "orphan":
            user(db, identifier, email)
        if failure == "partial":
            raise RuntimeError("simulate Buyer insert failure")
    with registry.engine.connect() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(R)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 1


@pytest.mark.parametrize("key", ["A@example.test", "a@παράδειγμα.test", "a@@test", "@test", "test@", "a b@test", "a@t\n", "x" * 256])
def test_key_constraints(registry, key):
    with pytest.raises(DBAPIError), registry.engine.begin() as db:
        reserve(db, registry.legacy, key)


@pytest.mark.parametrize("change", ["reassign", "rekey", "unblock", "policy", "state"])
def test_reservation_mutation_guards(registry, change):
    other_user = uuid.uuid4()
    with registry.engine.begin() as db:
        if change == "reassign":
            # Both owners must exist: otherwise the deferred foreign key could
            # reject reassignment even if the ownership trigger were broken.
            ready(db)
            reserve(db, other_user, "other@example.test")
            user(db, other_user, "other@example.test")
        reserve(db, registry.legacy)
        reserve(db, None, "blocked@example.test", state="blocked")
        before = db.execute(sa.select(R).order_by(R.c.lookup_key)).all()
    with pytest.raises(DBAPIError) as error, registry.engine.begin() as db:
        if change == "unblock":
            db.execute(R.update().where(R.c.state == "blocked").values(state="owned", user_id=registry.legacy))
        else:
            values = {"reassign": {"user_id": other_user}, "rekey": {"lookup_key": "other@example.test"}, "policy": {"policy_version": 2}, "state": {"state": "bad"}}[change]
            db.execute(R.update().where(R.c.lookup_key == "new@example.test").values(**values))
    if change == "reassign":
        assert error.value.orig.sqlstate == "23514"
        assert error.value.orig.diag.message_primary == "Email reservation transition is unavailable"
    with registry.engine.connect() as db:
        assert db.execute(sa.select(R).order_by(R.c.lookup_key)).all() == before
        assert db.scalar(sa.select(R.c.user_id).where(R.c.lookup_key == "new@example.test")) == registry.legacy
        if change == "reassign":
            assert set(db.scalars(sa.select(User.id))) == {registry.legacy, other_user}
    with registry.engine.begin() as db:
        db.execute(R.update().where(R.c.lookup_key == "new@example.test").values(state="blocked", user_id=None))


def test_legacy_updates_sessions_and_email_immutability(registry):
    with registry.engine.begin() as db:
        before = db.execute(sa.select(User.__table__)).one()
        db.execute(User.__table__.update().where(User.id == registry.legacy).values(updated_at=User.updated_at, email=User.email))
        assert db.execute(sa.select(User.__table__)).one() == before
    # SessionService locks User with a value-preserving UPDATE, including while building.
    settings = Settings(_env_file=None, _secrets_dir=None)
    credentials = SessionService(registry.engine, settings=settings).create_session(registry.legacy)
    assert credentials is not None
    with pytest.raises(DBAPIError), registry.engine.begin() as db:
        db.execute(User.__table__.update().where(User.id == registry.legacy).values(email="changed@example.test"))
    with registry.engine.connect() as db:
        assert db.scalar(sa.select(User.email).where(User.id == registry.legacy)) == before.email


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_concurrent_duplicate_and_readiness_lock(registry, isolation):
    with registry.engine.begin() as db:
        ready(db)
    barrier = threading.Barrier(2)
    outcomes = []

    def register():
        try:
            with registry.engine.connect().execution_options(isolation_level=isolation) as db, db.begin():
                barrier.wait(10)
                identifier = uuid.uuid4()
                reserve(db, identifier)
                user(db, identifier)
            outcomes.append("committed")
        except DBAPIError as error:
            assert error.orig.sqlstate in {"23505", "40001", "40P01"}
            outcomes.append("conflict")
    run_threads(register, register)
    assert sorted(outcomes) == ["committed", "conflict"]
    # A successful insert retains a policy SHARE lock until transaction end.
    with registry.engine.begin() as db:
        identifier = uuid.uuid4()
        reserve(db, identifier, "lock@example.test")
        user(db, identifier, "lock@example.test")
        with pytest.raises(DBAPIError) as error, registry.engine.begin() as maintenance:
            maintenance.exec_driver_sql("SET LOCAL lock_timeout='100ms'")
            maintenance.execute(P.update().values(status="building"))
        assert error.value.orig.sqlstate == "55P03"


def test_restricted_nonowner_role_cannot_bypass_guards(registry, local_postgres):
    role = "email_runtime_" + uuid.uuid4().hex
    with local_postgres.begin() as db:
        assert db.scalar(sa.text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user"))
        db.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS")
        # SET ROLE tests DML permissions, but session_user is still the test
        # superuser; audit membership rather than falsely testing SET ROLE back
        # to that original login (which PostgreSQL intentionally permits).
        assert not db.scalar(sa.text("SELECT pg_has_role(:role, current_user, 'MEMBER')"), {"role": role})
        assert not db.scalar(sa.text("SELECT has_schema_privilege(:role, :schema, 'CREATE')"), {"role": role, "schema": registry.schema})
        db.exec_driver_sql(f"GRANT USAGE ON SCHEMA {registry.schema} TO {role}")
        for table in ("users", "email_identity_reservations", "email_identity_policy_state"):
            db.exec_driver_sql(f"GRANT SELECT ON {registry.schema}.{table} TO {role}")
        db.exec_driver_sql(f"GRANT INSERT (id,email,password_hash,full_name,role,is_active) ON {registry.schema}.users TO {role}")
        db.exec_driver_sql(f"GRANT UPDATE (updated_at) ON {registry.schema}.users TO {role}")
        # SELECT FOR SHARE needs UPDATE on at least one column. Narrow grants on
        # immutable columns allow row locks without policy-state mutation.
        db.exec_driver_sql(f"GRANT UPDATE (id) ON {registry.schema}.email_identity_policy_state TO {role}")
        db.exec_driver_sql(f"GRANT UPDATE (id) ON {registry.schema}.email_identity_reservations TO {role}")
        db.exec_driver_sql(f"GRANT INSERT (id,lookup_key,user_id) ON {registry.schema}.email_identity_reservations TO {role}")
    try:
        with registry.engine.begin() as db:
            reserve(db, registry.legacy, "legacy@example.test")
        for statement in (
            "UPDATE email_identity_policy_state SET status='ready'",
            "DELETE FROM email_identity_policy_state", "TRUNCATE email_identity_policy_state",
            "DELETE FROM email_identity_reservations", "TRUNCATE email_identity_reservations",
            "UPDATE email_identity_reservations SET user_id=NULL",
            "INSERT INTO email_identity_reservations(id,lookup_key,state) VALUES (gen_random_uuid(),'blocked@example.test','blocked')",
            "DELETE FROM users", "TRUNCATE users CASCADE",
            "ALTER TABLE users DISABLE TRIGGER ALL", "SET LOCAL session_replication_role=replica",
            "CREATE TABLE unauthorized_table(id integer)",
            "SET CONSTRAINTS ct_users_email_reservation DEFERRED",
            "UPDATE email_identity_policy_state SET id=gen_random_uuid()",
            "UPDATE email_identity_reservations SET id=gen_random_uuid()",
        ):
            with pytest.raises(DBAPIError), registry.engine.begin() as db:
                db.exec_driver_sql(f"SET LOCAL ROLE {role}")
                db.exec_driver_sql(statement)
        with pytest.raises(DBAPIError) as error, registry.engine.begin() as db:
            db.exec_driver_sql(f"SET LOCAL ROLE {role}")
            identifier = uuid.uuid4()
            reserve(db, identifier)
            user(db, identifier)
        assert error.value.orig.sqlstate == "55000"
        with registry.engine.begin() as db:
            ready(db)
        with pytest.raises(DBAPIError) as error, registry.engine.begin() as db:
            db.exec_driver_sql(f"SET LOCAL ROLE {role}")
            user(db, uuid.uuid4())
        assert error.value.orig.sqlstate == "23514"
        with registry.engine.begin() as db:
            db.exec_driver_sql(f"SET LOCAL ROLE {role}")
            identifier = uuid.uuid4()
            reserve(db, identifier)
            user(db, identifier)
            db.execute(User.__table__.update().values(updated_at=User.updated_at))
    finally:
        with local_postgres.begin() as db:
            db.exec_driver_sql(f"DROP OWNED BY {role}")
            db.exec_driver_sql(f"DROP ROLE {role}")


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_stale_ready_snapshot_cannot_bypass_maintenance(registry, isolation):
    with registry.engine.begin() as db:
        ready(db)
    snapshot_taken = threading.Event()
    state_changed = threading.Event()
    outcomes = []

    def insert_after_snapshot():
        try:
            with registry.engine.connect().execution_options(isolation_level=isolation) as db, db.begin():
                assert db.scalar(sa.select(P.c.status)) == "ready"
                snapshot_taken.set()
                assert state_changed.wait(10)
                identifier = uuid.uuid4()
                reserve(db, identifier)
                user(db, identifier)
        except DBAPIError as error:
            outcomes.append(error.orig.sqlstate)

    def maintenance():
        assert snapshot_taken.wait(10)
        try:
            with registry.engine.begin() as db:
                db.execute(P.update().values(status="building"))
        finally:
            state_changed.set()

    run_threads(insert_after_snapshot, maintenance)
    assert outcomes == ["55000" if isolation == "READ COMMITTED" else "40001"]
    with registry.engine.connect() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(R)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 1


def test_undrained_maintenance_deadlock_rolls_back_losing_transaction(registry):
    """Demonstrate why Phase 1 maintenance must disable AND drain writers.

    This intentionally unsafe overlap exists only in a throwaway schema. It is
    not a registration service, backfill, or approved maintenance protocol.
    """
    with registry.engine.begin() as db:
        ready(db)
        # Let PostgreSQL detect the cycle before our bounded safety timeouts.
        assert int(db.scalar(sa.text(
            "SELECT setting FROM pg_settings WHERE name='deadlock_timeout'"
        ))) <= 2000
    candidate = uuid.uuid4()
    reservation_inserted = threading.Event()
    policy_locked = threading.Event()
    outcomes = {}

    def registration():
        try:
            with registry.engine.begin() as db:
                db.exec_driver_sql("SET LOCAL lock_timeout='8s'")
                db.exec_driver_sql("SET LOCAL statement_timeout='12s'")
                reserve(db, candidate)
                reservation_inserted.set()
                assert policy_locked.wait(5)
                # AFTER INSERT now waits for maintenance's policy row lock.
                user(db, candidate)
            outcomes["registration"] = "committed"
        except DBAPIError as error:
            assert error.orig.sqlstate == "40P01"
            outcomes["registration"] = "deadlock"

    def maintenance():
        assert reservation_inserted.wait(5)
        try:
            with registry.engine.begin() as db:
                db.exec_driver_sql("SET LOCAL lock_timeout='8s'")
                db.exec_driver_sql("SET LOCAL statement_timeout='12s'")
                db.execute(P.update().values(status="building"))
                policy_locked.set()
                # The unique index waits for registration's uncommitted key.
                reserve(db, None, state="blocked")
            outcomes["maintenance"] = "committed"
        except DBAPIError as error:
            assert error.orig.sqlstate == "40P01"
            outcomes["maintenance"] = "deadlock"

    run_threads(registration, maintenance)
    assert sorted(outcomes.values()) == ["committed", "deadlock"]
    with registry.engine.connect() as db:
        reservations = db.execute(sa.select(R.c.state, R.c.user_id)).all()
        users = set(db.scalars(sa.select(User.id)))
        if outcomes["registration"] == "committed":
            assert db.scalar(sa.select(P.c.status)) == "ready"
            assert reservations == [("owned", candidate)]
            assert users == {registry.legacy, candidate}
        else:
            assert db.scalar(sa.select(P.c.status)) == "building"
            assert reservations == [("blocked", None)]
            assert users == {registry.legacy}


def test_deferred_foreign_key_is_enforced_when_forced(registry):
    with pytest.raises(DBAPIError) as error, registry.engine.begin() as db:
        reserve(db, uuid.uuid4())
        db.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    assert error.value.orig.sqlstate == "23503"


@pytest.mark.parametrize("values", [
    {"state": "blocked", "user_id": "owner"},
    {"state": "owned", "user_id": None},
    {"state": "unknown", "user_id": None},
    {"policy_version": 2, "user_id": "owner"},
])
def test_reservation_ownership_and_policy_constraints(registry, values):
    values = {key: registry.legacy if value == "owner" else value for key, value in values.items()}
    owner = values.pop("user_id")
    with pytest.raises(DBAPIError), registry.engine.begin() as db:
        reserve(db, owner, **values)


@pytest.mark.parametrize("values", [
    {"id": uuid.UUID("00000000-0000-0000-0000-000000000002")},
    {"policy_version": 2}, {"status": "invalid"}, {"users_processed": -1},
    {"source_count": -1}, {"manifest_sha256": b"short"},
    {"status": "ready"},
    {"status": "ready", "source_count": 1, "manifest_sha256": b"x" * 32},
])
def test_policy_state_constraints(registry, values):
    with pytest.raises(DBAPIError), registry.engine.begin() as db:
        db.execute(P.update().values(**values))


def test_lookup_has_usable_unique_index_without_user_scan(registry):
    with registry.engine.begin() as db:
        reserve(db, registry.legacy)
        # An empty/small fixture may legitimately choose a sequential scan;
        # disabling that option here verifies the intended index is usable.
        db.exec_driver_sql("SET LOCAL enable_seqscan=off")
        plan = db.exec_driver_sql(
            "EXPLAIN SELECT user_id FROM email_identity_reservations "
            "WHERE lookup_key = 'new@example.test' COLLATE \"C\" AND state='owned'"
        ).scalars().all()
        assert any("uq_eir_lookup_key" in line for line in plan)
        assert not any("users" in line or "Seq Scan" in line for line in plan)


def test_full_migration_chain_upgrade_and_downgrade(local_postgres):
    from pathlib import Path
    from alembic.script import ScriptDirectory

    schema = "email_chain_" + uuid.uuid4().hex
    scripts = ScriptDirectory(str(Path(__file__).parents[1] / "alembic"))
    revisions = list(reversed(list(scripts.walk_revisions())))
    with local_postgres.begin() as db:
        db.exec_driver_sql("CREATE SCHEMA " + schema)
    try:
        with local_postgres.begin() as db:
            db.exec_driver_sql("SET LOCAL search_path=" + schema)
            with Operations.context(MigrationContext.configure(db, opts={"version_table_schema": schema})):
                for revision in revisions:
                    revision.module.upgrade()
                assert db.scalar(sa.select(P.c.status)) == "building"
                for revision in reversed(revisions):
                    revision.module.downgrade()
            assert sa.inspect(db).get_table_names(schema=schema) == []
            assert db.scalar(sa.text("SELECT count(*) FROM pg_proc JOIN pg_namespace n ON n.oid=pronamespace WHERE n.nspname=:schema"), {"schema": schema}) == 0
    finally:
        with local_postgres.begin() as db:
            db.exec_driver_sql("DROP SCHEMA " + schema + " CASCADE")


def test_before_trigger_cannot_hide_email_changes(registry):
    with registry.engine.begin() as db:
        db.exec_driver_sql(f"""
CREATE FUNCTION {registry.schema}.test_change_email() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.email := 'changed@example.test'; RETURN NEW; END $$;
CREATE TRIGGER test_change_email BEFORE UPDATE ON users FOR EACH ROW
EXECUTE FUNCTION {registry.schema}.test_change_email();
""")
    with pytest.raises(DBAPIError) as error, registry.engine.begin() as db:
        db.execute(User.__table__.update().values(updated_at=User.updated_at))
    assert error.value.orig.sqlstate == "23514"
    with registry.engine.connect() as db:
        assert db.scalar(sa.select(User.email)) == "Σ@παράδειγμα.test"
