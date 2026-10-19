"""Step 2 backfill components, restricted to private disposable local schemas.

PRODUCTION BLOCKER: no production freeze/role inventory has been approved. This
module supplies NO production maintenance context or command. Its isolated-test
context uses a real SHARE table lock to drain/freeze ALL User DML (including
Stage 2B updates while held), a private schema, and an exclusive advisory lock.
It must not be used as a production availability/privilege guarantee.

Only a private schema name and an enumerated isolation level are accepted. Context
engines are constructed internally; caller Engines/connectors are never accepted.
connections are private, never caller-owned. Batch writes/checkpoints commit
together; source/prefix reconstruction on prepare supports safe resumption. This
is NOT the independent final verifier and never activates readiness.
"""
from dataclasses import dataclass, field
import hashlib
import ipaddress
from itertools import zip_longest
import json
import re
import subprocess
import threading
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.modules.auth.email_identity_models import EmailIdentityPolicyState, EmailIdentityReservation, POLICY_STATE_ID
from app.modules.auth.email_identity_policy import AliasDisposition, LegacyIdentity, legacy_email_identity, policy_fingerprint
from app.modules.auth.models import User

APPROVED_FINGERPRINT = "cbdc5198ab2b1c3f23062e5318c97f0ab4e403023a69035e355bc8e8c431e59f"
DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 1000
_LOCK_CLASS = 0x534D454D
_SCHEMA = re.compile(r"email_backfill_[0-9a-f]{32}\Z")


class BackfillError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Email identity backfill stopped; maintenance revalidation required")


class MaintenanceRequired(BackfillError):
    pass


class SourceRejected(BackfillError):
    pass


class CheckpointRejected(BackfillError):
    pass


class CommitOutcomeUnknown(BackfillError):
    """Never blindly retry: reopen context and prepare from durable state."""


@dataclass(frozen=True)
class SourceRecord:
    user_id: uuid.UUID
    email: str = field(repr=False)
    identity: LegacyIdentity


@dataclass(frozen=True)
class SourceSnapshot:
    count: int
    last_user_id: uuid.UUID | None
    digest: bytes


@dataclass(frozen=True)
class Checkpoint:
    users_processed: int
    source_count: int
    last_user_id: uuid.UUID | None
    digest: bytes

    @property
    def source_exhausted(self) -> bool:
        # Exhaustion is NOT independent verification or readiness approval.
        return self.users_processed == self.source_count


def checked_batch_size(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_BATCH_SIZE:
        raise ValueError("Batch size must be an integer between 1 and 1000")
    return value


def source_record(user_id: uuid.UUID, email: str) -> SourceRecord:
    identity = legacy_email_identity(email)
    if identity.blocks_readiness:
        raise SourceRejected()
    return SourceRecord(user_id, email, identity)


def _extend(digest: bytes, record: SourceRecord) -> bytes:
    data = json.dumps({
        "id": record.user_id.hex, "email": record.email,
        "classification": record.identity.classification.value,
        "aliases": [(alias.key, alias.disposition.value) for alias in record.identity.aliases],
    }, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(digest + len(data).to_bytes(4, "big") + data).digest()


def _source_seed() -> bytes:
    return hashlib.sha256(b"scrapmart-email-source-v1\0" + APPROVED_FINGERPRINT.encode("ascii")).digest()


def _checkpoint_seed(snapshot: SourceSnapshot) -> bytes:
    return hashlib.sha256(
        b"scrapmart-email-checkpoint-v1\0" + APPROVED_FINGERPRINT.encode("ascii")
        + snapshot.digest + snapshot.count.to_bytes(8, "big")
        + (snapshot.last_user_id.bytes if snapshot.last_user_id is not None else bytes(16))
    ).digest()


def aggregate_aliases(records: list[SourceRecord]) -> list[dict]:
    """One input row per key; no per-key owner sets or unbounded owner lists."""
    if len(records) > MAX_BATCH_SIZE:
        raise ValueError("Alias aggregation exceeds the maximum batch size")
    keys = {}
    for record in records:
        for alias in record.identity.aliases:
            blocked = alias.disposition is AliasDisposition.BLOCKED
            previous = keys.get(alias.key)
            if previous is not None:
                blocked = blocked or previous["state"] == "blocked" or previous["user_id"] != record.user_id
            keys[alias.key] = {
                "lookup_key": alias.key, "state": "blocked" if blocked else "owned",
                "user_id": None if blocked else record.user_id, "policy_version": 1,
            }
    return [keys[key] for key in sorted(keys)]


class IsolatedMaintenanceContext:
    """A real freeze for TEST SCHEMAS ONLY. No bool/callback freeze attestation.

    Tests must first perform the established Docker/database contents preflight.
    This context additionally inspects Docker before connecting and verifies both
    connections' server addresses. It accepts no URL, Engine, pool or creator.
    Other owner/superuser sessions remain trusted maintenance actors, not runtime
    writers. Ordinary roles have no schema access. A separate connection holds
    Users SHARE across batch commits; the worker retains the advisory lock.
    """
    def __init__(self, schema: str, *, expected_fingerprint: str, isolation_level="READ COMMITTED"):
        if (
            type(schema) is not str or not _SCHEMA.fullmatch(schema)
            or isolation_level not in ("READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE")
            or expected_fingerprint != APPROVED_FINGERPRINT
            or policy_fingerprint() != APPROVED_FINGERPRINT
        ):
            raise MaintenanceRequired()
        self.schema, self._isolation_level = schema, isolation_level
        self._engine = None
        self._worker = self._freezer = None
        self._used = self._retired = False
        metadata = sa.MetaData()
        self.reservations = EmailIdentityReservation.__table__.to_metadata(metadata, schema=schema)
        self.policy = EmailIdentityPolicyState.__table__.to_metadata(metadata, schema=schema)
        self.users = User.__table__.to_metadata(metadata, schema=schema)

    @staticmethod
    def _transactional(connection):
        if connection.dialect.detect_autocommit_setting(connection.connection.dbapi_connection):
            raise MaintenanceRequired()

    @staticmethod
    def _docker_addresses():
        try:
            result = subprocess.run([
                "docker", "inspect", "scrapmart-postgres-test", "--format",
                "{{json .Name}}\n{{json .Config.Image}}\n{{json .State.Running}}\n"
                "{{json .NetworkSettings.Ports}}\n{{json .NetworkSettings.Networks}}",
            ], capture_output=True, text=True, check=True, timeout=10)
            name, image, running, ports, networks = [json.loads(line) for line in result.stdout.splitlines()]
            if (name != "/scrapmart-postgres-test" or image != "postgres:16-alpine" or running is not True
                or ports != {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]}):
                raise MaintenanceRequired()
            addresses = frozenset(str(ipaddress.ip_address(n["IPAddress"])) for n in networks.values())
            if not addresses or any(not ipaddress.ip_address(address).is_private for address in addresses):
                raise MaintenanceRequired()
            return addresses
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
            raise MaintenanceRequired() from None

    def _check_server(self, db, addresses):
        self._transactional(db)
        identity = db.execute(sa.text(
            "SELECT current_database(),current_user,current_setting('server_version_num')::int,"
            "inet_server_port(),pg_is_in_recovery(),pg_backend_pid(),host(inet_server_addr())"
        )).one()
        if (identity[:2] != ("scrapmart_test", "scrapmart_test") or not 160000 <= identity[2] < 170000
            or identity[3] != 5432 or identity[4] or identity[6] not in addresses):
            raise MaintenanceRequired()
        return identity[5]

    def __enter__(self):
        if self._used or self._retired:
            raise MaintenanceRequired()
        self._used = True
        self._thread = threading.get_ident()
        try:
            addresses = self._docker_addresses()  # Must succeed BEFORE any DB connection.
            self._engine = sa.create_engine(sa.URL.create(
                "postgresql+psycopg", username="scrapmart_test", password="local_test_only",
                host="127.0.0.1", port=55432, database="scrapmart_test",
            ), hide_parameters=True, poolclass=sa.pool.NullPool, isolation_level=self._isolation_level,
                connect_args={
                    # Explicit hostaddr defeats PGHOSTADDR/service-file routing.
                    "hostaddr": "127.0.0.1", "connect_timeout": 5, "sslmode": "disable",
                    "options": f"-c search_path={self.schema} -c statement_timeout=15000 -c lock_timeout=2000",
                })
            self._worker = self._engine.connect()
            with self._worker.begin():
                db = self._worker
                self._worker_pid = self._check_server(db, addresses)
                info = db.execute(sa.text(
                    "SELECT n.oid,n.nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user),"
                    "EXISTS(SELECT 1 FROM aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a "
                    "WHERE a.grantee<>n.nspowner) FROM pg_namespace n WHERE n.nspname=:schema"
                ), {"schema": self.schema}).one_or_none()
                if info is None or not info[1] or info[2] or not 0 < info[0] < 2**31:
                    raise MaintenanceRequired()
                self._schema_oid = info[0]
                if not db.scalar(sa.text("SELECT pg_try_advisory_lock(:class,:obj)"), {"class": _LOCK_CLASS, "obj": self._schema_oid}):
                    raise MaintenanceRequired()
            self._freezer = self._engine.connect()
            self._freeze_tx = self._freezer.begin()
            self._freezer.exec_driver_sql("SET LOCAL lock_timeout='2s'")
            self._freezer_pid = self._check_server(self._freezer, addresses)
            self._freezer.exec_driver_sql(f'LOCK TABLE "{self.schema}".users IN SHARE MODE')
            return self
        except BaseException as error:
            self.__exit__(None, None, None)
            if isinstance(error, SQLAlchemyError):
                raise MaintenanceRequired() from None
            raise

    def _assert_ownership(self, db):
        if (
            self._retired or db is not self._worker or self._worker is None or self._freezer is None
            or threading.get_ident() != self._thread
            or db.invalidated or self._freezer.invalidated
            or not self._freezer.in_transaction()
            or policy_fingerprint() != APPROVED_FINGERPRINT
        ):
            raise MaintenanceRequired()
        checks = db.execute(sa.text(
            "SELECT pg_backend_pid()=:worker,"
            "EXISTS(SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory' "
            "AND classid=:class AND objid=:obj AND objsubid=2 AND mode='ExclusiveLock' AND granted),"
            "EXISTS(SELECT 1 FROM pg_locks WHERE pid=:freezer AND locktype='relation' "
            "AND relation=CAST(:table AS regclass) AND mode='ShareLock' AND granted)"
        ), {"worker": self._worker_pid, "freezer": self._freezer_pid,
            "class": _LOCK_CLASS, "obj": self._schema_oid, "table": self.schema + ".users"}).one()
        if not all(checks):
            raise MaintenanceRequired()

    def __exit__(self, *_):
        # Never return a pooled backend retaining a session-level advisory lock.
        worker, freezer = self._worker, self._freezer
        self._worker = self._freezer = None
        try:
            if worker is not None:
                try:
                    worker.invalidate()
                finally:
                    worker.close()
        finally:
            try:
                if freezer is not None:
                    freezer.close()  # rolls back the freeze transaction
            finally:
                if self._engine is not None:
                    self._engine.dispose()

    def retire(self):
        """Irreversible context retirement, including its live DB connections."""
        self._retired = True
        self.__exit__(None, None, None)


class EmailIdentityBackfill:
    """Bounded engine; prepare/reprepare performs source + prefix checks only.

    No independent final verifier, readiness activation, or production entry point.
    Each successful batch result follows its durable transaction commit. Unknown
    commit outcomes poison this engine; use a NEW context and prepare again.
    """
    def __init__(self, context: IsolatedMaintenanceContext, *, batch_size=DEFAULT_BATCH_SIZE):
        if type(context) is not IsolatedMaintenanceContext or context._worker is None:
            raise MaintenanceRequired()
        self.context = context
        self.batch_size = checked_batch_size(batch_size)
        self._snapshot = self._checkpoint = None
        self._poisoned = False

    def _transaction(self, operation):
        if self._poisoned or self.context._worker is None or threading.get_ident() != self.context._thread:
            raise MaintenanceRequired()
        db = self.context._worker
        for attempt in range(3):
            tx = None
            committing = False
            try:
                tx = db.begin()
                db.exec_driver_sql("SET LOCAL statement_timeout='15s'")
                db.exec_driver_sql("SET LOCAL lock_timeout='2s'")
                db.exec_driver_sql("SET LOCAL synchronous_commit=on")
                self.context._assert_ownership(db)
                # Retain our OWN source fence through this transaction's commit,
                # even if the across-batch freezer connection dies mid-operation.
                db.exec_driver_sql(f'LOCK TABLE "{self.context.schema}".users IN SHARE MODE')
                result = operation(db)
                self.context._assert_ownership(db)
                committing = True
                tx.commit()
                return result
            except BaseException as error:
                if tx is not None:
                    try:
                        # A failed COMMIT can leave an inactive root transaction
                        # attached. Clear it before any confirmed-abort retry.
                        db.rollback()
                    except SQLAlchemyError:
                        self._poisoned = True
                code = getattr(getattr(error, "orig", None), "sqlstate", None)
                if isinstance(error, DBAPIError) and code in {"40001", "40P01"} and not db.invalidated and not self._poisoned and attempt < 2:
                    continue
                self._snapshot = self._checkpoint = None
                if committing or db.invalidated:
                    self._poisoned = True
                    self.context.retire()
                    raise CommitOutcomeUnknown() from None
                if isinstance(error, SQLAlchemyError):
                    raise BackfillError() from None
                raise

    def _state(self, db):
        p = self.context.policy
        state = db.execute(sa.select(p).where(p.c.id == POLICY_STATE_ID).with_for_update()).mappings().one_or_none()
        if state is None or state["status"] != "building" or state["policy_version"] != 1:
            raise CheckpointRejected()
        return state

    def _pages(self, db, *, after=None, through=None):
        u = self.context.users
        while True:
            query = sa.select(u.c.id, u.c.email).order_by(u.c.id).limit(self.batch_size)
            if after is not None:
                query = query.where(u.c.id > after)
            if through is not None:
                query = query.where(u.c.id <= through)
            rows = db.execute(query).all()
            if not rows:
                return
            yield [source_record(row.id, row.email) for row in rows]
            after = rows[-1].id

    @staticmethod
    def _write(db, table, records):
        rows = aggregate_aliases(records)
        if not rows:
            return
        statement = insert(table).values([dict(row, id=uuid.uuid4()) for row in rows])
        different = sa.or_(table.c.state == "blocked", statement.excluded.state == "blocked",
                           table.c.user_id.is_distinct_from(statement.excluded.user_id))
        db.execute(statement.on_conflict_do_update(
            index_elements=[table.c.lookup_key],
            set_={"state": sa.case((different, "blocked"), else_="owned"),
                  "user_id": sa.case((different, sa.null()), else_=table.c.user_id)},
            where=table.c.state != "blocked",
        ))

    def _reservation_rows(self, db, table):
        """Indexed merge inputs; no whole-registry fetch or hash-set operation."""
        after = None
        while True:
            query = sa.select(*(table.c[key] for key in (
                "lookup_key", "state", "user_id", "policy_version",
            ))).order_by(table.c.lookup_key).limit(self.batch_size)
            if after is not None:
                query = query.where(table.c.lookup_key > after)
            rows = db.execute(query).all()
            if not rows:
                return
            yield from (tuple(row) for row in rows)
            after = rows[-1].lookup_key

    def prepare(self) -> Checkpoint:
        def operation(db):
            state = self._state(db)
            count, last, digest = 0, None, _source_seed()
            for records in self._pages(db):
                for record in records:
                    digest = _extend(digest, record)
                count += len(records)
                last = records[-1].user_id
            snapshot = SourceSnapshot(count, last, digest)
            seed = _checkpoint_seed(snapshot)
            p, r = self.context.policy, self.context.reservations
            if state["manifest_sha256"] is None:
                if state["users_processed"] != 0 or state["last_user_id"] is not None or state["source_count"] != 0 or db.scalar(sa.select(sa.exists().where(r.c.id.is_not(None)))):
                    raise CheckpointRejected()
                db.execute(p.update().where(p.c.id == POLICY_STATE_ID).values(
                    source_count=count, manifest_sha256=seed, updated_at=sa.func.clock_timestamp(),
                ))
                return snapshot, Checkpoint(0, count, None, seed)
            if state["source_count"] != count or not 0 <= state["users_processed"] <= count:
                raise CheckpointRejected()
            # Resume guard, not an independent verifier: deliberately replay the
            # SAME aggregation/upsert logic into a session-local prefix table.
            name = "email_prefix_" + uuid.uuid4().hex
            db.exec_driver_sql(f'CREATE TEMP TABLE "{name}" (LIKE "{self.context.schema}".email_identity_reservations INCLUDING ALL) ON COMMIT DROP')
            expected = r.to_metadata(sa.MetaData(), schema="pg_temp", name=name)
            prefix_count, prefix_last, prefix_digest = 0, None, seed
            if state["last_user_id"] is not None:
                for records in self._pages(db, through=state["last_user_id"]):
                    self._write(db, expected, records)
                    for record in records:
                        prefix_digest = _extend(prefix_digest, record)
                    prefix_count += len(records)
                    prefix_last = records[-1].user_id
            if prefix_count != state["users_processed"] or prefix_last != state["last_user_id"] or prefix_digest != state["manifest_sha256"]:
                raise CheckpointRejected()
            if any(actual != wanted for actual, wanted in zip_longest(
                self._reservation_rows(db, r), self._reservation_rows(db, expected),
            )):
                raise CheckpointRejected()
            return snapshot, Checkpoint(prefix_count, count, prefix_last, prefix_digest)
        self._snapshot, self._checkpoint = self._transaction(operation)
        return self._checkpoint

    def run_batch(self) -> Checkpoint:
        if self._snapshot is None or self._checkpoint is None:
            raise MaintenanceRequired()
        def operation(db):
            state = self._state(db)
            current = Checkpoint(state["users_processed"], state["source_count"], state["last_user_id"], state["manifest_sha256"])
            if current != self._checkpoint:
                raise CheckpointRejected()
            records = next(self._pages(db, after=current.last_user_id), [])
            if not records:
                if not current.source_exhausted or current.last_user_id != self._snapshot.last_user_id:
                    raise CheckpointRejected()
                return current
            processed = current.users_processed + len(records)
            if processed > current.source_count:
                raise CheckpointRejected()
            digest = current.digest
            for record in records:
                digest = _extend(digest, record)
            self._write(db, self.context.reservations, records)
            p = self.context.policy
            db.execute(p.update().where(p.c.id == POLICY_STATE_ID).values(
                users_processed=processed, last_user_id=records[-1].user_id,
                manifest_sha256=digest, updated_at=sa.func.clock_timestamp(),
            ))
            return Checkpoint(processed, current.source_count, records[-1].user_id, digest)
        self._checkpoint = self._transaction(operation)
        return self._checkpoint
