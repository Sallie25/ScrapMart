"""Offline tests for bounded aggregation, source binding, and context refusal."""
import uuid

import pytest
import sqlalchemy as sa

from app.modules.auth.email_identity_backfill import (
    APPROVED_FINGERPRINT, DEFAULT_BATCH_SIZE, Checkpoint, EmailIdentityBackfill,
    IsolatedMaintenanceContext, MaintenanceRequired, SourceRejected, SourceSnapshot,
    _checkpoint_seed, _extend, _source_seed, aggregate_aliases, checked_batch_size, source_record,
)


def record(number, email):
    return source_record(uuid.UUID(int=number), email)


def test_aggregation_deduplicates_same_owner_and_blocks_distinct_owners():
    first = record(1, "Buyer@example.test")
    same = record(1, "buyer@example.test")
    other = record(2, "BUYER@example.test")
    assert aggregate_aliases([first, same]) == [{
        "lookup_key": "buyer@example.test", "state": "owned",
        "user_id": first.user_id, "policy_version": 1,
    }]
    expected = [{"lookup_key": "buyer@example.test", "state": "blocked", "user_id": None, "policy_version": 1}]
    assert aggregate_aliases([first, same, other]) == expected
    assert aggregate_aliases([other, same, first]) == expected


def test_mandatory_blocking_dominates_in_both_orders():
    canonical, compatibility = record(1, "i@example.test"), record(2, "İ@example.test")
    for records in ([canonical, compatibility], [compatibility, canonical], [compatibility]):
        assert aggregate_aliases(records) == [{"lookup_key": "i@example.test", "state": "blocked", "user_id": None, "policy_version": 1}]


def test_zero_alias_records_advance_manifest_without_reservation_rows():
    zero = record(1, "Σ@example.test")
    assert aggregate_aliases([zero]) == []
    assert _extend(_source_seed(), zero) != _source_seed()


def test_aggregation_rejects_unbounded_input():
    with pytest.raises(ValueError):
        aggregate_aliases([record(1, "one@example.test")] * 1001)


def test_manifest_binds_exact_source_not_just_normalized_aliases():
    first = record(1, "Buyer@example.test")
    recased = record(1, "buyer@example.test")
    other_id = record(2, "Buyer@example.test")
    assert first.identity == recased.identity
    digests = {_extend(_source_seed(), row) for row in (first, recased, other_id)}
    assert len(digests) == 3
    assert _extend(_source_seed(), first) == _extend(_source_seed(), first)


def test_checkpoint_seed_binds_full_source_count_last_uuid_and_digest():
    first = SourceSnapshot(1, uuid.UUID(int=1), bytes(32))
    variants = [first, SourceSnapshot(2, first.last_user_id, first.digest),
                SourceSnapshot(1, uuid.UUID(int=2), first.digest),
                SourceSnapshot(1, first.last_user_id, b"x" * 32)]
    assert len({_checkpoint_seed(snapshot) for snapshot in variants}) == 4


@pytest.mark.parametrize("email", ["bad", "person@" + "ß" * 32 + ".test"])
def test_invalid_and_unclassifiable_sources_are_rejected_safely(email):
    with pytest.raises(SourceRejected) as error:
        record(1, email)
    assert str(error.value) == "Email identity backfill stopped; maintenance revalidation required"
    assert email not in str(error.value)


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1001, 500.0, "500"])
def test_invalid_batch_size(value):
    with pytest.raises(ValueError):
        checked_batch_size(value)


@pytest.mark.parametrize("value", [1, 500, 1000])
def test_batch_size_bounds(value):
    assert checked_batch_size(value) == value
    assert DEFAULT_BATCH_SIZE == 500


@pytest.mark.parametrize("schema,fingerprint", [
    ("sqlite://", APPROVED_FINGERPRINT),
    ("postgresql+psycopg://scrapmart_test@remote.invalid/test", APPROVED_FINGERPRINT),
    ("public", APPROVED_FINGERPRINT),
    ("email_backfill_" + "a" * 32, "unapproved"),
])
def test_unsafe_contexts_refused_before_any_connection(monkeypatch, schema, fingerprint):
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected target must not be connected")
    monkeypatch.setattr(sa, "create_engine", forbidden)
    with pytest.raises(MaintenanceRequired):
        IsolatedMaintenanceContext(schema, expected_fingerprint=fingerprint)


def test_no_caller_session_factory_or_boolean_freeze_claim_is_accepted():
    for context in (None, True, lambda: True, object()):
        with pytest.raises(MaintenanceRequired):
            EmailIdentityBackfill(context)
    with pytest.raises(MaintenanceRequired):
        IsolatedMaintenanceContext(object(), expected_fingerprint=APPROVED_FINGERPRINT)


def test_exhaustion_is_explicitly_only_a_checkpoint_count():
    checkpoint = Checkpoint(0, 0, None, bytes(32))
    assert checkpoint.source_exhausted
    assert not hasattr(checkpoint, "ready")


@pytest.mark.parametrize("override", ["query", "connect_args", "creator", "pool"])
def test_engine_destination_overrides_are_rejected_without_connecting(monkeypatch, override):
    url = "postgresql+psycopg://scrapmart_test@127.0.0.1:55432/scrapmart_test"
    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted connector must never be called")
    options = {}
    if override == "query":
        url += "?host=remote.invalid&port=5432"
    elif override == "connect_args":
        options["connect_args"] = {"host": "remote.invalid", "port": 5432}
    elif override == "creator":
        options["creator"] = forbidden
    else:
        options["pool"] = sa.pool.StaticPool(creator=forbidden)
    engine = sa.create_engine(url, **options)
    monkeypatch.setattr(engine, "connect", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    try:
        with pytest.raises(MaintenanceRequired):
            IsolatedMaintenanceContext(engine, expected_fingerprint=APPROVED_FINGERPRINT)
    finally:
        engine.dispose()


def test_internal_engine_has_no_destination_override_surface(monkeypatch):
    captured = {}
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setattr(IsolatedMaintenanceContext, "_docker_addresses", staticmethod(lambda: frozenset({"172.18.0.2"})))
    def inspect_engine(url, **kwargs):
        captured.update(url=url, **kwargs)
        raise MaintenanceRequired()
    monkeypatch.setattr(sa, "create_engine", inspect_engine)
    with pytest.raises(MaintenanceRequired):
        with IsolatedMaintenanceContext("email_backfill_" + "a"*32, expected_fingerprint=APPROVED_FINGERPRINT):
            pytest.fail("Inspection must not connect")
    assert captured["url"].host == "127.0.0.1"
    assert captured["url"].port == 55432
    assert captured["url"].database == captured["url"].username == "scrapmart_test"
    assert not captured["url"].query
    assert captured["connect_args"]["hostaddr"] == "127.0.0.1"
    assert captured["poolclass"] is sa.pool.NullPool
    assert "creator" not in captured and "pool" not in captured


@pytest.mark.parametrize("damage", ["name", "image", "running", "ports", "addresses", "malformed", "failure"])
def test_docker_mismatch_fails_before_engine_creation(monkeypatch, damage):
    import json
    import subprocess
    from types import SimpleNamespace
    values = ["/scrapmart-postgres-test", "postgres:16-alpine", True,
              {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]},
              {"local": {"IPAddress": "172.18.0.2"}}]
    position = {"name": 0, "image": 1, "running": 2, "ports": 3, "addresses": 4}
    if damage in position:
        values[position[damage]] = None
    def docker(*args, **kwargs):
        if damage == "failure":
            raise subprocess.CalledProcessError(1, "docker")
        return SimpleNamespace(stdout="bad json" if damage == "malformed" else "\n".join(json.dumps(v) for v in values))
    def forbidden(*args, **kwargs):
        pytest.fail("Docker rejection must precede engine creation")
    monkeypatch.setattr(subprocess, "run", docker)
    monkeypatch.setattr(sa, "create_engine", forbidden)
    with pytest.raises(MaintenanceRequired):
        with IsolatedMaintenanceContext("email_backfill_" + "a"*32, expected_fingerprint=APPROVED_FINGERPRINT):
            pass


def test_public_schema_and_autocommit_rejected_by_new_construction_contract():
    for schema, level in [("public", "READ COMMITTED"), ("email_backfill_" + "a"*32, "AUTOCOMMIT")]:
        with pytest.raises(MaintenanceRequired):
            IsolatedMaintenanceContext(schema, expected_fingerprint=APPROVED_FINGERPRINT, isolation_level=level)
