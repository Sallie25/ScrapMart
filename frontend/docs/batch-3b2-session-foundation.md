# Batch 3B.2 local session foundation

This is an unconnected server-side library, not an activated authentication flow.
No routes, actions, UI, cookies, login calls, database connections or migrations
are activated by importing it. Existing UI remains a demo. Node runtime required.

## Storage and cryptography

`src/lib/server/sessions/` is protected by Next's `server-only` import marker.
The framework supplies that marker; no additional package is needed. Never mark
these modules `use server`: that would turn exports into callable actions.

The browser identifier contains 32 random bytes, encoded as canonical base64url.
Only its SHA-256 hex digest is persisted. AES-256-GCM encrypts the access token,
refresh-cookie **value**, and access expiry together. Every encryption uses a new
12-byte nonce, a 16-byte tag, an explicit key version and additional authenticated
data binding the envelope to its identifier hash, format and key version.
Retained key versions decrypt existing rows; new writes use the current version.
Unknown/missing keys and authentication failures deny use, without plaintext
fallback. Key material uses private class fields and is copied at construction.
Removing an old key invalidates rows still encrypted under it. No automatic bulk
reencryption is implemented. Backups contain encrypted credentials but still need
access controls; key material must be managed separately.

`create` returns the browser identifier only after an acknowledged insert.
`lookup` returns expiry metadata only for active unexpired records. `withAccess`
is an internal credential-use callback, never a browser DTO; callers must never
return its credential argument from routes/actions or log it. Backend permissions
and live-session checks remain authoritative. Local records are not permission
grants. Expired access tokens require refresh; local expiry never extends.

## Refresh and logout protocol

The source of truth is the separate FastAPI backend's
`app/modules/auth/http_security.py`, `session_service.py` and `README.md`:
login issues access JSON and `__Secure-scrapmart_refresh`; refresh/logout accept
that cookie only, require exact allowed Origin plus `X-ScrapMart-CSRF: 1`, and
refresh rotation never extends absolute backend expiry. Reusing a consumed token
revokes its backend session. Backend JWT defaults: 15 minutes; session: seven days.

The BFF atomically commits active -> refreshing with an attempt UUID BEFORE the
upstream callback. PostgreSQL's conditional UPDATE is the coordination boundary
across instances. Other instances deny refresh/access while refreshing. There is
no timeout takeover: an abandoned attempt cannot safely be replayed. The callback
is invoked once and must itself issue exactly one upstream request, with a bounded
timeout and no retries. It must validate status/body/Set-Cookie and return a fresh
refresh-cookie value and access expiry. This batch deliberately supplies no HTTP
adapter. Tests supply callbacks only; nothing contacts FastAPI.

Success replaces the envelope only if the attempt still owns a refreshing,
unexpired row. Failure, malformed credentials, an unchanged refresh credential,
or uncertain upstream outcome quarantines the record as uncertain and erases its
envelope. If quarantine storage fails, the previously committed refreshing claim
remains blocked. A lost claim acknowledgment never permits upstream dispatch.
A lost completion acknowledgment attempts quarantine even if completion committed.
No distributed transaction can make the upstream and local commits atomic: after
a process crash an attempt can remain permanently refreshing, or an upstream
replacement can be lost. Reauthentication is the conservative recovery; no retry
or expired-lease recovery is provided. Owner cleanup can remove expired rows.

`revoke` provides local logout immediately, even during refresh. Completion cannot
revive a revoked record. It is idempotent but a storage failure is an error, never
reported as successful logout. It does NOT itself revoke the backend session.
A future logout integration must coordinate backend cookie logout and browser
cookie deletion, report unconfirmed backend revocation, and handle an upstream
replacement received after local revocation. Already dispatched backend requests
cannot be canceled by local revocation. No live logout behavior is activated here.

## Proposed server-only configuration

No values or environment files were created. Never prefix these names NEXT_PUBLIC.

| Name | Meaning |
| --- | --- |
| BFF_SESSION_KEY_VERSION | Current encryption key version |
| BFF_SESSION_KEYS_JSON | JSON object of version to canonical base64 32-byte keys |
| BFF_SESSION_DB_HOST | Must be 127.0.0.1 in this batch |
| BFF_SESSION_DB_PORT | Explicit local disposable PostgreSQL port |
| BFF_SESSION_DB_NAME | Must be scrapmart_bff_local_test |
| BFF_SESSION_DB_USER | Must be scrapmart_bff_runtime |
| BFF_SESSION_DB_PASSWORD | Separately provisioned local-only password |

All instances must share the configured key ring. No signing-secret reuse.
`createLocalSessionStore` validates configuration before constructing a bounded
pg pool (four connections, connect/query/statement timeouts). It uses individual
fields, not connection strings or generic PG environment defaults. It refuses
cloud hosts and arbitrary databases; local forwarding to cloud services is also
prohibited. Imported modules do not construct pools. Close explicitly on shutdown.
Storage errors become generic SessionError without logging raw errors or inputs.

The proposed browser cookie is `__Host-scrapmart_session`, Secure, HttpOnly,
SameSite=Lax, Path=/, no Domain, containing only the opaque identifier. Set expiry
no later than backend absolute session expiry. Future creation callers must obtain
that expiry from a trusted backend contract: access-token expiry alone is not
session expiry. No cookie is actually set. Integration must enforce Origin/CSRF,
no-store responses and server-only credential handling. Do not weaken backend
SameSite settings; the BFF must capture/replay the upstream cookie server-side.

## Reviewed SQL and permission plan (not executed)

`db/bff-sessions/schema.sql` targets a NEW dedicated disposable local PostgreSQL
16+ database, not backend public tables or existing fixtures. A separate owner
must create the database and apply the script only after provisioning approval.
The script checks the database name; that assertion is not proof of host identity.
Verify disposable container identity, port and ownership independently first.
Do not point any fixture at Neon, Render, a tunnel or an existing shared database.

The schema/table owner is the maintenance operator, never the runtime role.
The script creates a NOLOGIN restricted runtime role with explicit column INSERT
and UPDATE, SELECT, CONNECT and schema USAGE only. There is no runtime DELETE,
DDL, ownership, grant option, elevated attribute or membership. PUBLIC database
access/TEMP and public schema CREATE are revoked only inside this dedicated local
database. Enable login and establish authentication separately; no credential is
embedded/generated here. Do not apply these PUBLIC changes to managed/shared Neon.
Use a distinct owner connection for expiry cleanup and future migrations.
Inspect inherited/default privileges and role membership before acceptance.
This remains a trusted BFF role, not isolation against compromise of that role:
it can read encrypted rows and alter session states directly. There is no RLS.

After separate approval: provision a NEW labelled disposable PostgreSQL instance
bound to loopback, verify its identity, create the dedicated database using its
owner, review/apply SQL, establish a local-only restricted login, and inject local
configuration privately. No commands are automated in this batch. Existing
backend test containers/databases must remain untouched. No cloud prerequisite.

## Validation boundaries

Offline tests run via:

```
node --import ./tests/helpers/session-loader.mjs --test --test-isolation=none tests/session-store.test.mjs
```

The test loader replaces only the build-time server-only marker and resolves
TypeScript imports for Node. It is never used by application code. Cryptography
tests run real Node crypto with disposable ephemeral test material. Store tests
run actual orchestration against a single-record boundary double, including
two instances, deferred callbacks and simulated lost acknowledgments/outages.
They do NOT prove PostgreSQL syntax, privileges, locking, durability or isolation.

Required pending real PostgreSQL tests (not executed, not yet implemented as live
fixtures): schema application/constraints; restricted-role positive/negative
grants and ownership; create/read/expiry/revoke round trips; two independent pools
contending for refresh; logout/refresh UPDATE races in both orders; process death
after claim and after upstream response; real disconnects during claim/completion;
restart durability; encryption round trips/key rotation; expiry cleanup by owner;
pool exhaustion/timeouts and outage recovery. Backend HTTP contract integration,
cookie/CSRF browser acceptance and Next client-import rejection also remain pending.

## Executed checks for this batch

- Installed `pg@8.23.1` and development dependency `@types/pg@8.23.1` using npm;
  `npm ls pg @types/pg` confirms both. Manifest and lockfile updated.
- Session command above: 17 passed, zero failed, no PostgreSQL connection.
- Existing auth-passwords, buyer-actions, buyer-orders and materials tests:
  11 passed using `node --test --test-isolation=none` with those four files.
- `npm run lint`: passed. An initial callback name triggered the React Hook rule;
  renaming the internal callback resolved it without suppressing the rule.
- `npx tsc --noEmit --incremental false`: passed after the approved types installed.
- `npm run build -- --webpack`: passed outside the sandbox. The first sandboxed
  attempt failed parsing the TypeScript subprocess's showConfig output.
- `git diff --check`: passed for tracked changes.

`npm audit --json` completed and reported **18 vulnerable packages: 16 moderate,
one high, one critical**. No audit fixes/upgrades were applied. Neither pg nor
@types/pg appears in the vulnerability report.

| Severity | Package/finding |
| --- | --- |
| Critical | next: SVG image optimization RCE and typed-array use-cache RCE; also an App Router Server Actions DoS advisory |
| High | zod: memory exhaustion validating oversized constrained collections |
| Moderate | minimatch globparts amplification and 15 affected ESLint/TypeScript-ESLint dependency ancestors |

These are npm audit's findings, not an assessment that each vulnerable feature is
reachable in this application. Dependency remediation requires a separately
approved change; none is part of the session foundation.

Next approval: provision a new isolated loopback-only disposable PostgreSQL 16+
instance/database, apply the reviewed SQL using a separate owner, establish a
local-only restricted login, privately provide test configuration, and implement/
run the database-dependent tests above. No further package is currently required.
Cloud rollout, real authentication integration and dependency upgrades are separate.
