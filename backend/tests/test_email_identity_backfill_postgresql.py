"""Opt-in Step 2 components in private disposable schemas, never public DDL.

No production freeze claim: the isolated context deliberately blocks all User
writes while held. Production selective-freeze/role provisioning is unresolved.
"""
import os
from concurrent.futures import ThreadPoolExecutor
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.modules.auth.email_identity_backfill import (
    APPROVED_FINGERPRINT, BackfillError, CheckpointRejected, CommitOutcomeUnknown,
    EmailIdentityBackfill, IsolatedMaintenanceContext, MaintenanceRequired, SourceRejected,
)
from app.modules.auth.email_identity_models import EmailIdentityPolicyState, EmailIdentityReservation
from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionService, SessionAuthenticationError
from app.modules.buyers.models import BuyerProfile
from tests.test_auth_sessions_postgresql import local_postgres
from tests.test_email_identity_schema import migration

pytestmark = pytest.mark.skipif(os.environ.get("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS") != "1", reason="Requires explicit verified disposable local PostgreSQL")
R = EmailIdentityReservation.__table__
P = EmailIdentityPolicyState.__table__


@pytest.fixture
def database(local_postgres):
    stores = []
    with local_postgres.connect() as db:
        assert set(db.scalars(sa.text("SELECT datname FROM pg_database"))) == {"postgres", "template0", "template1", "scrapmart_test"}

    def create(emails=()):
        schema = "email_backfill_" + uuid.uuid4().hex
        with local_postgres.begin() as db:
            db.exec_driver_sql("CREATE SCHEMA " + schema)
        engine = sa.create_engine(local_postgres.url, hide_parameters=True, connect_args={
            "connect_timeout": 5, "options": f"-c search_path={schema} -c statement_timeout=15000 -c lock_timeout=3000",
        })
        store = SimpleNamespace(engine=engine, schema=schema)
        stores.append(store)
        User.metadata.create_all(engine, tables=[User.__table__, BuyerProfile.__table__, AuthSession.__table__, RefreshToken.__table__])
        with engine.begin() as db:
            # Reverse insertion order verifies native UUID keyset ordering.
            for number, email in reversed(list(enumerate(emails, 1))):
                db.execute(User.__table__.insert().values(id=uuid.UUID(int=number), email=email, full_name="Legacy 名", password_hash="test-only"))
            with Operations.context(MigrationContext.configure(db, opts={"version_table_schema": schema})):
                migration().upgrade()
        return store
    try:
        yield create
    finally:
        for store in stores:
            store.engine.dispose()
            with local_postgres.begin() as db:
                db.exec_driver_sql("DROP SCHEMA " + store.schema + " CASCADE")
                assert not db.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:s)"), {"s": store.schema})


def context(store, *, isolation_level="READ COMMITTED"):
    return IsolatedMaintenanceContext(store.schema, expected_fingerprint=APPROVED_FINGERPRINT, isolation_level=isolation_level)


def finish(worker):
    progress = worker.prepare()
    while not progress.source_exhausted:
        progress = worker.run_batch()
    assert worker.run_batch() == progress
    return progress


def state(store):
    with store.engine.connect() as db:
        return dict(db.execute(sa.select(P)).mappings().one())


def reservations(store):
    with store.engine.connect() as db:
        return db.execute(sa.select(R).order_by(R.c.lookup_key)).all()


@pytest.mark.parametrize("emails", [(), ("Buyer@example.test", "Σ@example.test", "person@bücher.test")])
def test_empty_nonempty_and_zero_alias_sources_remain_building(database, emails):
    store = database(emails)
    with store.engine.connect() as db:
        before = db.execute(sa.select(User.__table__).order_by(User.id)).all()
    with context(store) as maintenance:
        progress = finish(EmailIdentityBackfill(maintenance, batch_size=1))
        assert progress.users_processed == progress.source_count == len(emails)
        assert progress.last_user_id == (uuid.UUID(int=len(emails)) if emails else None)
    assert state(store)["status"] == "building"
    with store.engine.connect() as db:
        assert db.execute(sa.select(User.__table__).order_by(User.id)).all() == before
        assert db.scalar(sa.select(sa.func.count()).select_from(AuthSession)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(BuyerProfile)) == 0
    # Reopening after full source exhaustion is still just resume, not readiness.
    with context(store) as maintenance:
        assert finish(EmailIdentityBackfill(maintenance)) == progress


@pytest.mark.parametrize("batch_size", [1, 2, 500])
def test_same_batch_cross_batch_conflicts_and_permanent_blocking(database, batch_size):
    store = database(["Buyer@example.test", "buyer@example.test", "BUYER@example.test", "i@example.test", "İ@example.test", "person@faß.test"])
    with context(store) as maintenance:
        finish(EmailIdentityBackfill(maintenance, batch_size=batch_size))
    actual = {row.lookup_key: (row.state, row.user_id) for row in reservations(store)}
    assert actual == {
        "buyer@example.test": ("blocked", None), "i@example.test": ("blocked", None),
        "person@fass.test": ("blocked", None), "person@xn--fa-hia.test": ("owned", uuid.UUID(int=6)),
    }
    before = reservations(store)
    with context(store) as maintenance:
        finish(EmailIdentityBackfill(maintenance, batch_size=2))
    assert reservations(store) == before


@pytest.mark.parametrize("bad", ["bad", "person@" + "ß" * 32 + ".test"])
def test_invalid_tail_preflight_writes_nothing(database, bad):
    store = database(["first@example.test", bad])
    before = state(store)
    with context(store) as maintenance:
        with pytest.raises(SourceRejected):
            EmailIdentityBackfill(maintenance, batch_size=1).prepare()
    assert state(store) == before
    assert reservations(store) == []


def test_interrupt_between_batches_resume_matches_uninterrupted(database):
    emails = ["Buyer@example.test", "buyer@example.test", "Σ@example.test", "person@bücher.test"]
    interrupted, reference = database(emails), database(emails)
    with context(interrupted) as maintenance:
        worker = EmailIdentityBackfill(maintenance, batch_size=1)
        worker.prepare()
        partial = worker.run_batch()
        assert partial.users_processed == 1
    with context(interrupted) as maintenance:
        resumed = EmailIdentityBackfill(maintenance, batch_size=2)
        assert resumed.prepare() == partial
        while not resumed.run_batch().source_exhausted:
            pass
        result = resumed.run_batch()
    with context(reference) as maintenance:
        expected = finish(EmailIdentityBackfill(maintenance, batch_size=500))
    assert result == expected
    assert [(r.lookup_key, r.state, r.user_id) for r in reservations(interrupted)] == [(r.lookup_key, r.state, r.user_id) for r in reservations(reference)]


@pytest.mark.parametrize("corruption", ["digest", "count", "last", "source_count", "reservation"])
def test_resume_rejects_checkpoint_or_prefix_corruption(database, corruption):
    store = database(["one@example.test", "two@example.test"])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance, batch_size=1)
        worker.prepare()
        worker.run_batch()
    with store.engine.begin() as db:
        changes = {"digest": {"manifest_sha256": b"x" * 32}, "count": {"users_processed": 0},
                   "last": {"last_user_id": uuid.UUID(int=2)}, "source_count": {"source_count": 3}}
        if corruption == "reservation":
            db.execute(R.delete())  # Deliberate trusted-maintenance corruption.
        else:
            db.execute(P.update().values(**changes[corruption]))
    before = state(store), reservations(store)
    with context(store) as maintenance:
        with pytest.raises(CheckpointRejected):
            EmailIdentityBackfill(maintenance).prepare()
    assert (state(store), reservations(store)) == before


@pytest.mark.parametrize("change", ["delete", "id", "email"])
def test_source_changes_invalidate_even_zero_processed_checkpoint(database, change):
    store = database(["one@example.test", "two@example.test"])
    with context(store) as maintenance:
        EmailIdentityBackfill(maintenance).prepare()
    with store.engine.begin() as db:
        if change == "delete":
            db.execute(User.__table__.delete().where(User.id == uuid.UUID(int=2)))
        elif change == "id":
            db.execute(User.__table__.update().where(User.id == uuid.UUID(int=2)).values(id=uuid.UUID(int=3)))
        else:
            # Simulate an out-of-protocol privileged source repair, only here.
            db.exec_driver_sql("ALTER TABLE users DISABLE TRIGGER tr_users_email_immutable")
            db.execute(User.__table__.update().where(User.id == uuid.UUID(int=2)).values(email="changed@example.test"))
            db.exec_driver_sql("ALTER TABLE users ENABLE TRIGGER tr_users_email_immutable")
    with context(store) as maintenance:
        with pytest.raises(CheckpointRejected):
            EmailIdentityBackfill(maintenance).prepare()
    assert reservations(store) == []


@pytest.mark.parametrize("failure", ["interrupt", "database"])
def test_failure_after_reservation_write_rolls_back_batch_and_checkpoint(database, failure):
    store = database(["one@example.test"])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance)
        prepared = worker.prepare()
        def fail_checkpoint(connection, cursor, statement, parameters, ctx, executemany):
            if statement.startswith("UPDATE") and "users_processed" in statement:
                if failure == "database":
                    connection.exec_driver_sql("SELECT 1/0")
                raise RuntimeError("injected interruption")
        sa.event.listen(maintenance._engine, "before_cursor_execute", fail_checkpoint)
        try:
            with pytest.raises(RuntimeError if failure == "interrupt" else BackfillError):
                worker.run_batch()
        finally:
            sa.event.remove(maintenance._engine, "before_cursor_execute", fail_checkpoint)
        assert reservations(store) == []
        assert worker.prepare() == prepared
        finish(worker)


@pytest.mark.parametrize("persisted", [False, True])
def test_lost_commit_acknowledgment_requires_fresh_context(database, monkeypatch, persisted):
    from app.modules.auth.email_identity_verifier import EmailIdentityVerifier
    from app.modules.auth.email_identity_finalization import LocalEmailIdentityFinalizer
    store = database(["one@example.test", "two@example.test"])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance, batch_size=1)
        worker.prepare()
        verifier = EmailIdentityVerifier(maintenance)
        finalizer = LocalEmailIdentityFinalizer(maintenance)
        original = maintenance._engine.dialect.do_commit
        def lose_ack(connection):
            if persisted:
                original(connection)
            raise OSError("injected lost acknowledgment")
        with monkeypatch.context() as patch:
            patch.setattr(maintenance._engine.dialect, "do_commit", lose_ack)
            with pytest.raises(CommitOutcomeUnknown):
                worker.run_batch()
        with pytest.raises(MaintenanceRequired):
            worker.prepare()
        assert maintenance._retired
        assert maintenance._worker is maintenance._freezer is None
        for constructor in (EmailIdentityBackfill, EmailIdentityVerifier, LocalEmailIdentityFinalizer):
            with pytest.raises(MaintenanceRequired):
                constructor(maintenance)
        for operation in (verifier.verify, finalizer.finalize, maintenance.__enter__):
            with pytest.raises(MaintenanceRequired):
                operation()
    assert state(store)["users_processed"] == int(persisted)
    with context(store) as maintenance:
        resumed = EmailIdentityBackfill(maintenance)
        with pytest.raises(MaintenanceRequired):
            resumed.run_batch()  # A fresh context alone is not a resume inspection.
        assert resumed.prepare().users_processed == int(persisted)
        assert finish(resumed).users_processed == 2


def test_actual_server_address_must_match_docker(database, monkeypatch):
    store = database(["one@example.test"])
    before = state(store), reservations(store)
    monkeypatch.setattr(IsolatedMaintenanceContext, "_docker_addresses", staticmethod(lambda: frozenset({"192.0.2.1"})))
    with pytest.raises(MaintenanceRequired):
        with context(store):
            pytest.fail("Actual server must not match a fabricated Docker address")
    assert (state(store), reservations(store)) == before


def test_both_connections_are_independently_verified(database, monkeypatch):
    store = database(["one@example.test"])
    original = IsolatedMaintenanceContext._check_server
    observed = []
    def check(self, db, addresses):
        pid = original(self, db, addresses)
        observed.append(pid)
        if len(observed) == 2:
            raise MaintenanceRequired()
        return pid
    monkeypatch.setattr(IsolatedMaintenanceContext, "_check_server", check)
    with pytest.raises(MaintenanceRequired):
        with context(store):
            pytest.fail("Freezer verification failure must prevent entry")
    assert len(set(observed)) == 2
    # Cleanup released advisory ownership even when only entry partially succeeded.
    monkeypatch.setattr(IsolatedMaintenanceContext, "_check_server", original)
    with context(store) as maintenance:
        finish(EmailIdentityBackfill(maintenance))


@pytest.mark.parametrize("code", ["40001", "40P01"])
def test_retry_rolls_back_entire_batch_in_new_transactions(database, code):
    store = database(["one@example.test"])
    transactions = []
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance)
        worker.prepare()
        def abort_twice(connection, cursor, statement, parameters, ctx, executemany):
            if statement.startswith("UPDATE") and "users_processed" in statement:
                transactions.append(connection.scalar(sa.text("SELECT txid_current()")))
                if len(transactions) < 3:
                    connection.exec_driver_sql(f"DO $$ BEGIN RAISE EXCEPTION USING ERRCODE='{code}', MESSAGE='test transaction abort'; END $$")
        sa.event.listen(maintenance._engine, "before_cursor_execute", abort_twice)
        try:
            assert worker.run_batch().users_processed == 1
        finally:
            sa.event.remove(maintenance._engine, "before_cursor_execute", abort_twice)
    assert len(transactions) == len(set(transactions)) == 3
    assert len(reservations(store)) == 1


def test_freeze_lost_during_batch_rolls_back_before_commit(database):
    store = database(["one@example.test"])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance)
        worker.prepare()
        def lose_freeze(connection, cursor, statement, parameters, ctx, executemany):
            if statement.startswith("UPDATE") and "users_processed" in statement:
                maintenance._freezer.rollback()
        sa.event.listen(maintenance._engine, "before_cursor_execute", lose_freeze)
        try:
            with pytest.raises(MaintenanceRequired):
                worker.run_batch()
        finally:
            sa.event.remove(maintenance._engine, "before_cursor_execute", lose_freeze)
    assert state(store)["users_processed"] == 0
    assert reservations(store) == []


def test_autocommit_and_public_schema_access_are_not_maintenance_contexts(database):
    store = database(["one@example.test"])
    autocommit = store.engine.execution_options(isolation_level="AUTOCOMMIT")
    with pytest.raises(MaintenanceRequired):
        with IsolatedMaintenanceContext(autocommit, expected_fingerprint=APPROVED_FINGERPRINT):
            pytest.fail("AUTOCOMMIT entered maintenance")
    with store.engine.begin() as db:
        db.exec_driver_sql(f"GRANT USAGE ON SCHEMA {store.schema} TO PUBLIC")
    with pytest.raises(MaintenanceRequired):
        with context(store):
            pytest.fail("Non-private schema entered maintenance")
    assert reservations(store) == []


def test_freeze_is_real_advisory_exclusive_and_loss_fails_closed(database):
    store = database(["one@example.test"])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance)
        worker.prepare()
        with pytest.raises(MaintenanceRequired):
            with context(store):
                pytest.fail("Concurrent maintenance runner entered")
        with pytest.raises(DBAPIError) as error, store.engine.begin() as writer:
            writer.exec_driver_sql("SET LOCAL lock_timeout='100ms'")
            writer.execute(User.__table__.update().values(updated_at=User.updated_at))
        assert error.value.orig.sqlstate == "55P03"
        maintenance._freezer.rollback()
        with pytest.raises(MaintenanceRequired):
            worker.run_batch()
    assert reservations(store) == []


def test_lost_advisory_ownership_fails_closed(database):
    store = database(["one@example.test"])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance)
        worker.prepare()
        with maintenance._worker.begin():
            maintenance._worker.exec_driver_sql("SELECT pg_advisory_unlock_all()")
        with pytest.raises(MaintenanceRequired):
            worker.run_batch()
    assert reservations(store) == []


def test_context_connections_cannot_be_shared_across_threads(database):
    store = database(["one@example.test"])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance)
        worker.prepare()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(MaintenanceRequired):
                pool.submit(worker.run_batch).result(timeout=5)
        assert worker.run_batch().source_exhausted


def test_source_and_resume_registry_reads_have_bounded_pages(database):
    store = database([f"user{number}@example.test" for number in range(31)])
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance, batch_size=7)
        worker.prepare()
        for _ in range(3):
            worker.run_batch()
    observed = {"source": [], "reservations": []}
    def inspect_pages(connection, cursor, statement, parameters, ctx, executemany):
        if not statement.startswith("SELECT"):
            return
        if ".users.email" in statement:
            observed["source"].append(cursor.rowcount)
        elif ".lookup_key" in statement:
            observed["reservations"].append(cursor.rowcount)
    with context(store) as maintenance:
        sa.event.listen(maintenance._engine, "after_cursor_execute", inspect_pages)
        try:
            progress = finish(EmailIdentityBackfill(maintenance, batch_size=3))
        finally:
            sa.event.remove(maintenance._engine, "after_cursor_execute", inspect_pages)
    assert progress.users_processed == 31
    for pages in observed.values():
        assert len(pages) > 1 and max(pages) == 3 and min(pages) >= 0


@pytest.mark.parametrize("state_name", ["owned", "blocked"])
def test_uninitialized_registry_with_unexplained_rows_is_not_overwritten(database, state_name):
    store = database(["one@example.test"])
    with store.engine.begin() as db:
        db.execute(R.insert().values(id=uuid.uuid4(), lookup_key="existing@example.test", state=state_name,
                                    user_id=uuid.UUID(int=1) if state_name == "owned" else None))
    before = state(store), reservations(store)
    with context(store) as maintenance:
        with pytest.raises(CheckpointRejected):
            EmailIdentityBackfill(maintenance).prepare()
    assert (state(store), reservations(store)) == before


def test_exhausted_serialization_retries_preserve_prior_checkpoint(database):
    store = database(["one@example.test"])
    attempts = []
    with context(store) as maintenance:
        worker = EmailIdentityBackfill(maintenance)
        prepared = worker.prepare()
        def abort(connection, cursor, statement, parameters, ctx, executemany):
            if statement.startswith("UPDATE") and "users_processed" in statement:
                attempts.append(connection.scalar(sa.text("SELECT txid_current()")))
                connection.exec_driver_sql("DO $$ BEGIN RAISE EXCEPTION USING ERRCODE='40001', MESSAGE='test abort'; END $$")
        sa.event.listen(maintenance._engine, "before_cursor_execute", abort)
        try:
            with pytest.raises(BackfillError):
                worker.run_batch()
        finally:
            sa.event.remove(maintenance._engine, "before_cursor_execute", abort)
        assert len(attempts) == len(set(attempts)) == 3
        assert reservations(store) == []
        assert worker.prepare() == prepared


@pytest.mark.parametrize("status", ["missing", "ready", "version"])
def test_policy_state_requires_building_v1(database, status):
    store = database(["one@example.test"])
    with store.engine.begin() as db:
        if status == "missing":
            db.execute(P.delete())
        elif status == "ready":
            db.execute(P.update().values(status="ready", manifest_sha256=b"x" * 32))
        else:
            db.exec_driver_sql("ALTER TABLE email_identity_policy_state DROP CONSTRAINT ck_eips_policy_version")
            db.execute(P.update().values(policy_version=2))
    with context(store) as maintenance:
        with pytest.raises(CheckpointRejected):
            EmailIdentityBackfill(maintenance).prepare()


def test_stage2b_operations_work_after_isolated_freeze_release(database):
    store = database(["one@example.test"])
    identifier = uuid.UUID(int=1)
    service = SessionService(store.engine, settings=Settings(_env_file=None, _secrets_dir=None))
    before = service.create_session(identifier)
    with context(store) as maintenance:
        finish(EmailIdentityBackfill(maintenance))
    rotated = service.rotate_refresh_token(before.refresh_token)
    with pytest.raises(SessionAuthenticationError):
        service.rotate_refresh_token(before.refresh_token)
    with pytest.raises(SessionAuthenticationError):
        service.rotate_refresh_token(rotated.refresh_token)
    service.create_session(identifier)
    service.revoke_all_sessions(identifier)
    assert state(store)["status"] == "building"
