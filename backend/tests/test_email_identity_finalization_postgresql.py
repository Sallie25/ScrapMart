"""Local-only finalization in disposable schemas; never public DDL or readiness."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa

from tests.test_auth_sessions_postgresql import local_postgres
from tests.test_email_identity_backfill_postgresql import database, context, finish, state, reservations
from app.modules.auth.email_identity_backfill import EmailIdentityBackfill, MaintenanceRequired
from app.modules.auth.email_identity_finalization import (
    LocalEmailIdentityFinalizer, FinalizationError, FinalizationOutcomeUnknown,
)

pytestmark = pytest.mark.skipif(os.environ.get("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS") != "1", reason="Verified disposable PostgreSQL only")


def populated(database, emails=("a@example.test", "b@example.test")):
    store = database(emails)
    with context(store) as maintenance:
        finish(EmailIdentityBackfill(maintenance, batch_size=1))
    return store


@pytest.mark.parametrize("emails", [(), ("Σ@example.test",), ("A@example.test", "a@example.test", "ß@example.test", "ss@example.test", "person@bücher.test")])
def test_success_preserves_source_reservations_and_checkpoint(database, emails):
    store = populated(database, emails)
    before, rows = state(store), reservations(store)
    with store.engine.connect() as db:
        users_before = db.execute(sa.text("SELECT * FROM users ORDER BY id")).all()
    with context(store) as maintenance:
        result = LocalEmailIdentityFinalizer(maintenance, batch_size=1).finalize()
        assert result.verification.passed
        assert result.verification.source_count == len(emails)
        assert result.checkpoint_digest == before["manifest_sha256"]
        with pytest.raises(FinalizationError):
            LocalEmailIdentityFinalizer(maintenance).finalize()
    after = state(store)
    assert after["status"] == "ready"
    assert {k:v for k,v in after.items() if k not in ("status", "updated_at")} == {k:v for k,v in before.items() if k not in ("status", "updated_at")}
    assert reservations(store) == rows
    with store.engine.connect() as db:
        assert db.execute(sa.text("SELECT * FROM users ORDER BY id")).all() == users_before


@pytest.mark.parametrize("damage", ["digest", "count", "last", "missing", "extra", "blocked", "owner", "no_policy"])
def test_rejections_do_not_activate(database, damage):
    store = populated(database)
    with context(store) as maintenance:
        with maintenance._worker.begin():
            db, p, r = maintenance._worker, maintenance.policy, maintenance.reservations
            if damage == "digest":
                db.execute(p.update().values(manifest_sha256=bytes(32)))
            elif damage == "count":
                db.execute(p.update().values(source_count=3))
            elif damage == "last":
                db.execute(p.update().values(last_user_id=uuid.UUID(int=1)))
            elif damage == "missing":
                db.execute(r.delete().where(r.c.lookup_key == "a@example.test"))
            elif damage == "extra":
                db.execute(r.insert().values(id=uuid.uuid4(), lookup_key="extra@example.test", state="blocked", user_id=None))
            elif damage == "blocked":
                db.execute(r.update().where(r.c.lookup_key == "a@example.test").values(state="blocked", user_id=None))
            elif damage == "owner":
                table = '"' + store.schema + '".email_identity_reservations'
                db.exec_driver_sql("ALTER TABLE " + table + " DISABLE TRIGGER USER")
                db.execute(r.update().where(r.c.lookup_key == "a@example.test").values(user_id=uuid.UUID(int=2)))
                db.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
                db.exec_driver_sql("ALTER TABLE " + table + " ENABLE TRIGGER USER")
            else:
                db.execute(p.delete())
        with pytest.raises(FinalizationError):
            LocalEmailIdentityFinalizer(maintenance).finalize()
        assert not maintenance._worker.in_transaction()
        with maintenance._worker.begin():
            assert not maintenance._worker.scalar(sa.select(sa.exists().where(maintenance.policy.c.status == "ready")))


@pytest.mark.parametrize("emails", [("a@example.test", "b@example.test"), ("invalid-address",)])
def test_incomplete_and_invalid_sources(database, emails):
    store = database(emails)
    with context(store) as maintenance:
        with pytest.raises(FinalizationError):
            LocalEmailIdentityFinalizer(maintenance).finalize()
    assert state(store)["status"] == "building"


def test_partial_backfill(database):
    store = database(["a@example.test", "b@example.test"])
    with context(store) as maintenance:
        backfill = EmailIdentityBackfill(maintenance, batch_size=1)
        backfill.prepare()
        backfill.run_batch()
        with pytest.raises(FinalizationError):
            LocalEmailIdentityFinalizer(maintenance).finalize()
    assert state(store)["status"] == "building"


def test_failed_verification_and_concurrent_maintenance(database, monkeypatch):
    store = populated(database)
    with context(store) as maintenance:
        finalizer = LocalEmailIdentityFinalizer(maintenance)
        original = finalizer.verifier._verify
        def verify(db, directory):
            with ThreadPoolExecutor() as executor:
                def competing():
                    with pytest.raises(MaintenanceRequired):
                        with context(store):
                            pass
                executor.submit(competing).result(timeout=10)
            report = original(db, directory)
            from dataclasses import replace
            return replace(report, issues=(("injected_failure", 1),))
        monkeypatch.setattr(finalizer.verifier, "_verify", verify)
        with pytest.raises(FinalizationError):
            finalizer.finalize()
    assert state(store)["status"] == "building"


def test_interrupted_after_ready_update_rolls_back(database, monkeypatch):
    store = populated(database)
    with context(store) as maintenance:
        original = maintenance._assert_ownership
        calls = 0
        def interrupt(db):
            nonlocal calls
            calls += 1
            original(db)
            if calls == 3:
                raise KeyboardInterrupt()
        monkeypatch.setattr(maintenance, "_assert_ownership", interrupt)
        with pytest.raises(KeyboardInterrupt):
            LocalEmailIdentityFinalizer(maintenance).finalize()
    assert state(store)["status"] == "building"


@pytest.mark.parametrize("committed", [False, True])
def test_unknown_commit_outcome_never_returns_success(database, monkeypatch, committed):
    from sqlalchemy.engine import RootTransaction
    store = populated(database)
    with context(store) as maintenance:
        original = RootTransaction.commit
        def lost_ack(tx):
            if tx.connection is maintenance._worker:
                if committed:
                    original(tx)
                raise OSError("lost acknowledgement")
            return original(tx)
        with monkeypatch.context() as patch:
            patch.setattr(RootTransaction, "commit", lost_ack)
            with pytest.raises(FinalizationOutcomeUnknown):
                LocalEmailIdentityFinalizer(maintenance).finalize()
        assert maintenance._worker is None
        assert maintenance._retired
    assert state(store)["status"] == ("ready" if committed else "building")


def test_same_alias_source_change_invalidates_checkpoint(database):
    store = populated(database, ["Buyer@example.test"])
    # Simulate a privileged source alteration before acquiring the writer freeze.
    with store.engine.begin() as db:
        db.exec_driver_sql("ALTER TABLE users DISABLE TRIGGER USER")
        db.exec_driver_sql("UPDATE users SET email='buyer@example.test'")
        db.exec_driver_sql("ALTER TABLE users ENABLE TRIGGER USER")
    with context(store) as maintenance:
        # The independent reservation comparison alone cannot detect this change.
        assert LocalEmailIdentityFinalizer(maintenance).verifier.verify().passed
        with pytest.raises(FinalizationError):
            LocalEmailIdentityFinalizer(maintenance).finalize()
    assert state(store)["status"] == "building"


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
def test_write_fences_and_configured_isolation(database, monkeypatch, isolation):
    from sqlalchemy.exc import DBAPIError
    store = populated(database)
    with context(store, isolation_level=isolation) as maintenance:
        finalizer = LocalEmailIdentityFinalizer(maintenance)
        original = finalizer.verifier._verify
        def verify(db, directory):
            assert db.scalar(sa.text("SHOW transaction_isolation")) == "read committed"
            def competing_writes():
                for statement in (
                    "UPDATE users SET full_name=full_name",
                    "UPDATE email_identity_reservations SET state='blocked',user_id=NULL",
                    "UPDATE email_identity_policy_state SET status='ready'",
                ):
                    with pytest.raises(DBAPIError) as error:
                        with store.engine.begin() as other:
                            other.exec_driver_sql("SET LOCAL lock_timeout='100ms'")
                            other.exec_driver_sql(statement)
                    assert error.value.orig.sqlstate == "55P03"
            with ThreadPoolExecutor() as executor:
                executor.submit(competing_writes).result(timeout=10)
            return original(db, directory)
        monkeypatch.setattr(finalizer.verifier, "_verify", verify)
        assert finalizer.finalize().verification.passed
    assert state(store)["status"] == "ready"
