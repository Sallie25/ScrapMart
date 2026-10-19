"""Local isolated-schema finalization only. No deployment/registration interface.

Users, reservations and policy are write-fenced through the final commit. The
independent verifier is invoked inside that same transaction, rather than trusting
a prior report. Checkpoint bytes are reconstructed from the entire ordered source
using the Step 2 wire format, independently of its writer implementation.

The checkpoint authenticates a deterministic traversal, not an audit trail of
historical batches (the schema stores no batch journal). A lost commit response
has an uncertain outcome: inspect durable state in a NEW maintenance context;
never retry blindly or assume a reported error undid an acknowledged-by-server
commit. Production writer/role provisioning remains out of scope.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
from tempfile import TemporaryDirectory

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from app.modules.auth.email_identity_backfill import IsolatedMaintenanceContext, MaintenanceRequired
from app.modules.auth.email_identity_models import POLICY_STATE_ID
from app.modules.auth.email_identity_policy import legacy_email_identity, policy_fingerprint
from app.modules.auth.email_identity_verifier import EmailIdentityVerifier, VerificationReport

FINGERPRINT = "cbdc5198ab2b1c3f23062e5318c97f0ab4e403023a69035e355bc8e8c431e59f"


class FinalizationError(RuntimeError):
    def __init__(self):
        super().__init__("Local readiness finalization rejected; maintenance review required")


class FinalizationOutcomeUnknown(FinalizationError):
    """Commit acknowledgement was lost; re-open context and inspect durable state."""


@dataclass(frozen=True)
class LocalFinalizationResult:
    verification: VerificationReport
    checkpoint_digest: bytes


def _extend(digest, user_id, email, identity):
    payload = json.dumps({
        "id": user_id.hex, "email": email,
        "classification": identity.classification.value,
        "aliases": [(a.key, a.disposition.value) for a in identity.aliases],
    }, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(digest + len(payload).to_bytes(4, "big") + payload).digest()


class LocalEmailIdentityFinalizer:
    def __init__(self, context, *, batch_size=500):
        # Reuses only the verified local target/freeze boundary, never backfill writes.
        self.verifier = EmailIdentityVerifier(context, batch_size=batch_size)
        self.context = context

    def _source(self, db):
        c = self.context
        for user_id, email in self.verifier._pages(db, c.users, c.users.c.id, (c.users.c.id, c.users.c.email)):
            identity = legacy_email_identity(email)
            if identity.blocks_readiness or identity.policy_version != 1 or identity.fingerprint != FINGERPRINT:
                raise FinalizationError()
            yield user_id, email, identity

    def _checkpoint(self, db, state):
        source = hashlib.sha256(b"scrapmart-email-source-v1\0" + FINGERPRINT.encode("ascii")).digest()
        count, last = 0, None
        for user_id, email, identity in self._source(db):
            source = _extend(source, user_id, email, identity)
            count, last = count + 1, user_id
        if state["source_count"] != count or state["users_processed"] != count or state["last_user_id"] != last:
            raise FinalizationError()
        digest = hashlib.sha256(
            b"scrapmart-email-checkpoint-v1\0" + FINGERPRINT.encode("ascii")
            + source + count.to_bytes(8, "big") + (last.bytes if last is not None else bytes(16))
        ).digest()
        for user_id, email, identity in self._source(db):
            digest = _extend(digest, user_id, email, identity)
        stored = state["manifest_sha256"]
        if stored is None or not hmac.compare_digest(digest, stored):
            raise FinalizationError()
        return digest

    def finalize(self):
        c = self.context
        if type(c) is not IsolatedMaintenanceContext or c._worker is None or c._worker.in_transaction():
            raise MaintenanceRequired()
        if policy_fingerprint() != FINGERPRINT:
            raise FinalizationError()
        db = c._worker
        committing = False
        try:
            tx = db.begin()
            # READ COMMITTED observes writers that finished before lock acquisition.
            # Once acquired, all three tables remain stable until our commit.
            db.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ WRITE")
            db.exec_driver_sql("SET LOCAL statement_timeout='15s'")
            db.exec_driver_sql("SET LOCAL lock_timeout='2s'")
            db.exec_driver_sql("SET LOCAL synchronous_commit=on")
            c._assert_ownership(db)
            for name, mode in (("users", "SHARE"), ("email_identity_reservations", "SHARE"),
                               ("email_identity_policy_state", "EXCLUSIVE")):
                db.exec_driver_sql(f'LOCK TABLE "{c.schema}"."{name}" IN {mode} MODE')
            state = db.execute(sa.select(c.policy).where(c.policy.c.id == POLICY_STATE_ID).with_for_update()).mappings().one_or_none()
            if state is None or state["status"] != "building" or state["policy_version"] != 1:
                raise FinalizationError()
            digest = self._checkpoint(db, state)
            # _verify is the unchanged independent comparison core. Its public
            # verify() owns a read-only transaction and cannot be nested here.
            with TemporaryDirectory(prefix="scrapmart-email-finalization-") as directory:
                report = self.verifier._verify(db, directory)
            if not report.passed or report.fingerprint != FINGERPRINT or policy_fingerprint() != FINGERPRINT:
                raise FinalizationError()
            c._assert_ownership(db)
            result = db.execute(c.policy.update().where(
                c.policy.c.id == POLICY_STATE_ID, c.policy.c.status == "building",
                c.policy.c.policy_version == 1, c.policy.c.manifest_sha256 == digest,
            ).values(status="ready", updated_at=sa.func.clock_timestamp()))
            if result.rowcount != 1:
                raise FinalizationError()
            c._assert_ownership(db)
            committing = True
            tx.commit()
            return LocalFinalizationResult(report, digest)
        except BaseException as error:
            try:
                db.rollback()
            except SQLAlchemyError:
                db.invalidate()
            if committing:
                db.invalidate()
                # Do not leave this context available for a blind retry.
                c.retire()
                raise FinalizationOutcomeUnknown() from None
            if isinstance(error, (SQLAlchemyError, OSError)):
                raise FinalizationError() from None
            raise
