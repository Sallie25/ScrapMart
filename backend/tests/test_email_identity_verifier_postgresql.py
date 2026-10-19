"""Verifier tests use private schemas only; public schema is never changed."""
import os
import uuid

import pytest
import sqlalchemy as sa

from tests.test_auth_sessions_postgresql import local_postgres
from tests.test_email_identity_backfill_postgresql import database, context, finish, state
from app.modules.auth.email_identity_backfill import EmailIdentityBackfill
from app.modules.auth.email_identity_verifier import EmailIdentityVerifier, VerificationError

pytestmark = pytest.mark.skipif(os.environ.get("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS") != "1", reason="Opt-in disposable local PostgreSQL only")


def populated(database, emails):
    store = database(emails)
    with context(store) as maintenance:
        finish(EmailIdentityBackfill(maintenance, batch_size=1))
    return store


@pytest.mark.parametrize("emails", [(), ("A@example.test", "a@example.test", "ß@example.test", "ss@example.test", "Σ@example.test", "person@bücher.test")])
def test_complete_independent_and_read_only(database, monkeypatch, emails):
    store = populated(database, emails)
    before = state(store)
    import app.modules.auth.email_identity_backfill as backfill
    def forbidden(*args, **kwargs):
        raise AssertionError("Backfill algorithm reused")
    monkeypatch.setattr(backfill, "aggregate_aliases", forbidden)
    monkeypatch.setattr(EmailIdentityBackfill, "_write", forbidden)
    with context(store) as maintenance:
        first = EmailIdentityVerifier(maintenance, batch_size=1).verify()
        second = EmailIdentityVerifier(maintenance, batch_size=500).verify()
    assert first == second
    assert first.passed
    assert first.source_count == len(emails)
    assert first.expected_manifest == first.actual_manifest
    assert state(store) == before
    assert before["status"] == "building"


@pytest.mark.parametrize("damage,issue", [("missing", "missing_key"), ("extra", "unexpected_key"), ("blocked", "state"), ("count", "source_count"), ("progress", "incomplete_checkpoint")])
def test_detect_corruption(database, damage, issue):
    store = populated(database, ["a@example.test", "b@example.test"])
    with context(store) as maintenance:
        r, p = maintenance.reservations, maintenance.policy
        with maintenance._worker.begin():
            db = maintenance._worker
            if damage == "missing":
                db.execute(r.delete().where(r.c.lookup_key == "a@example.test"))
            elif damage == "extra":
                db.execute(r.insert().values(id=uuid.uuid4(), lookup_key="extra@example.test", state="blocked", user_id=None))
            elif damage == "blocked":
                db.execute(r.update().where(r.c.lookup_key == "a@example.test").values(state="blocked", user_id=None))
            elif damage == "count":
                db.execute(p.update().values(source_count=3))
            else:
                db.execute(p.update().values(users_processed=1))
        report = EmailIdentityVerifier(maintenance).verify()
    assert not report.passed
    assert dict(report.issues)[issue] > 0


def test_invalid_source_and_incomplete_registry(database):
    store = database(["not-an-email", "Σ@example.test"])
    with context(store) as maintenance:
        report = EmailIdentityVerifier(maintenance).verify()
    assert dict(report.issues)["invalid_source"] == 1
    assert report.zero_alias_count == 1
    assert not report.passed


def test_postgres_enforces_read_only(database, monkeypatch):
    store = populated(database, ["a@example.test"])
    before = state(store)
    import app.modules.auth.email_identity_verifier as verifier
    with context(store) as maintenance:
        def attempted_write(email):
            assert maintenance._worker.scalar(sa.text("SHOW transaction_read_only")) == "on"
            maintenance._worker.execute(maintenance.policy.update().values(users_processed=0))
        monkeypatch.setattr(verifier, "legacy_email_identity", attempted_write)
        with pytest.raises(VerificationError, match="maintenance review required"):
            EmailIdentityVerifier(maintenance).verify()
        assert not maintenance._worker.in_transaction()
    assert state(store) == before


def test_manually_constructed_registry_without_backfill(database):
    store = database(["Buyer@example.test", "buyer@example.test", "ß@example.test", "only@example.test", "Σ@example.test"])
    with context(store) as maintenance:
        with maintenance._worker.begin():
            maintenance._worker.execute(maintenance.reservations.insert(), [
                {"id": uuid.uuid4(), "lookup_key": key, "state": status, "user_id": owner}
                for key, status, owner in [
                    ("buyer@example.test", "blocked", None),
                    ("ss@example.test", "blocked", None),
                    ("only@example.test", "owned", uuid.UUID(int=4)),
                ]
            ])
            maintenance._worker.execute(maintenance.policy.update().values(
                source_count=5, users_processed=5, last_user_id=uuid.UUID(int=5), manifest_sha256=bytes(32)))
        report = EmailIdentityVerifier(maintenance, batch_size=1).verify()
    assert report.passed
    assert report.zero_alias_count == 1
    assert report.expected_count == report.actual_count == 3


@pytest.mark.parametrize("damage,issue", [("owner", "ownership"), ("version", "policy_version")])
def test_corruption_beyond_normal_writer_guards(database, damage, issue):
    store = populated(database, ["a@example.test", "b@example.test"])
    # Privileged corruption simulation is strictly limited to this private schema.
    with context(store) as maintenance:
        with maintenance._worker.begin():
            db = maintenance._worker
            table = '"' + store.schema + '".email_identity_reservations'
            db.exec_driver_sql("ALTER TABLE " + table + " DISABLE TRIGGER USER")
            if damage == "owner":
                db.execute(maintenance.reservations.update().where(
                    maintenance.reservations.c.lookup_key == "a@example.test").values(user_id=uuid.UUID(int=2)))
            else:
                db.exec_driver_sql("ALTER TABLE " + table + " DROP CONSTRAINT ck_eir_policy_version")
                db.execute(maintenance.reservations.update().values(policy_version=2))
            # Drain the valid deferred FK event before further table DDL.
            db.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
            db.exec_driver_sql("ALTER TABLE " + table + " ENABLE TRIGGER USER")
        report = EmailIdentityVerifier(maintenance).verify()
    assert not report.passed
    assert dict(report.issues)[issue] > 0


def test_scratch_cleanup_after_failure(database, monkeypatch, tmp_path):
    import app.modules.auth.email_identity_verifier as verifier
    from tempfile import TemporaryDirectory
    monkeypatch.setattr(verifier, "TemporaryDirectory", lambda **kwargs: TemporaryDirectory(dir=tmp_path, **kwargs))
    store = populated(database, ["a@example.test", "b@example.test"])
    original = verifier.legacy_email_identity
    def fail_second(email):
        if email.startswith("b@"):
            raise OSError("sensitive internal diagnostic")
        return original(email)
    monkeypatch.setattr(verifier, "legacy_email_identity", fail_second)
    with context(store) as maintenance:
        with pytest.raises(VerificationError) as error:
            EmailIdentityVerifier(maintenance, batch_size=1).verify()
    assert "sensitive" not in str(error.value)
    assert list(tmp_path.iterdir()) == []
