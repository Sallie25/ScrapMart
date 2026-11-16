import uuid

import pytest
import sqlalchemy as sa

from app.modules.auth.email_identity_backfill import IsolatedMaintenanceContext, MaintenanceRequired
from app.modules.auth.email_identity_finalization import FINGERPRINT, LocalEmailIdentityFinalizer, _extend
from app.modules.auth.email_identity_policy import legacy_email_identity


@pytest.mark.parametrize("candidate", [None, object(), lambda: None])
def test_requires_real_local_maintenance_context(candidate):
    with pytest.raises(MaintenanceRequired):
        LocalEmailIdentityFinalizer(candidate)


@pytest.mark.parametrize("url,schema", [
    ("postgresql+psycopg://scrapmart_test@127.0.0.1:55432/scrapmart_test", "public"),
    ("postgresql+psycopg://scrapmart_test@remote.invalid:55432/scrapmart_test", "email_backfill_" + "a"*32),
    ("postgresql+psycopg://scrapmart_test@127.0.0.1:5432/scrapmart_test", "email_backfill_" + "a"*32),
])
def test_caller_engines_rejected_without_connecting(url, schema):
    engine = sa.create_engine(url)
    try:
        with pytest.raises(MaintenanceRequired):
            IsolatedMaintenanceContext(engine, expected_fingerprint=FINGERPRINT)
    finally:
        engine.dispose()


def test_checkpoint_wire_format_golden():
    # Separate fixed expected serialization, including a zero-alias source.
    import hashlib
    identity = legacy_email_identity("Σ@example.test")
    payload = b'{"aliases":[],"classification":"zero_ascii_aliases","email":"\\u03a3@example.test","id":"00000000000000000000000000000001"}'
    wanted = hashlib.sha256(bytes(32) + len(payload).to_bytes(4, "big") + payload).digest()
    assert _extend(bytes(32), uuid.UUID(int=1), "Σ@example.test", identity) == wanted
