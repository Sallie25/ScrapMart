"""Opt-in registration tests, using only the established disposable PostgreSQL."""
import inspect
import os
import threading
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.database.base import Base
from app.main import create_app
from app.modules.auth.models import User
from app.modules.auth.registration_schemas import BuyerSignupRequest
from app.modules.auth.registration_service import BuyerRegistrationService
from app.modules.auth.signup_rate_limit import SignupRateLimiter
from tests import test_buyer_signup as functional
from tests.test_auth_sessions_postgresql import local_postgres, run_threads
from tests.test_email_identity_schema import migration
from app.modules.auth.email_identity_backfill import EmailIdentityBackfill, IsolatedMaintenanceContext, APPROVED_FINGERPRINT
from app.modules.auth.email_identity_finalization import LocalEmailIdentityFinalizer
from app.modules.auth.email_identity_models import EmailIdentityReservation as Reservation, EmailIdentityPolicyState as Policy, POLICY_STATE_ID

pytestmark = pytest.mark.skipif(
    os.environ.get("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS") != "1",
    reason="Requires explicit disposable local PostgreSQL opt-in",
)


@pytest.fixture
def signup_store(local_postgres, monkeypatch):
    # The reused module fixture checks Docker identity, server identity, revision,
    # public tables, emptiness and absence of extra schemas before any writes.
    with local_postgres.connect() as db:
        names = db.execute(sa.text("SELECT datname FROM pg_database")).scalars().all()
        assert set(names) == {"postgres", "template0", "template1", "scrapmart_test"}
    schema = "email_backfill_" + uuid.uuid4().hex
    with local_postgres.begin() as db:
        db.exec_driver_sql("CREATE SCHEMA " + schema)
    engine = sa.create_engine(local_postgres.url, hide_parameters=True, connect_args={
        "connect_timeout": 5,
        "options": "-c search_path=" + schema + " -c statement_timeout=15000 -c lock_timeout=10000",
    })
    try:
        Base.metadata.create_all(engine, tables=functional.TABLES)
        def install_registry():
            with engine.begin() as db:
                with Operations.context(MigrationContext.configure(db, opts={"version_table_schema": schema})):
                    migration().upgrade()
            with IsolatedMaintenanceContext(schema, expected_fingerprint=APPROVED_FINGERPRINT) as maintenance:
                backfill = EmailIdentityBackfill(maintenance)
                progress = backfill.prepare()
                while not progress.source_exhausted:
                    progress = backfill.run_batch()
                LocalEmailIdentityFinalizer(maintenance).finalize()

        install_registry()

        def seed_legacy(**values):
            # Legacy data belongs before guard installation, never bypassed during signup.
            with engine.begin() as db:
                assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 0
                with Operations.context(MigrationContext.configure(db, opts={"version_table_schema": schema})):
                    migration().downgrade()
            with Session(engine) as db, db.begin():
                user = User(**values)
                db.add(user)
                db.flush()
                identifier = user.id
            install_registry()
            return identifier

        settings = Settings(_env_file=None, _secrets_dir=None, auth_allowed_origins=[functional.ORIGIN])
        monkeypatch.setattr("app.main.get_settings", lambda: settings)
        monkeypatch.setattr("app.api.v1.buyer_signup.get_engine", lambda: engine)
        redis = functional.FakeRedis()
        limiter = SignupRateLimiter(redis, functional.KEY)
        monkeypatch.setattr("app.api.v1.buyer_signup.get_signup_rate_limiter", lambda: limiter)
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        with TestClient(app, client=("127.0.0.1", 34567)) as client:
            yield SimpleNamespace(engine=engine, schema=schema, seed_legacy=seed_legacy, settings=settings, redis=redis, limiter=limiter, client=client, app=app)
    finally:
        engine.dispose()
        with local_postgres.begin() as db:
            db.exec_driver_sql("DROP SCHEMA " + schema + " CASCADE")
        with local_postgres.connect() as db:
            assert db.scalar(sa.text("SELECT count(*) FROM pg_namespace WHERE nspname=:name"), {"name": schema}) == 0


@pytest.mark.parametrize("name", [
    "test_success_atomic_no_automatic_login",
    "test_duplicate_case_variants_identical_response_no_linking",
    "test_existing_user_profiles_remain_unchanged",
    "test_serialization_retries_independent_registration_transactions",
    "test_registration_rolls_back_partial_insert",
    "test_registration_commit_failure_never_acknowledged",
    "test_registration_rejects_caller_resources_and_autocommit",
])
def test_registration_postgresql(signup_store, monkeypatch, name):
    function = getattr(functional, name)
    kwargs = {"monkeypatch": monkeypatch} if "monkeypatch" in inspect.signature(function).parameters else {}
    function(signup_store, **kwargs)


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_concurrent_case_variant_registration(signup_store, isolation):
    engine = signup_store.engine.execution_options(isolation_level=isolation)
    service = BuyerRegistrationService(engine)
    barrier = threading.Barrier(2)
    local = threading.local()
    outcomes = []
    arrivals = []

    def synchronize(connection, cursor, statement, parameters, context, executemany):
        if "email_identity_reservations.lookup_key IN" in statement and not getattr(local, "looked_up", False):
            local.looked_up = True
            arrivals.append(threading.get_ident())
            barrier.wait(10)

    sa.event.listen(signup_store.engine, "after_cursor_execute", synchronize)
    try:
        def register(email):
            service.register(BuyerSignupRequest.model_validate(functional.payload(email=email)))
            outcomes.append("acknowledged")
        run_threads(lambda: register("Race@Example.Test"), lambda: register(" RACE@example.test "))
    finally:
        sa.event.remove(signup_store.engine, "after_cursor_execute", synchronize)
    assert outcomes == ["acknowledged", "acknowledged"]
    assert len(arrivals) == len(set(arrivals)) == 2
    assert functional.counts(engine) == [1, 1, 0, 0, 0]
    with Session(engine) as db:
        assert db.scalar(sa.select(User.email)) == "race@example.test"


@pytest.mark.parametrize("email,expected", [
    ("buyer@example.test", "buyer@example.test"),
    (" BUYER@Example.Test ", "buyer@example.test"),
    ("buyer@xn--bcher-kva.test", "buyer@xn--bcher-kva.test"),
])
def test_ascii_email_policy_postgresql(signup_store, email, expected):
    functional.test_ascii_email_policy(signup_store, email, expected)


@pytest.mark.parametrize("email", ["ΟΣ@example.test", "İ@example.test", "K@example.test", "buyer@bücher.test"])
def test_unicode_email_rejected_postgresql(signup_store, email):
    functional.test_non_ascii_email_rejected_before_normalization(signup_store, email)


@pytest.mark.parametrize("legacy,candidate", [
    ("K@example.test", "k@example.test"),
    ("BUYER@BÜCHER.test", "buyer@xn--bcher-kva.test"),
    ("İ@example.test", "i@example.test"),
])
def test_legacy_unicode_collision_postgresql(signup_store, legacy, candidate):
    functional.test_legacy_unicode_ascii_alias_collision_no_new_identity(signup_store, legacy, candidate)


def test_international_name_password_postgresql(signup_store):
    functional.test_international_password_and_full_name_preserved(signup_store)


@pytest.mark.parametrize("name,args", [
    ("test_complete_punycode_bundle", ("buyer@xn--fa-hia.test", [("buyer@fass.test", "blocked"), ("buyer@xn--fa-hia.test", "owned")])),
    ("test_complete_punycode_bundle", ("buyer@xn--i-9bb.test", [("buyer@i.test", "blocked"), ("buyer@xn--i-9bb.test", "owned")])),
    ("test_complete_punycode_bundle", ("buyer@xn--3xa.test", [("buyer@xn--3xa.test", "owned"), ("buyer@xn--4xa.test", "blocked")])),
    ("test_conservative_overlap_changes_nothing", ("buyer@fass.test", "buyer@xn--fa-hia.test")),
    ("test_conservative_overlap_changes_nothing", ("buyer@xn--fa-hia.test", "buyer@fass.test")),
    ("test_unready_registry_never_acknowledges", ("missing",)),
    ("test_unready_registry_never_acknowledges", ("building",)),
    ("test_second_alias_failure_rolls_back_everything", ()),
])
def test_reservation_regressions(signup_store, name, args):
    getattr(functional, name)(signup_store, *args)


@pytest.mark.parametrize("persisted", [False, True])
def test_unknown_commit_postgresql(signup_store, monkeypatch, persisted):
    functional.test_uncertain_commit_has_no_automatic_retry(signup_store, monkeypatch, persisted)


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_concurrent_overlapping_bundles(signup_store, isolation):
    engine = signup_store.engine.execution_options(isolation_level=isolation)
    barrier, local, lookups = threading.Barrier(2), threading.local(), []
    def synchronize(connection, cursor, statement, parameters, context, many):
        if "email_identity_reservations.lookup_key IN" in statement and not getattr(local, "seen", False):
            local.seen = True
            lookups.append(1)
            barrier.wait(10)
    sa.event.listen(signup_store.engine, "after_cursor_execute", synchronize)
    try:
        def register(email):
            BuyerRegistrationService(engine).register(BuyerSignupRequest.model_validate(functional.payload(email=email)))
        run_threads(lambda: register("buyer@fass.test"), lambda: register("buyer@xn--fa-hia.test"))
    finally:
        sa.event.remove(signup_store.engine, "after_cursor_execute", synchronize)
    assert len(lookups) == 2
    assert functional.counts(engine) == [1, 1, 0, 0, 0]
    rows = functional.reservation_rows(engine)
    with Session(engine) as db:
        email = db.scalar(sa.select(User.email))
    assert len(rows) == (2 if email == "buyer@xn--fa-hia.test" else 1)


def test_bad_policy_version_and_missing_reservation_fail_closed(signup_store):
    with signup_store.engine.begin() as db:
        db.exec_driver_sql("ALTER TABLE email_identity_policy_state DROP CONSTRAINT ck_eips_policy_version")
        db.execute(Policy.__table__.update().values(policy_version=2))
    assert functional.post(signup_store).status_code == 503
    with signup_store.engine.begin() as db:
        db.execute(Policy.__table__.update().values(policy_version=1))
    assert functional.post(signup_store).status_code == 202
    with signup_store.engine.begin() as db:
        db.execute(Reservation.__table__.delete())  # Trusted corruption of private fixture only.
    assert functional.post(signup_store).status_code == 503  # User unique violation is NOT duplicate success.
    assert functional.reservation_rows(signup_store.engine) == []
    assert functional.counts(signup_store.engine) == [1, 1, 0, 0, 0]


def test_indexed_lookup_and_no_user_scan(signup_store):
    statements = []
    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    sa.event.listen(signup_store.engine, "before_cursor_execute", observe)
    try:
        assert functional.post(signup_store).status_code == 202
    finally:
        sa.event.remove(signup_store.engine, "before_cursor_execute", observe)
    assert not any("FROM users" in sql for sql in statements)
    lock = next(i for i,s in enumerate(statements) if "FOR SHARE" in s and "email_identity_policy_state" in s)
    lookup = next(i for i,s in enumerate(statements) if "email_identity_reservations.lookup_key IN" in s)
    reservation = next(i for i,s in enumerate(statements) if s.startswith("INSERT INTO email_identity_reservations"))
    user = next(i for i,s in enumerate(statements) if s.startswith("INSERT INTO users"))
    assert lock < lookup < reservation < user
    with signup_store.engine.begin() as db:
        db.exec_driver_sql("SET LOCAL enable_seqscan=off")
        plan = db.exec_driver_sql("EXPLAIN SELECT id FROM email_identity_reservations WHERE lookup_key IN ('buyer@example.test') LIMIT 1").all()
    assert "uq_eir_lookup_key" in str(plan)


def test_restricted_runtime_grants_and_immutable_ids(signup_store, monkeypatch):
    from sqlalchemy.exc import DBAPIError
    role = "email_runtime_" + uuid.uuid4().hex
    schema = signup_store.schema
    with signup_store.engine.begin() as db:
        db.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS")
    try:
        with signup_store.engine.begin() as db:
            db.exec_driver_sql(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
            for table in ("users", "buyer_profiles", "email_identity_reservations", "email_identity_policy_state"):
                db.exec_driver_sql(f"GRANT SELECT ON {schema}.{table} TO {role}")
            db.exec_driver_sql(f"GRANT INSERT (id,email,password_hash,full_name,phone_number,role,is_active) ON {schema}.users TO {role}")
            db.exec_driver_sql(f"GRANT INSERT (id,user_id,created_at,signup_completed_at) ON {schema}.buyer_profiles TO {role}")
            db.exec_driver_sql(f"GRANT INSERT (id,lookup_key,user_id,state) ON {schema}.email_identity_reservations TO {role}")
            for table in ("email_identity_reservations", "email_identity_policy_state"):
                db.exec_driver_sql(f"GRANT UPDATE (id) ON {schema}.{table} TO {role}")
        class RuntimeSession(Session):
            pass
        @sa.event.listens_for(RuntimeSession, "after_begin")
        def runtime(db, transaction, connection):
            connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
            assert connection.scalar(sa.text("SELECT current_user")) == role
        monkeypatch.setattr("app.modules.auth.registration_service.Session", RuntimeSession)
        assert functional.post(signup_store, functional.payload(email="buyer@xn--fa-hia.test")).status_code == 202
        before = functional.reservation_rows(signup_store.engine)
        with signup_store.engine.connect() as db:
            ids_before = db.execute(sa.select(Reservation.id).order_by(Reservation.id)).all()
        mutations = [
            ("UPDATE email_identity_reservations SET id=gen_random_uuid()", "23514"),
            ("UPDATE email_identity_policy_state SET id=gen_random_uuid()", "23514"),
            ("UPDATE email_identity_reservations SET user_id=NULL", "42501"),
            ("UPDATE email_identity_reservations SET lookup_key='changed@example.test'", "42501"),
            ("UPDATE email_identity_reservations SET state='blocked'", "42501"),
            ("UPDATE email_identity_reservations SET policy_version=1", "42501"),
            ("UPDATE email_identity_policy_state SET status='building'", "42501"),
            ("UPDATE email_identity_policy_state SET users_processed=0", "42501"),
            ("DELETE FROM email_identity_reservations", "42501"),
            ("TRUNCATE email_identity_reservations", "42501"),
            ("DELETE FROM email_identity_policy_state", "42501"),
            ("DELETE FROM users", "42501"),
            ("ALTER TABLE users DISABLE TRIGGER ALL", "42501"),
            ("CREATE TABLE forbidden_table(id integer)", "42501"),
            ("SET LOCAL session_replication_role=replica", "42501"),
        ]
        for statement, code in mutations:
            with pytest.raises(DBAPIError) as error:
                with signup_store.engine.begin() as db:
                    db.exec_driver_sql(f"SET LOCAL ROLE {role}")
                    db.exec_driver_sql(statement)
            assert error.value.orig.sqlstate == code
        assert functional.reservation_rows(signup_store.engine) == before
        with signup_store.engine.connect() as db:
            assert db.execute(sa.select(Reservation.id).order_by(Reservation.id)).all() == ids_before
            assert db.scalar(sa.select(Policy.status)) == "ready"
        # Show each narrow grant is necessary, not hidden by an owner connection.
        for table in ("email_identity_policy_state", "email_identity_reservations"):
            with signup_store.engine.begin() as db:
                db.exec_driver_sql(f"REVOKE UPDATE (id) ON {schema}.{table} FROM {role}")
            assert functional.post(signup_store, functional.payload(email="new@example.test")).status_code == 503
            with signup_store.engine.begin() as db:
                db.exec_driver_sql(f"GRANT UPDATE (id) ON {schema}.{table} TO {role}")
            assert functional.reservation_rows(signup_store.engine) == before
            assert functional.counts(signup_store.engine) == [1, 1, 0, 0, 0]
    finally:
        with signup_store.engine.begin() as db:
            db.exec_driver_sql(f"DROP OWNED BY {role}")
            db.exec_driver_sql(f"DROP ROLE {role}")


def test_stage2b_sessions_after_registration(signup_store):
    from app.modules.auth.session_service import SessionService, SessionAuthenticationError
    assert functional.post(signup_store).status_code == 202
    with Session(signup_store.engine) as db:
        identifier = db.scalar(sa.select(User.id))
    service = SessionService(signup_store.engine, settings=signup_store.settings)
    initial = service.create_session(identifier)
    replacement = service.rotate_refresh_token(initial.refresh_token)
    with pytest.raises(SessionAuthenticationError):
        service.rotate_refresh_token(initial.refresh_token)
    with pytest.raises(SessionAuthenticationError):
        service.rotate_refresh_token(replacement.refresh_token)
    service.create_session(identifier)
    service.revoke_all_sessions(identifier)


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_readiness_transition_waits_for_signup(signup_store, monkeypatch, isolation):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.exc import DBAPIError
    from app.modules.buyers.models import BuyerProfile
    engine = signup_store.engine.execution_options(isolation_level=isolation)
    monkeypatch.setattr("app.api.v1.buyer_signup.get_engine", lambda: engine)
    observations = []
    def before_profile(mapper, connection, target):
        def maintenance():
            with pytest.raises(DBAPIError) as error:
                with signup_store.engine.begin() as other:
                    other.exec_driver_sql("SET LOCAL lock_timeout='100ms'")
                    other.execute(Policy.__table__.update().values(status="building"))
            observations.append(error.value.orig.sqlstate)
        with ThreadPoolExecutor() as pool:
            pool.submit(maintenance).result(timeout=10)
    sa.event.listen(BuyerProfile, "before_insert", before_profile)
    try:
        assert functional.post(signup_store).status_code == 202
    finally:
        sa.event.remove(BuyerProfile, "before_insert", before_profile)
    assert observations == ["55P03"]
    with signup_store.engine.begin() as db:
        db.execute(Policy.__table__.update().values(status="building"))
    assert functional.post(signup_store, functional.payload(email="new@example.test")).status_code == 503
    assert functional.counts(engine) == [1, 1, 0, 0, 0]
