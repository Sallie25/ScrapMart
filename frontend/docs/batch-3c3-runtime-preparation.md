# Batch 3C.3 — authentication runtime preparation

Branch: `feature/frontend-buyer-vendor-integration`. Starting and retained HEAD:
`2f83bc99579aad2fcddc4691038c5327705ccf69`.
The initial 3C.3 tracked tree was clean. On resumption, the existing partial
implementation and tests were reviewed and retained, then the remaining
configuration regressions and this documentation were completed. The untracked
backend PRD was preserved. No dependencies, UI, backend, SQL schema, session
rotation protocol or PostgreSQL regression tests were changed.

## Implementation and activation boundary

`src/lib/server/sessions/connection-settings.ts` validates both the original
loopback settings and a separate TLS settings shape. `database.ts` derives pg
pool options from those settings; callers cannot supply pools, query adapters,
connection URLs or arbitrary SSL options. TLS settings require the expected
runtime role and environment-specific database name. Local settings retain
127.0.0.1, scrapmart_bff_local_test, scrapmart_bff_runtime and ssl:false; no remote
hostname or production database can use that configuration shape.

Remote connections use rejectUnauthorized:true, TLS 1.2 minimum, explicit SNI
and Node's default hostname verification. The pg driver source was inspected to
confirm it preserves these options and fails if the server refuses TLS. Default
Node trust applies when no CA bundle is provided. A supplied CA bundle is bounded
to 64 KiB, permits only PEM CERTIFICATE blocks, and each certificate must parse
as an X.509 CA and be currently valid. Private keys, malformed/expired/future CAs
and empty bundles are rejected. An explicit bundle replaces default CA trust,
so it must contain the approved trust chain. No TLS handshake was performed.

The pool remains private and bounded: maximum 4 connections per pool, 2-second
connection timeout, 10-second idle timeout, 5-second statement timeout and
6-second query timeout. Remote startup options force synchronous_commit=on and
search_path=pg_catalog,bff_sessions,pg_temp. Local options are preserved. Existing
owned transactions, acknowledged COMMIT requirements, uncertain-outcome handling,
identifier rotation and family revocation are unchanged.

`src/lib/server/auth/configuration.ts` exports
`AuthenticationRuntimeConfiguration`. Construct it explicitly at a future
server bootstrap with a server environment map. Construction synchronously
validates the complete enabled configuration without a pool, DNS, HTTP, SQL or
connection. Invalid configuration throws only a generic
RuntimeConfigurationError with no cause or submitted values. Secrets are held in
private fields and the configuration serializes as `{}`. No file reads, dotenv
loading or process-environment mutation occur in production code.

Only an absent gate or exact `false` means disabled; disabled configuration does
not read secrets. Exact `true` requires every enabled setting below. Other gate
values are errors. A validated enabled instance still requires an explicitly
injected HttpTransport through createRuntime(transport). There is no fetch
fallback. The returned runtime owns its SessionStore and exposes handle/close;
construction and closing an unused pool perform no connections. Future bootstrap
must reuse one runtime per process and own shutdown rather than create one per
request. Configuration is a snapshot; changes require recreation/restart.

**The current browser route remains hard-disabled.** `runtime.ts` still exports
createBffHandlers() without dependencies. It does not import or instantiate the
new configuration class. Setting BFF_AUTH_ENABLED or any other environment
variable cannot activate browser authentication. The prepared factory can only
be exercised through an explicit server-side caller; tests use synthetic
transports and the pg boundary double. Wiring the route and switching demo forms
remain separate, explicitly authorized work. These APIs do not grant Vendor
approval or bypass backend authorization.

## Required server environment settings

No secret values are recorded here. None of these variables should use a
NEXT_PUBLIC_ prefix or enter client code, logs or a committed environment file.
This contract applies to the prepared runtime factory, not the unwired route.

| Name | Required contract when enabled |
| --- | --- |
| BFF_AUTH_ENABLED | Exact `true` to validate enabled configuration; absent or exact `false` disables the factory. No implicit truthiness. |
| BFF_AUTH_ENVIRONMENT | Exact `staging` or `production`. |
| BFF_SESSION_DB_HOST | Canonical lowercase multi-label DNS hostname, at most 253 characters, valid 1–63 character labels. No IP literals, socket paths, URLs, short names, trailing dot or local/internal/home/invalid suffixes. Ownership and DNS resolution require separate verification. |
| BFF_SESSION_DB_PORT | Canonical decimal integer 1024–65535, no padding, exponent, sign or whitespace. |
| BFF_SESSION_DB_NAME | Exactly `scrapmart_bff_staging` or `scrapmart_bff_production`, matching BFF_AUTH_ENVIRONMENT. These are newly defined runtime database identities; no such database was created or inspected. |
| BFF_SESSION_DB_USER | Exactly `scrapmart_bff_runtime`. Use only the restricted role, never an owner/admin credential. |
| BFF_SESSION_DB_PASSWORD | Required nonempty string of 24–1024 characters, without ASCII whitespace/control characters or boundary whitespace. Provision a random password through the approved secret store; validation alone cannot establish password entropy. |
| BFF_SESSION_DB_CA_PEM | Optional approved public CA bundle; omitted uses Node's default trust. Empty, malformed, non-CA, expired/future certificates or extra non-certificate material fail. There is no insecure SSL mode switch. |
| BFF_SESSION_KEY_VERSION | Current version, 1–32 characters from A–Z, a–z, 0–9, underscore or hyphen, present in the key ring. |
| BFF_SESSION_KEYS_JSON | JSON object of 1–8 version-to-key mappings, at most 8192 characters. Each key is canonical padded standard base64 encoding of exactly 32 bytes with at least 16 distinct byte values. Duplicate key values across versions fail. Generate independent cryptographically random keys; retain old versions for existing sessions. |
| BFF_BACKEND_ORIGIN | Exact canonical HTTPS origin with a valid DNS hostname, HTTPS port 443, no explicit port/path/trailing slash/query/fragment/userinfo. The backend client appends /api/v1/auth; do not include that prefix. |
| BFF_BROWSER_ORIGIN | Same origin format, distinct from the backend origin. Must match the public frontend host and FastAPI's explicit Origin allowlist. |

DATABASE_URL and PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD/PGSSLMODE/PGOPTIONS are
not configuration fallbacks for the identity, TLS and transaction options set by
this adapter. Offline tests check the effective installed pg option parser under
hostile defaults. NODE_TLS_REJECT_UNAUTHORIZED=0 is rejected both during enabled
configuration validation and again before constructing a TLS pool. Do not use
process-level TLS weakening or unreviewed trust-store overrides. No production
configuration permits rejectUnauthorized:false or ssl:false.

All instances must share the encryption key ring. AES-256-GCM, fresh nonces,
authenticated row/version binding and hashed browser identifiers remain supplied
by the existing CredentialVault/SessionStore. The byte-diversity check detects
obvious weak keys; it is not proof that keys were randomly generated. Do not reuse
backend signing/rate-limit secrets. Key removal requires a session expiry or
revocation plan.

## Remaining prerequisites for controlled staging

1. Review and authorize an actual staging DNS target and deployment origin. DNS
   syntax validation cannot prove host ownership or prevent an operator from
   choosing a hostname that resolves to an unintended address. Configure approved
   egress/network policy and validate certificates and hostname mismatch failure
   during controlled acceptance. Real PostgreSQL/TLS and multi-instance behavior
   are not certified by these offline tests.
2. Review a target-specific PostgreSQL 16+ migration. The existing schema.sql is
   guarded for a fresh local database and must not be applied unchanged to staging.
   Provision and verify the runtime role separately: no superuser, database/role
   creation, replication, bypass-RLS, inherited memberships or object ownership;
   grant only CONNECT, schema USAGE, table SELECT, the documented INSERT columns
   and UPDATE columns. Deny root_hash/identifier/expiry UPDATE, DELETE, TRUNCATE,
   DDL and grant options. A role name in configuration cannot prove actual grants.
   Whole-family expiry cleanup remains an owner responsibility.
3. Supply secret-managed database credentials and encryption keys, approved CA
   material if needed, and instance/pool budgets. Independently establish backend
   database/email-registry/JWT/Redis readiness. FastAPI AUTH_ALLOWED_ORIGINS must
   include the exact frontend origin; POSTs require X-ScrapMart-CSRF: 1. Agree on
   trusted proxy identity and BFF egress rate limiting without forwarding arbitrary
   browser headers or weakening limits. See 3C.2 for exact backend settings.
4. Explicitly authorize and implement server bootstrap and route wiring. Validate
   once before serving enabled requests; treat startup errors as fail-closed,
   generic failures. Do not add a silent local configuration fallback. Connect the
   operational gate to a process lifecycle that closes/replaces the old runtime.
   Keep the demo forms until an explicit UI switch is authorized.
5. Run separately authorized PostgreSQL/TLS and HTTPS browser acceptance: trusted
   and untrusted certificate/hostname cases, actual role permissions, opaque
   Secure/HttpOnly/host-only cookies, cross-site and Origin/CSRF denial, no token
   exposure, Buyer/Vendor isolation and approval checks, refresh rotation/replay/
   concurrent claims, outage and lost-response fencing, restart persistence and
   logout races. Confirm all authentication responses remain no-store.

For future rollback, stop new dispatch through the wired gate, drain in-flight
work, close runtimes and restore the disabled route/demo revision. Revalidate
503 authentication_disabled without any pool or transport construction. Preserve
schema, encrypted sessions and retained key versions until separately authorized
revocation/expiry handling is complete. Disabling routes or clearing browser
cookies does not confirm backend revocation. No activation or rollback was
performed here.

## Validation

The resumed configuration suite passes 16/16 tests. Coverage includes missing,
malformed and insecure settings; secret-free disabled startup; TLS/identity
options; CA parsing/validity; ambient TLS/pg overrides; key-ring boundaries;
unchanged loopback settings; synthetic transport assembly; configuration snapshot
behavior; and the unwired browser route under a complete enabled environment.

Commands and final results are recorded below after all checks finish. No real
PostgreSQL/Redis/backend connections, SQL execution, provider access, account
creation, commits, pushes or deployment were performed. The PostgreSQL opt-in
runner remains unexecuted. No new package dependency was introduced.

Final executed checks:

| Command/check | Result |
| --- | --- |
| npm run lint | Passed, exit 0 |
| npx tsc --noEmit --incremental false | Passed, exit 0 |
| npm run build -- --webpack | Passed, exit 0; 15/15 static pages generated |
| node --import ./tests/helpers/session-loader.mjs --test --test-isolation=none tests/auth-runtime-configuration.test.mjs | 16 passed, zero failed |
| node --import ./tests/helpers/session-loader.mjs --test --test-isolation=none tests/*.test.mjs | 95 passed, zero failed, one PostgreSQL opt-in test skipped (96 total) |
| git diff --check | Passed |
| Protected file diff | No changes to dependencies, app/components, SQL schema, session store protocol, PostgreSQL tests or isolated runner |

Build used the approved local execution outside the sandbox, as in 3C.1/3C.2,
for Next.js subprocess compatibility. The offline Node suite emits the existing
MODULE_TYPELESS_PACKAGE_JSON warning; no module-mode change was made. Mock SQL
handlers in regression tests are in-memory doubles, not database execution.

Complete final Git status, using repository-root-relative paths:

```text
 M frontend/src/lib/server/auth/runtime.ts
 M frontend/src/lib/server/sessions/database.ts
 M frontend/tests/helpers/session-pg-double.mjs
?? backend/docs/ScrapMart_Backend_PRD_MVP_Aligned_v2.docx
?? frontend/docs/batch-3c3-runtime-preparation.md
?? frontend/src/lib/server/auth/configuration.ts
?? frontend/src/lib/server/sessions/connection-settings.ts
?? frontend/tests/auth-runtime-configuration.test.mjs
```

HEAD remains 2f83bc99579aad2fcddc4691038c5327705ccf69; no staged changes.
Ready for review and explicitly authorized controlled staging wiring/acceptance,
subject to the target, migration, role, secret, backend and TLS prerequisites above.
Browser authentication remains disabled.
