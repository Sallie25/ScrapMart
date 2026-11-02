"""Explicit opt-in tests against the fixed disposable local Docker database.

No settings/environment files or configurable database URLs are used. Container,
identity, public revision/schema/data are checked BEFORE creating temporary schemas.
"""
import inspect
import json
import os
import subprocess
import threading
import time
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionAuthenticationError, SessionService
from app.modules.buyers.models import BuyerProfile
from tests import test_auth_sessions as functional


pytestmark = pytest.mark.skipif(
    os.environ.get("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS") != "1",
    reason="Requires explicit disposable local PostgreSQL opt-in",
)


@pytest.fixture(scope="module")
def local_postgres():
    inspected = subprocess.run(
        ["docker", "inspect", "scrapmart-postgres-test", "--format",
         '{{json .Name}}\n{{json .Config.Image}}\n{{json .NetworkSettings.Ports}}\n{{json .NetworkSettings.Networks}}'],
        capture_output=True, text=True, check=True, timeout=10,
    )
    name, image, ports, networks = [json.loads(line) for line in inspected.stdout.splitlines()]
    assert name == "/scrapmart-postgres-test" and image == "postgres:16-alpine"
    assert ports == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]}
    addresses = {network["IPAddress"] for network in networks.values()}
    url = sa.URL.create(
        "postgresql+psycopg", username="scrapmart_test", password="local_test_only",
        host="127.0.0.1", port=55432, database="scrapmart_test",
    )
    engine = sa.create_engine(url, hide_parameters=True, connect_args={
        "connect_timeout": 5, "options": "-c statement_timeout=15000 -c lock_timeout=10000",
    })
    try:
        with engine.connect() as connection:
            identity = connection.execute(sa.text(
                "SELECT current_database(),current_user,current_setting('server_version_num')::int,"
                "host(inet_server_addr()),inet_server_port(),pg_is_in_recovery()"
            )).one()
            assert identity[0] == identity[1] == "scrapmart_test"
            assert 160000 <= identity[2] < 170000
            assert identity[3] in addresses and identity[4] == 5432 and not identity[5]
            expected = {"alembic_version", "users", "vendors", "categories", "listings",
                        "listing_images", "buyer_profiles", "auth_sessions", "refresh_tokens"}
            assert set(sa.inspect(connection).get_table_names(schema="public")) == expected
            assert connection.execute(sa.text("SELECT version_num FROM public.alembic_version")).scalars().all() == ["b81d4f2a9c06"]
            assert not connection.execute(sa.text(
                "SELECT nspname FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') "
                "AND nspname NOT LIKE 'pg_%'"
            )).first(), "Unexpected schemas: stop before test writes"
            for table in expected - {"alembic_version"}:
                assert connection.execute(sa.text("SELECT count(*) FROM public." + table)).scalar_one() == 0, "Unexpected application data: stop before test writes"
        yield engine
        with engine.connect() as connection:
            for table in expected - {"alembic_version"}:
                assert connection.execute(sa.text("SELECT count(*) FROM public." + table)).scalar_one() == 0
    finally:
        engine.dispose()


@pytest.fixture
def store(local_postgres):
    schema = "stage2b_validation_" + uuid.uuid4().hex
    with local_postgres.begin() as connection:
        connection.execute(sa.text("CREATE SCHEMA " + schema))
    engine = sa.create_engine(local_postgres.url, hide_parameters=True, connect_args={
        "connect_timeout": 5,
        "options": "-c search_path=" + schema + " -c statement_timeout=15000 -c lock_timeout=10000",
    })
    try:
        User.metadata.create_all(engine, tables=[User.__table__, BuyerProfile.__table__, AuthSession.__table__, RefreshToken.__table__])
        yield functional.make_store(engine)
    finally:
        engine.dispose()
        with local_postgres.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA " + schema + " CASCADE"))


@pytest.mark.parametrize("name", [
    "test_create_commits_digest_only_absolute_expiry_and_no_profile",
    "test_credentials_follow_actual_commit_and_retries_use_new_sessions",
    "test_configurable_lifetime", "test_inactive_identity_rejected_everywhere",
    "test_access_identity_and_ownership",
    "test_rotation_retains_consumed_digest_without_extending_expiry",
    "test_single_revocation_idempotency_and_ownership",
    "test_logout_all_only_active_sessions_for_identity",
    "test_rotation_failure_rolls_back_consumption_and_insert",
    "test_no_credentials_returned_when_commit_fails",
    "test_replay_commit_failure_is_persistence_error_not_success",
    "test_reject_shared_session_without_rolling_back_caller_work",
    "test_user_lock_preserves_identity_fields",
    "test_logout_all_does_not_revoke_expired_sessions",
    "test_naive_clock_fails_without_persistence",
    "test_exhausted_serialization_retries_roll_back",
])
def test_functional_postgresql(store, monkeypatch, name):
    function = getattr(functional, name)
    if "monkeypatch" in inspect.signature(function).parameters:
        function(store, monkeypatch)
    else:
        function(store)


@pytest.mark.parametrize("state", ["active", "inactive", "expired"])
def test_replay_postgresql(store, state):
    functional.test_reuse_commits_revocation_even_when_rejected(store, state)


@pytest.mark.parametrize("state", ["expired", "revoked", "future"])
def test_session_eligibility_postgresql(store, state):
    functional.test_ineligible_sessions_reject_access_and_rotation(store, state)


@pytest.mark.parametrize("state", ["expired", "future", "beyond_session"])
def test_token_eligibility_postgresql(store, state):
    functional.test_invalid_refresh_record_rejected(store, state)


def run_threads(*functions):
    errors = []

    def guarded(function):
        try:
            function()
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=guarded, args=(function,), daemon=True,
                                name="stage2b-worker-" + str(index))
               for index, function in enumerate(functions)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(25)
    assert not any(thread.is_alive() for thread in threads), "Concurrency test timed out"
    assert not errors, [type(error).__name__ for error in errors]


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_concurrent_rotation_commits_replay_revocation(store, isolation):
    service = SessionService(store.engine.execution_options(isolation_level=isolation), settings=store.settings)
    first = service.create_session(store.user_id)
    barrier = threading.Barrier(2)
    local = threading.local()
    successes, rejections = [], []

    def synchronize_lookup(connection, cursor, statement, parameters, context, executemany):
        if (
            threading.current_thread().name.startswith("stage2b-worker-")
            and "JOIN auth_sessions" in statement and "refresh_tokens.token_digest" in statement
            and not getattr(local, "looked_up", False)
        ):
            local.looked_up = True
            barrier.wait(timeout=10)

    sa.event.listen(store.engine, "after_cursor_execute", synchronize_lookup)
    try:
        def rotate():
            try:
                successes.append(service.rotate_refresh_token(first.refresh_token))
            except SessionAuthenticationError:
                rejections.append(True)
        run_threads(rotate, rotate)
    finally:
        sa.event.remove(store.engine, "after_cursor_execute", synchronize_lookup)
    assert len(successes) == len(rejections) == 1
    with store.factory() as db:
        assert db.get(AuthSession, first.session_id).revoked_at is not None
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 2
    with pytest.raises(SessionAuthenticationError):
        service.rotate_refresh_token(successes[0].refresh_token)
    with pytest.raises(SessionAuthenticationError):
        service.validate_access_session(functional.access_claims(successes[0]))


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_logout_all_waiting_for_creation_includes_new_session(store, isolation, monkeypatch):
    class ConcurrentSession(Session):
        pass

    monkeypatch.setattr("app.modules.auth.session_service.Session", ConcurrentSession)
    service = SessionService(store.engine.execution_options(isolation_level=isolation), settings=store.settings)
    service.create_session(store.user_id)
    creating, logging_out, release = threading.Event(), threading.Event(), threading.Event()
    created, revoked = [], []

    @sa.event.listens_for(ConcurrentSession, "before_commit")
    def hold_creation(db):
        if threading.current_thread().name == "stage2b-worker-0":
            creating.set()
            assert release.wait(10)

    def observe_logout(connection, cursor, statement, parameters, context, executemany):
        if threading.current_thread().name == "stage2b-worker-1" and statement.startswith("UPDATE users"):
            # Establish the stronger-isolation snapshot before releasing the
            # creator, rather than relying on thread scheduling at cursor.execute.
            connection.exec_driver_sql("SELECT 1")
            logging_out.set()

    sa.event.listen(store.engine, "before_cursor_execute", observe_logout)
    try:
        def create():
            created.append(service.create_session(store.user_id))

        def logout():
            assert creating.wait(10)
            # Separate releaser ensures the logout UPDATE begins before commit.
            def unblock():
                if logging_out.wait(10):
                    release.set()
            helper = threading.Thread(target=unblock, daemon=True)
            helper.start()
            revoked.append(service.revoke_all_sessions(store.user_id))
            helper.join(2)
        run_threads(create, logout)
    finally:
        release.set()
        sa.event.remove(store.engine, "before_cursor_execute", observe_logout)
    assert revoked == [2]
    with pytest.raises(SessionAuthenticationError):
        service.validate_access_session(functional.access_claims(created[0]))


def test_rotation_checks_expiry_after_waiting_for_lock(store):
    service = SessionService(store.engine, settings=store.settings)
    first = service.create_session(store.user_id)
    waiting, outcome = threading.Event(), []

    def observe(connection, cursor, statement, parameters, context, executemany):
        if threading.current_thread().name == "expiry-worker" and statement.startswith("UPDATE users"):
            waiting.set()

    def rotate():
        try:
            service.rotate_refresh_token(first.refresh_token)
            outcome.append("unexpected success")
        except SessionAuthenticationError:
            outcome.append("rejected")
        except Exception as error:
            outcome.append(type(error).__name__)

    sa.event.listen(store.engine, "before_cursor_execute", observe)
    try:
        with store.factory.begin() as db:
            db.execute(sa.update(User).where(User.id == store.user_id).values(updated_at=User.updated_at))
            token = functional.token_row(db, first.refresh_token)
            token.expires_at = db.scalar(sa.select(sa.func.clock_timestamp())) + functional.timedelta(seconds=1)
            db.flush()
            worker = threading.Thread(target=rotate, daemon=True, name="expiry-worker")
            worker.start()
            assert waiting.wait(10)
            time.sleep(1.2)
        worker.join(15)
        assert not worker.is_alive()
    finally:
        sa.event.remove(store.engine, "before_cursor_execute", observe)
    assert outcome == ["rejected"]


def test_default_clock_is_timezone_aware_database_time(store):
    service = SessionService(store.engine, settings=store.settings)
    with store.factory() as db:
        before = db.scalar(sa.select(sa.func.clock_timestamp()))
    credentials = service.create_session(store.user_id)
    with store.factory() as db:
        after = db.scalar(sa.select(sa.func.clock_timestamp()))
        session = db.get(AuthSession, credentials.session_id)
        assert before <= session.created_at <= after
        assert session.expires_at - session.created_at == functional.timedelta(days=7)


@pytest.mark.parametrize("mode", [None, "create_savepoint", "control_fully"])
def test_external_transaction_rejection_postgresql(store, mode):
    functional.test_reject_external_transaction_without_touching_caller_work(store, mode)


def test_autocommit_rejected_postgresql(store):
    functional.test_autocommit_rejected_before_writes(store, "options")
