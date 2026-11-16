"""Independent, read-only Step 3A verification; never a readiness certificate.

Restricted to the existing isolated maintenance context, NOT a production entry
point. PostgreSQL runs REPEATABLE READ READ ONLY. Private temporary files contain
derived identifiers, are removed on exit, and require trusted local storage.
Memory and open files are bounded; scratch disk and total work scale with source.
No backfill aggregation, upsert, or checkpoint reconstruction is reused.
"""
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import heapq
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from app.modules.auth.email_identity_backfill import IsolatedMaintenanceContext, MaintenanceRequired
from app.modules.auth.email_identity_models import POLICY_STATE_ID
from app.modules.auth.email_identity_policy import legacy_email_identity, policy_fingerprint

FINGERPRINT = "cbdc5198ab2b1c3f23062e5318c97f0ab4e403023a69035e355bc8e8c431e59f"
FAN_IN = 16


class VerificationError(RuntimeError):
    def __init__(self):
        super().__init__("Email identity verification failed; maintenance review required")


@dataclass(frozen=True)
class VerificationReport:
    """Snapshot observation only. No permission to activate readiness or login."""
    source_count: int
    zero_alias_count: int
    expected_count: int
    actual_count: int
    issues: tuple[tuple[str, int], ...]
    source_manifest: str
    expected_manifest: str
    actual_manifest: str
    fingerprint: str

    @property
    def passed(self):
        return not self.issues


def _bound(value):
    if type(value) is not int or not 1 <= value <= 1000:
        raise ValueError("Verification batch size must be between 1 and 1000")
    return value


def _digest(digest, row):
    data = json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    digest.update(len(data).to_bytes(8, "big"))
    digest.update(data)


def _read(path):
    with path.open(encoding="ascii") as stream:
        for line in stream:
            yield tuple(json.loads(line))


def _write(path, rows):
    # Directory is private (0700), and files are explicitly private (0600).
    with path.open("x", encoding="ascii") as stream:
        path.chmod(0o600)
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n")


class _Sort:
    def __init__(self, directory, limit):
        self.directory, self.limit = Path(directory), limit
        self.pending, self.runs = [], 0

    def add(self, row):
        self.pending.append(row)
        if len(self.pending) >= self.limit:
            self.flush()

    def flush(self):
        if self.pending:
            _write(self.directory / f"0-{self.runs}", sorted(self.pending))
            self.runs += 1
            self.pending.clear()

    def rows(self):
        self.flush()
        level, count = 0, self.runs
        while count > 1:
            following = 0
            for first in range(0, count, FAN_IN):
                paths = [self.directory / f"{level}-{n}" for n in range(first, min(first + FAN_IN, count))]
                with ExitStack() as stack:
                    streams = [stack.enter_context(p.open(encoding="ascii")) for p in paths]
                    iterators = [(tuple(json.loads(line)) for line in stream) for stream in streams]
                    _write(self.directory / f"{level+1}-{following}", heapq.merge(*iterators))
                for path in paths:
                    path.unlink()
                following += 1
            level, count = level + 1, following
        if count:
            yield from _read(self.directory / f"{level}-0")


def _expected(rows):
    """Streaming distinct-owner reduction, independent of backfill's upsert."""
    key = owner = None
    blocked = False
    for next_key, next_owner, mandatory in rows:
        if key is not None and next_key != key:
            yield (key, "blocked" if blocked else "owned", None if blocked else owner, 1)
            key = None
        if key is None:
            key, owner, blocked = next_key, next_owner, bool(mandatory)
        else:
            blocked = blocked or bool(mandatory) or owner != next_owner
    if key is not None:
        yield (key, "blocked" if blocked else "owned", None if blocked else owner, 1)


class EmailIdentityVerifier:
    def __init__(self, context, *, batch_size=500):
        if type(context) is not IsolatedMaintenanceContext or context._worker is None:
            raise MaintenanceRequired()
        self.context, self.batch_size = context, _bound(batch_size)

    def _pages(self, db, table, key, columns):
        after = None
        while True:
            query = sa.select(*columns).order_by(key).limit(self.batch_size)
            if after is not None:
                query = query.where(key > after)
            rows = db.execute(query).all()
            if not rows:
                return
            yield from rows
            after = rows[-1][0]

    def verify(self):
        if policy_fingerprint() != FINGERPRINT:
            raise VerificationError()
        db = self.context._worker
        if db is None or db.in_transaction():
            raise MaintenanceRequired()
        try:
            with db.begin():
                db.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                db.exec_driver_sql("SET LOCAL statement_timeout='15s'")
                db.exec_driver_sql("SET LOCAL lock_timeout='2s'")
                self.context._assert_ownership(db)
                with TemporaryDirectory(prefix="scrapmart-email-verifier-") as directory:
                    report = self._verify(db, directory)
                self.context._assert_ownership(db)
            return report
        except (SQLAlchemyError, OSError):
            raise VerificationError() from None

    def _verify(self, db, directory):
        c = self.context
        issues = Counter()
        state = db.execute(sa.select(c.policy).where(c.policy.c.id == POLICY_STATE_ID)).mappings().one_or_none()
        if state is None or state["status"] != "building" or state["policy_version"] != 1:
            issues["policy_state"] += 1
        source_hash = hashlib.sha256(b"email-verifier-source-v1\0" + FINGERPRINT.encode("ascii"))
        expected_hash = hashlib.sha256(b"email-verifier-reservations-v1\0")
        actual_hash = hashlib.sha256(b"email-verifier-reservations-v1\0")
        sorter = _Sort(directory, self.batch_size)
        count = zero = 0
        last = None
        for user_id, email in self._pages(db, c.users, c.users.c.id, (c.users.c.id, c.users.c.email)):
            count += 1
            last = user_id
            identity = legacy_email_identity(email)
            _digest(source_hash, (user_id.hex, email, identity.classification.value,
                                  [(a.key, a.disposition.value) for a in identity.aliases]))
            if identity.blocks_readiness or identity.fingerprint != FINGERPRINT or identity.policy_version != 1:
                issues["invalid_source"] += 1
                continue
            if not identity.aliases:
                zero += 1
            for alias in identity.aliases:
                sorter.add((alias.key, user_id.hex, alias.disposition.value == "blocked"))
        if state is not None:
            if state["source_count"] != count:
                issues["source_count"] += 1
            if state["users_processed"] != count or state["last_user_id"] != last:
                issues["incomplete_checkpoint"] += 1
            if state["manifest_sha256"] is None:
                issues["missing_checkpoint_manifest"] += 1
        # Checkpoint digest is deliberately NOT trusted as verification evidence.
        # These independently domain-separated manifests are not backfill digests.
        actual_rows = self._pages(db, c.reservations, c.reservations.c.lookup_key, (
            c.reservations.c.lookup_key, c.reservations.c.state,
            c.reservations.c.user_id, c.reservations.c.policy_version))
        def actual():
            for key, status, owner, version in actual_rows:
                yield key, status, owner.hex if owner is not None else None, version
        expected_iter, actual_iter = iter(_expected(sorter.rows())), iter(actual())
        expected, observed = next(expected_iter, None), next(actual_iter, None)
        expected_count = actual_count = 0
        while expected is not None or observed is not None:
            if observed is None or (expected is not None and expected[0] < observed[0]):
                issues["missing_key"] += 1
                take_expected, take_actual = True, False
            elif expected is None or observed[0] < expected[0]:
                issues["unexpected_key"] += 1
                take_expected, take_actual = False, True
            else:
                for index, name in ((1, "state"), (2, "ownership"), (3, "policy_version")):
                    if expected[index] != observed[index]:
                        issues[name] += 1
                take_expected = take_actual = True
            if take_expected:
                expected_count += 1
                _digest(expected_hash, expected)
                expected = next(expected_iter, None)
            if take_actual:
                actual_count += 1
                if observed[3] != 1 and not take_expected:
                    issues["policy_version"] += 1
                _digest(actual_hash, observed)
                observed = next(actual_iter, None)
        return VerificationReport(count, zero, expected_count, actual_count,
                                  tuple(sorted(issues.items())), source_hash.hexdigest(),
                                  expected_hash.hexdigest(), actual_hash.hexdigest(), FINGERPRINT)
