# Batch 3B.5 — hardened session PostgreSQL revalidation

Branch: feature/frontend-buyer-vendor-integration.
HEAD: 0fb6e37af284bc5995fc71536b2fa0fb30b02346.
No production/session implementation, SQL, dependencies, UI or backend changes.
The PostgreSQL suite now stops after its first failed scenario; existing assertions
were preserved. No security assertion failed in this run.

## Isolation and cleanup

Both dedicated names were verified absent before creation:
scrapmart-bff-3b3 and scrapmart-bff-3b3-data. A fresh container/volume used the
previously approved isolation runner and cached image digest:
sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d.

Before SQL, host Docker metadata verified exact container/image identity,
network=none, no published ports, no host mounts, one dedicated named volume,
batch label and unique run label. Test workers ran inside that container, checked
that only loopback existed, and used the dedicated scrapmart_bff_local_test database.
Only synthetic test data/keys were used. No environment files/cloud credentials
were loaded. No Neon, Render, Vercel or FastAPI requests were made.

The UPDATED 3B.4 fresh-install schema was applied by the disposable owner. Its
restricted runtime role was enabled only within the network-isolated fixture.
Workers exited before cleanup. The supervisor re-inspected exact container and
volume identities/labels before deletion. A separate host-side check then compared
Docker metadata with the pre-run baseline: both dedicated names were absent, all
pre-existing container IDs/names and volume names remained present. Synthetic keys
and data were removed with the dedicated resources. No existing resource was reset,
restarted, stopped, deleted or used for SQL.

## Results

Executed: python3 tests/run-isolated-postgres.py --run-isolated.

- **26 PostgreSQL scenario subtests passed**, plus their enclosing test:
  **27 reported passes**, zero failed, zero skipped.
- **Six restart verification checks passed**: active session/ciphertext survives;
  revoked, uncertain, refreshing and retired identifiers remain blocked; logout
  through the retired root revokes the surviving active successor.

The actual restricted login successfully exercised create/lookup/access and the
updated root_hash foreign key/INSERT permission. Owner/runtime separation,
non-elevated attributes, membership/CREATE/TEMP restrictions, protected columns,
DDL/deletion/truncation denial, unchanged PUBLIC grants and lifecycle constraints
passed. Unauthorized GRANT was validated by catalog outcome, not assumed errors.

Concurrency/failure evidence includes independent owned pools, exactly one refresh
owner, real PostgreSQL row blocking and predicate re-evaluation, statement timeout,
session expiry during refresh, no token replay, real connection refusal/termination,
owned-pool exhaustion/recovery, fresh Node processes and SIGKILL after a committed
claim. Corruption, cross-row encryption binding, unknown key versions and retained
key rotation checks passed.

Both hardened boundaries passed their real-PostgreSQL regression checks:

1. Transaction-bound clients/shared pools/query adapters are rejected before
   dispatch; the private owned-pool claim is visible from an independent connection
   while upstream is paused. No caller-owned transaction is accepted.
2. A committed completion with lost acknowledgment and failed quarantine leaves
   the old browser identifier retired and unusable for lookup, access or refresh.
   Its undisclosed successor is not recovered. Retirement remains blocked after a
   real PostgreSQL restart. Logout through retired ancestors and logout between
   committed completion and identifier handoff both block the current successor.

Lost acknowledgments/quarantine failures were injected around actual pg operations
and real commits, not through packet-loss tooling. Upstream callbacks were synthetic.
Tests used the fixture's default Read Committed isolation. This is not verification
of arbitrary provider settings, real backend HTTP behavior or every isolation level.

Offline command:
node --import ./tests/helpers/session-loader.mjs --test --test-isolation=none tests/*.test.mjs

Result: **39 passed, one integration opt-in check skipped, zero failed**. The skip
prevents offline execution against an arbitrary database; real integration passed
separately above. Lint and Webpack production build passed; all 15 pages generated.
Standalone TypeScript and final preservation/diff checks are in the final report.

## Readiness and remaining boundaries

No failures remain in the executed scenarios. The two earlier limitations are
addressed and locally revalidated. The foundation is ready for a separately scoped
authentication-integration implementation batch, not activation/deployment.

Undisclosed orphan successors may remain active in storage until owner cleanup;
their identifiers cannot be recovered from stored hashes or old browser identifiers.
Lost responses may require reauthentication. Backend revocation is still separate
from local family revocation. Cookie handoff, backend refresh-cookie handling,
Origin/CSRF/no-store controls, backend logout and browser acceptance still require
implementation/testing. Cloud targets/settings were not inspected or changed.
The SQL remains a fresh-install script, not an existing-database migration.
