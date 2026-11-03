# Batch 3B.3 — isolated PostgreSQL validation

Branch: feature/frontend-buyer-vendor-integration.
Baseline HEAD: 0fb6e37af284bc5995fc71536b2fa0fb30b02346.
This batch adds test infrastructure only. Application/session implementation,
reviewed SQL, package dependencies, existing UI and backend files are unchanged.
No cloud database or backend API was contacted; authentication remains inactive.

## Isolation and lifecycle

Run only with explicit disposable-resource authorization:

```
python3 tests/run-isolated-postgres.py --run-isolated
```

The opt-in runner checks the required branch and rejects existing names before
creating anything. It uses exactly:

- Container: scrapmart-bff-3b3.
- Volume: scrapmart-bff-3b3-data.
- Cached official image digest:
  sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d.
- Network: none; PostgreSQL listens on 127.0.0.1 inside the container.
- No published ports, host networking, bind mounts or Docker socket mount.
- One dedicated data volume, batch label and unique per-run label.
- Database: scrapmart_bff_local_test. Runtime role: scrapmart_bff_runtime.

Image ID, container ID, labels, mount, volume metadata and empty port mappings
are checked before SQL, test phases, restart and cleanup. Workers additionally
require a fixture marker, loopback as their only network interface, and the exact
database/user/PostgreSQL 16 identity. Trust authentication and LOGIN activation
exist only inside this disposable network namespace; no passwords are generated.

Passwordless sudo was unavailable. Instead of nsenter, the runner copies the
existing Node executable, installed pg dependency closure, session modules and
allowlisted tests into the container. No package/image downloads are performed.
No frontend/backend environment files are copied or loaded. Test Node processes
run under env -i with only the synthetic opt-in flag. Keys and identifiers are
synthetic, generated inside the container and never printed. Restart fixture
material uses a temporary mode-0600 file in the disposable container layer.

The unchanged schema.sql is applied using the disposable postgres owner, followed
by local-only runtime LOGIN activation. No schema is installed on a shared server.

The runner waits for synchronous workers to exit; on errors/timeouts it stops the
exact verified container before deleting it and its exact verified volume. A
cleanup identity mismatch aborts deletion. It verifies both names are absent and
all pre-existing container/volume names remain after cleanup. It never resets,
starts, stops or removes existing fixtures. A host/daemon crash or SIGKILL of the
supervisor can still prevent finally cleanup: inspect identity/labels before any
manual recovery. Never use prune, wildcard deletion or automatic name adoption.

## Executed PostgreSQL results

Final run: **24 scenario subtests passed**, plus their enclosing test (**25/25 in
Node's report**). Four further database-restart verification checks passed.

Verified using the actual restricted login and independent PostgreSQL connections:

- Schema/table owner separation, non-elevated runtime attributes, no outward role
  memberships, no database/schema CREATE or TEMP privileges.
- Allowed inserts/reads/updates; denied DDL, DELETE, TRUNCATE, protected-column
  updates, SET ROLE and elevated role changes.
- An unauthorized GRANT can warn and succeed as a no-op. Catalog checks confirm
  PUBLIC gains zero table privileges and runtime has no SELECT grant option.
- SQL hash, expiry and lifecycle constraints reject inconsistent records.
- One refresh owner across independent pools, a visible committed refresh fence,
  real row blocking verified with pg_blocking_pids, predicate re-evaluation after
  competing revocation, and statement-timeout cancellation before upstream dispatch.
- Database-clock session expiry, expiry during refresh, idempotent logout and
  logout racing a late refresh completion without resurrection.
- Lost upstream response blocks replay. Rotation uses the committed replacement;
  returning the old refresh value is rejected.
- Lost claim/completion acknowledgments and failed quarantine writes, using
  controlled exceptions around real SQL commits (not real packet-loss injection).
- Encrypted storage, ciphertext corruption, cross-row envelope swaps, unknown key
  versions, retained-key reads and re-encryption on refresh with a new key version.
- Real refused/terminated connections, exhausted-pool errors and recovery.
- Fresh Node processes recover committed sessions with a retained synthetic key.
  SIGKILL after claim leaves the session permanently fenced across process restart.
- A real container/PostgreSQL restart changes postmaster start time. Active
  ciphertext remains usable; revoked, uncertain and refreshing records stay blocked.

Upstream callbacks are synthetic: no FastAPI login, refresh or logout HTTP request
was made. PostgreSQL tests do not establish browser cookie/CSRF behavior or live
provider suitability. The tests use PostgreSQL's default Read Committed isolation;
they do not certify other isolation modes or arbitrary query adapters.

Initial unsuccessful runs exposed test-harness issues, corrected without changing
the implementation: inet text included /32; root-level asynchronous test cleanup
was scoped incorrectly; unauthorized GRANT was incorrectly assumed to throw.
The hanging worker was stopped before cleanup. Each attempted lifecycle verified
removal of its dedicated resources before the next run.

## Confirmed limitations — not security acceptance passes

Two passing diagnostic subtests characterize limitations; they do not certify
those behaviors as satisfying all live-authentication requirements:

1. **Completion committed + acknowledgment lost + quarantine failed:** the durable
   row can remain active. A fresh instance can use its stored replacement; the old
   refresh token is not replayed. The current code cannot guarantee durable
   quarantine in this case. Live integration needs an explicit reconciliation or
   reauthentication policy and tests for that policy. An error does not imply the
   row is necessarily refreshing/uncertain.
2. **Autocommit is not enforced by SessionStore's constructor:** a transaction-bound
   adapter can dispatch upstream while another connection still sees active state.
   The existing factory uses a Pool, which meets the intended contract, but callers
   can violate it through the exported constructor. Enforce or encapsulate this
   boundary before live integration.

Local revoke still does not revoke a FastAPI session. A future HTTP adapter must
coordinate backend logout, handle late upstream replacements, enforce Origin/CSRF
and body limits, serialize refresh, avoid retries of consumed credentials, and
keep credentials out of browser DTOs, logs and JavaScript. These remain separate
work; no authentication routes/actions were activated here.

## Other validation

Offline command (database integration safely skips without its isolated marker):

```
node --import ./tests/helpers/session-loader.mjs --test --test-isolation=none tests/*.test.mjs
```

Result: 28 passed, one integration opt-in test skipped, zero failed.
Lint, standalone TypeScript, Webpack build and diff checks are recorded in the
final task report. No new local-only dependency is required.

Cleanup succeeded: dedicated container and volume removed, synthetic keys/data
removed with them, pre-existing resource names preserved. The fixture is suitable
for further local security work. It does not authorize or certify Step 2 live
authentication integration while the above boundaries remain unresolved.
