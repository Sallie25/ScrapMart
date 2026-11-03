# Batch 3B.4 — session security hardening

No authentication flow is activated. No PostgreSQL, Docker, Neon, Render or Vercel
access occurred in this batch. Dependencies, backend, PRD and marketplace UI are
unchanged. The 3B.3 document is a historical report of the previous implementation;
its database test counts do not validate this revision.

## Owned connection boundary

SessionStore now accepts only five plain data settings: host, port, database,
user and password. It rejects pg clients, shared pools, query adapters, unexpected
properties and accessors before invoking them. Local target restrictions remain.
There is no production injection hook. The store creates a private pool and never
exposes its pool, checked-out clients, query methods or transaction callbacks.

The refresh claim runs as one autocommit statement on an owned connection.
Upstream is invoked only after that statement's result is acknowledged and the
connection is released. Startup options explicitly set synchronous_commit=on;
the underlying PostgreSQL durability/storage configuration must still be valid.
Completion uses a fresh checked-out connection with internally owned BEGIN/COMMIT.
Failed/uncertain connections are destroyed, with best-effort rollback and generic
errors. close() shuts down only that store's owned pool. Consumers must construct
one store per configured service lifecycle, not one pool per HTTP request.

## Fail-closed completion by opaque identifier rotation

Keeping the same browser identifier active after refresh cannot guarantee
quarantine if COMMIT succeeds, its acknowledgment is lost and later writes fail.
The new protocol instead makes the browser's existing identifier unusable in
either possible durable outcome:

1. Commit the active -> refreshing claim before dispatch. Never retry upstream or
   allow timeout takeover of an abandoned claim.
2. Receive and validate one synthetic/future upstream replacement. Generate a new
   random browser identifier and encrypt the replacement bound to its hash.
3. In one transaction, lock the stable root row and verify it is unrevoked and
   unexpired, conditionally retire the old identifier using its attempt UUID, erase
   its old envelope, and insert the new active identifier with unchanged absolute
   expiry and the same root hash.
4. Return the new browser identifier ONLY after COMMIT is acknowledged. A future
   HTTP adapter must replace the HttpOnly browser cookie with this returned value.

If completion did not commit, the browser's identifier remains refreshing (or
uncertain if cleanup succeeds). If completion committed but its acknowledgment
was lost, that identifier is retired. Both deny access/refresh across instances.
The possible active successor is an undisclosed orphan: only its SHA-256 hash is
stored, no API resolves successors from old identifiers, and the raw value is
never returned on an error. Best-effort quarantine only updates the matching
refreshing attempt; it cannot overwrite a retired or revoked row.

This is not a claim that all orphans are durably quarantined. It deliberately
abandons them rather than recovering them or replaying credentials. A later owner
cleanup can remove whole expired families. Lost responses, process crashes or
failure to deliver the new cookie can force reauthentication even when upstream
refresh succeeded. The callback must still issue at most one bounded upstream
request without its own retry. There is no grace window or automatic recovery.

## Logout and family state

Each record has an immutable root_hash referencing the original session row.
That root remains the stable revocation gate after its identifier is retired.
All lookup/access/refresh paths check root revocation and expiry. Revocation via
any retained identifier updates that root. Completion locks the same root, so
logout before completion prevents insertion, and logout after committed completion
also blocks a late successor before/after cookie handoff. Already dispatched
requests cannot be recalled. Backend HTTP session revocation remains separate.

## Schema and compatibility

schema.sql is updated for a NEW disposable database only, not an upgrade migration:
root_hash NOT NULL/self-reference, retired state, corresponding envelope constraint,
and an explicit INSERT grant for root_hash. No runtime UPDATE permission on root_hash
is granted. Existing identifier/expiry ownership and other restricted grants remain.
No SQL was executed. A separately reviewed migration would be needed for an existing
installation. Do not apply this script to a shared database.

API changes: SessionStore(settings, vault) replaces arbitrary query adapters;
refresh() returns a new opaque identifier; callers must use it for later requests;
logout through an old retained identifier revokes the family. create() and public
lookup metadata remain credential-free. Encryption keys/credentials stay server-only.

## Validation boundaries and next step

The explicit Node test loader substitutes a pg boundary double only for the
owned database module during offline testing. Production Next imports use real pg.
The isolated PostgreSQL test path uses a separate wrapper around real pg clients
for controlled acknowledgment/failure injection. No source constructor accepts
those wrappers. Driver doubles and their in-memory records are test-only.

Offline coverage includes constructor rejection without invocation, committed
claim before dispatch, failed completion rollback, commit-acknowledgment loss plus
failed quarantine or total storage outage, fresh-instance denial of old identifiers,
old-token non-reuse, family revocation across generations, logout during refresh
and before late handoff, encryption/key handling and pool shutdown/outage behavior.

Real PostgreSQL tests and restart phases have been updated, but NOT run here. A
NEW separately authorized disposable environment is required to verify the new
self-reference/grants, owned pools, root locking, atomic retirement/insertion,
ancestor logout, uncertain completion and restart persistence. Previous 3B.3
results must not be reused as acceptance evidence for the changed schema/protocol.

Live authentication is not ready for activation. After PostgreSQL revalidation,
the future HTTP adapter still needs backend cookie capture/rotation, correct
Origin/CSRF and no-store controls, browser cookie handoff, serialized refresh,
backend logout handling and explicit reauthentication for ambiguous outcomes.

## Executed checks

- Offline tests: **39 passed, zero failed, one PostgreSQL opt-in check skipped**
  (28 session tests plus 11 existing frontend tests).
- npm run lint: passed.
- npx tsc --noEmit --incremental false: passed.
- npm run build -- --webpack: passed; all 15 pages generated.
- Updated PostgreSQL test/helper syntax checks: passed, without executing SQL.
- git diff --check: passed. Pre-existing UI/assets/dependency files retain their
  starting fingerprints; only the scoped session SQL, implementation and tests
  were modified, with new session database/test-driver modules and this report.
- No real PostgreSQL tests, restarts or provider requests were executed in 3B.4.
