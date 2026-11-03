# Batch 3C.2 — integration checkpoint and runtime readiness

Initial branch: `feature/frontend-buyer-vendor-integration`. Initial HEAD:
`0fb6e37af284bc5995fc71536b2fa0fb30b02346`.

Initial scope: 15 modified tracked files and 52 untracked frontend files. One
additional untracked backend PRD is outside scope and must remain uncommitted.
All 67 frontend files were fingerprinted before work; no existing content is
changed in this batch. This checkpoint document is the only new file.

## Complete pending frontend inventory

Each file appears once below. Tests and documentation support the corresponding
implementation groups and will be committed with them.

### Dependencies

- `package-lock.json`
- `package.json`

### Buyer/Vendor interface improvements

- `src/app/listings/[id]/page.tsx`
- `src/app/login/page.tsx`
- `src/app/marketplace/page.tsx`
- `src/components/buyer/buyer-dashboard.tsx`
- `src/components/buyer/buyer-listing-card.tsx`
- `src/components/buyer/buyer-orders.tsx`
- `src/components/buyer/buyer-shell.tsx`
- `src/components/buyer/category-grid.tsx`
- `src/components/buyer/listing-details.tsx`
- `src/components/buyer/marketplace-discovery.tsx`
- `src/components/buyer/marketplace-navigation.tsx`
- `src/components/vendor/vendor-workspace.tsx`

### Media and marketplace changes

- `public/images/generated/SOURCES.json`
- `public/images/generated/aluminium.webp`
- `public/images/generated/bottles.webp`
- `public/images/generated/cardboard.webp`
- `public/images/generated/clothes.webp`
- `public/images/generated/copper.webp`
- `public/images/generated/electronics.webp`
- `public/images/generated/iron.webp`
- `public/images/generated/tyres.webp`
- `public/images/nigerian-scrap/LICENSE.txt`
- `public/images/nigerian-scrap/SOURCES.json`
- `public/images/nigerian-scrap/enugu-yard.webp`
- `public/images/nigerian-scrap/seme-bottles.webp`
- `src/components/landing/welcome.tsx`
- `src/components/marketplace/listing-card.tsx`
- `src/components/marketplace/listing-photo.tsx`
- `src/components/marketplace/material-placeholder.tsx`
- `src/components/marketplace/material-visual.tsx`
- `src/lib/marketplace/buyer-actions.ts`
- `src/lib/marketplace/legacy-photos.ts`
- `src/lib/media/materials.ts`

### Session foundation and PostgreSQL validation

- `db/bff-sessions/schema.sql`
- `src/lib/server/sessions/crypto.ts`
- `src/lib/server/sessions/database.ts`
- `src/lib/server/sessions/index.ts`
- `src/lib/server/sessions/store.ts`

### Authentication BFF HTTP integration

- `src/app/api/auth/[...operation]/route.ts`
- `src/lib/server/auth/backend.ts`
- `src/lib/server/auth/bff.ts`
- `src/lib/server/auth/contracts.ts`
- `src/lib/server/auth/runtime.ts`

### Tests and documentation

- `docs/batch-2a-media-review.md`
- `docs/batch-2c-nigerian-photographs.md`
- `docs/batch-2d-generated-media.md`
- `docs/batch-3b2-session-foundation.md`
- `docs/batch-3b3-postgresql-validation.md`
- `docs/batch-3b4-session-hardening.md`
- `docs/batch-3b5-postgresql-revalidation.md`
- `docs/batch-3c1-auth-http-integration.md`
- `docs/marketplace-design-correction.md`
- `tests/bff-auth-http.test.mjs`
- `tests/buyer-actions.test.mjs`
- `tests/buyer-orders.test.mjs`
- `tests/helpers/postgres-fixture.mjs`
- `tests/helpers/postgres-pg-faults.mjs`
- `tests/helpers/postgres-process-worker.mjs`
- `tests/helpers/session-loader.mjs`
- `tests/helpers/session-pg-double.mjs`
- `tests/materials.test.mjs`
- `tests/run-isolated-postgres.py`
- `tests/session-store.postgres-restart.mjs`
- `tests/session-store.postgres.test.mjs`
- `tests/session-store.test.mjs`

## Dependency and sensitive-file verification

`npm ls --depth=0` passed. Manifest and lockfile root dependency maps match;
resolved lockfile URLs use https://registry.npmjs.org/ and contain integrity
metadata. Changes include Next/ESLint 16.3.8 to 16.4.4, Zod pinned to 4.6.7,
pg ^8.23.1 and @types/pg ^8.23.1. Installed TypeScript is 5.9.3. No install,
registry query or vulnerability service was used; this is dependency consistency
verification, not a current vulnerability audit.

All pending frontend paths and contents were checked for environment files,
private-key headers, provider token patterns, credential-bearing database/Redis
URLs, credential assignments and temporary database artifacts. Matches were
reviewed: synthetic test passwords, fake JWTs and intentionally rejected test
inputs only. Encryption keys/identifiers are generated in memory for tests;
there are no real private keys, database credentials, environment files, database
dumps or data directories in the commit candidates. Binary candidates are ten
WebP media assets with recorded provenance; no database binaries are included.
Existing .gitignore excludes .env*, *.pem, node_modules, .next and .vercel.
No ignored environment or provider configuration was opened. Schema and isolated
fixture sources are review/test code, not database data. The isolated runner is
opt-in and is not invoked by offline tests. Runtime credentials are never logged.
Pattern scanning and review cannot prove the absence of every possible secret.

## Authentication gate verified

`src/lib/server/auth/runtime.ts` constructs `createBffHandlers()` with no
dependencies. Recognized routes return 503 authentication_disabled before store,
secret or transport construction. There is no environment flag that enables
fetch or storage. The route test asserts disabled GET/POST handlers cannot use
fetch. Demo forms remain unchanged. No real authentication is activated here.

## Exact runtime prerequisites

| Requirement | Current implementation and required next work |
| --- | --- |
| PostgreSQL | PostgreSQL 16+ schema with bff_sessions.sessions, immutable root_hash family link, encrypted envelope, statuses/claims, absolute expiry and owner-managed whole-family cleanup. Current schema.sql is a fresh local install script, not an upgrade migration. Review a target-specific migration and rollback separately; do not apply it to an existing/shared database. |
| Connection | Current OwnedSessionDatabase and SessionConnectionSettings permit only 127.0.0.1, port 1024–65535, database scrapmart_bff_local_test, user scrapmart_bff_runtime and nonempty password; ssl is false. Both this guard/type and createLocalSessionStore must be deliberately adapted for an approved remote target with certificate-verified TLS, fixed target validation, bounded pooling and owned transaction connections. Merely supplying a remote URL cannot work. Preserve acknowledged claim/commit ordering and synchronous_commit=on; assess pool budgets across instances. |
| Restricted role | Schema creates scrapmart_bff_runtime NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOREPLICATION, NOBYPASSRLS. An authorized owner must separately enable password-authenticated LOGIN. Runtime gets CONNECT, schema USAGE, table SELECT, INSERT only identifier_hash/root_hash/envelope/expires_at and UPDATE only envelope/status/refresh_attempt/refresh_started_at/revoked_at. No UPDATE of root_hash/identifier_hash/expires_at, DELETE, TRUNCATE, ownership, DDL, role memberships or grant options. search_path is pg_catalog,bff_sessions,pg_temp. Cleanup remains a separate owner task. |
| Encryption | BFF_SESSION_KEY_VERSION selects a key in BFF_SESSION_KEYS_JSON, a server-only JSON map of version to canonical standard-base64 32-byte independently generated random keys. Versions match [A-Za-z0-9_-]{1,32}. All instances share the ring; retain old versions until all corresponding sessions expire or are revoked. AES-256-GCM uses fresh nonces and row/version authenticated data. Do not reuse backend JWT/rate-limit secrets; do not prefix any secret with NEXT_PUBLIC_. |
| Existing local env interface | BFF_SESSION_DB_HOST, BFF_SESSION_DB_PORT, BFF_SESSION_DB_NAME, BFF_SESSION_DB_USER, BFF_SESSION_DB_PASSWORD plus the two key variables above. They describe the local-only constructor today, not production support. No production connection variable or DATABASE_URL fallback exists. |
| Backend URL and frontend origin | BackendAuthClient requires injected origin and browserOrigin as exact HTTPS origins: no path, trailing slash, credentials, query or fragment. It appends /api/v1/auth itself. Supply origin only, not a URL ending in /api/v1/auth. No backend URL env variable is implemented; future wiring must define server-only configuration and inject a bounded transport. Client defaults to 5s timeout (permitted 1–10000ms), 16KiB JSON, no redirects/retries, credentials omit, cache no-store. Never accept upstream URLs from browser input. |
| FastAPI Origin/CSRF | auth_allowed_origins (AUTH_ALLOWED_ORIGINS JSON environment list) must contain the exact approved frontend HTTPS origin. BFF mutations require the same configured Origin and request URL origin, X-ScrapMart-CSRF: 1 and same-origin Sec-Fetch-Site when present. BFF sends its configured frontend Origin and CSRF header upstream. FastAPI requires one exact allowlisted Origin and one CSRF header. No wildcard or Origin reflection. |
| Backend rate limits | REDIS_URL must reach the approved Redis; SIGNUP_RATE_LIMIT_SECRET and LOGIN_RATE_LIMIT_SECRET are separate unpadded canonical base64url 32-byte secrets with at least 16 distinct bytes. Signup: email 5/IP 20 per 3600s; login Buyer/Vendor share email 10/IP 30 per 900s. Missing/malformed configuration or Redis failure returns 503. No backend setting is changed here. |
| Proxy identity | AUTH_TRUSTED_PROXY_CIDRS defaults empty and must describe only verified proxy networks; backend Uvicorn must use --no-proxy-headers. BFF forwards no browser X-Forwarded-For. Backend consequently may share the IP budget across BFF egress: agree and test a trusted client-IP/rate-limiting design before activation. Do not fix this by forwarding untrusted headers or weakening limits. |
| Backend auth readiness | Backend database/session/email registry must already be ready, with approved JWT_SIGNING_SECRET (canonical unpadded base64url, 32 bytes, at least 16 distinct bytes), JWT_ISSUER and JWT_AUDIENCE; ACCESS_TOKEN_EXPIRE_MINUTES must be integer 1–15; AUTH_SESSION_EXPIRE_DAYS a positive integer supported by timedelta (default 7). No backend provisioning, settings lookup or readiness claim is made here. |
| Browser cookie | __Host-scrapmart_session only: opaque identifier, Secure, HttpOnly, SameSite=Lax, Path=/, no Domain; Max-Age/Expires bounded to upstream absolute session expiry. Requires HTTPS and a stable origin; changing preview domains does not transfer sessions. Proxy URL reconstruction must preserve the configured public HTTPS origin for mutation checks. All authentication responses are no-store and have no permissive browser CORS. |
| Upstream cookie | Capture __Secure-scrapmart_refresh server-side: Secure, HttpOnly, SameSite=Lax, Path=/api/v1/auth, no Domain, canonical 43-character base64url token, positive Max-Age and future Expires. Replay only this cookie on backend refresh/logout. Never forward its Set-Cookie or access JWT to browsers. Separate frontend/backend sites therefore do not require cross-site browser refresh cookies. |

Vendor capability/status reads are snapshots. Pending/rejected/suspended login is
not selling permission; backend live approval and approved evidence remain
required. No enrollment, verification submission or logout-all adapter is added.
Expired local access currently fails closed as 503; upstream bearer 401 becomes
session_refresh_required. A future UI must distinguish explicit refresh and
reauthentication without retrying uncertain rotations. Logout upstream failures
are reported as logout_unconfirmed even when the local family is revoked.

## Minimal future activation plan — not performed

1. Obtain explicit authorization for the target and activation scope. Review
   production DB/TLS adapter changes, a versioned migration, restricted-role
   grants, cleanup ownership, shared encryption key lifecycle and a BFF-aware
   abuse/rate-limit design. Revalidate changed storage behavior with separately
   authorized disposable PostgreSQL tests; preserve committed-claim/rotation and
   family revocation semantics. Supply backend readiness evidence separately.
2. Add explicit server-only runtime wiring and a default-off operational gate
   that is checked before constructing dependencies. Never allow test doubles in
   production. Wire secret-managed keys, approved database settings, fixed
   backend/browser HTTPS origins and bounded transport. Add gate tests. Keep
   demo UI until its replacement is explicitly authorized.
3. Run local checks, then separately authorized HTTPS acceptance against an
   approved controlled environment using synthetic accounts. Confirm no tokens
   appear in HTML, browser JSON/storage, URLs, logs or client bundles. Validate
   backend Origin allowlisting, proxy handling and rate-limit budgets.
4. Only after acceptance, explicitly authorize switching forms/session UX and
   enabling authentication. Define monitoring for generic 401/403/429/503,
   refresh uncertainty, logout_unconfirmed and DB pool saturation without
   credential logging. No deployment or provider action is authorized by this
   checkpoint.

### HTTPS acceptance tests required

- Buyer and Vendor signup: correct snake_case fields, unknown/role/approval field
  rejection, generic 202 for duplicate registration, no cookie/session on signup;
  Vendor remains pending. Wrong login returns generic 401, correct login creates
  a local encrypted record and exactly one host-only browser session cookie.
- Inspect actual browser Set-Cookie handling on the public HTTPS host, cookie
  expiry/path/flags and cross-site top-level/subresource behavior. Verify only
  BFF requests occur from the browser; no direct backend refresh-cookie reliance.
- Missing/wrong/duplicate Origin or CSRF and cross-site fetch metadata must be
  rejected before dispatch. Test public URL/proxy reconstruction and denial of
  arbitrary forwarded headers; verify responses and generated errors are no-store.
- Buyer-only, Vendor-only and shared identities return exact live capabilities;
  all four recognized Vendor states remain intact, and unauthorized Vendor reads
  return 403. Approval withdrawal must not be overridden by cached UI state.
- Explicit refresh rotates both upstream cookie and browser identifier once,
  retains absolute expiry and denies replay/concurrent reuse across instances.
  Test dropped response, timeout, lost commit acknowledgment and late cookie
  delivery: no retry, successor recovery or old-identifier reuse.
- Logout clears browser cookie and revokes the local family and backend session;
  old identifiers/tokens fail. Race logout with refresh. Backend/database outages
  must fail closed and report unconfirmed revocation honestly. Include fresh
  instance/restart persistence, retained old-key decryption and key rollover.
- Exercise Redis outage/rate limits, malformed upstream cookies/bodies, backend
  redirects and timeouts. Require bounded failure with no credential leakage.

### Rollback

Keep a reviewed disabled-runtime revision available. On acceptance failure,
first switch the future gate off to stop new dispatch, then revert the future
runtime/UI activation commit while retaining the validated session protocol.
Account for in-flight requests; the current unwired runtime cannot revoke backend
sessions. Use a separately authorized backend/session revocation procedure when
needed, and expire browser cookies with the same host/path/flags through a
reviewed mechanism. Do not report backend revocation as confirmed without evidence.
Retain encrypted data and key versions until expiry/revocation handling is
complete; do not drop schema, reset the database or delete keys to simplify
rollback. Storage migration rollback requires its own reviewed compatibility
plan. Check disabled routes return 503 without fetch/DB construction and demo
flows work. No rollback action is executed in this batch.

## Checks executed in this checkpoint

- npm run lint: passed.
- npx tsc --noEmit --incremental false: passed.
- npm run build -- --webpack: passed, exit 0; all 15 static pages generated.
  Run outside the sandbox using the approved local build workaround established
  in 3C.1. No provider, activation or database operations were involved.
- Offline command: node --import ./tests/helpers/session-loader.mjs --test
  --test-isolation=none tests/*.test.mjs: 79 passed, zero failed, one PostgreSQL
  opt-in test skipped. Includes 40 BFF HTTP tests. Node reports a harmless
  MODULE_TYPELESS_PACKAGE_JSON warning; package module mode was not changed.
- Dependency/lock consistency, candidate secret review and original-content
  fingerprint verification passed. No package downloads or security audit queries.
- Real PostgreSQL/Redis, backend execution, live HTTP accounts, HTTPS browser
  acceptance, provider checks and deployment were not executed. Previous 3B.5
  PostgreSQL evidence is historical and was not rerun in this batch.

## Commit boundaries

1. Dependencies: package.json and package-lock.json only.
2. Buyer/Vendor interface and marketplace/media: pending app/component/helper
   changes, ten media images and provenance/license metadata, associated UI/media
   documentation and buyer-actions/buyer-orders/materials tests.
3. Session foundation: session modules, review-only schema, offline and opt-in
   PostgreSQL tests/helpers, isolated runner and 3B.2–3B.5 reports. No SQL executed.
4. BFF HTTP integration: auth modules, browser API route, HTTP tests and 3C.1 report.
5. This inventory/readiness checkpoint report only.

All paths are explicitly selected; no repository-wide add, reset, clean or stash.
The backend PRD is excluded. Commit identifiers and verified final Git status are
provided in the final response to avoid a self-referential checkpoint commit SHA.
Expected final state is only the unchanged untracked backend PRD. Authentication
remains hard-disabled and production runtime support remains incomplete. Ready
for a separately authorized production-adapter and activation-gate implementation
step, not activation or deployment.

Verified implementation checkpoints:

| Commit | Files |
| --- | --- |
| 8a46023263d2457147560597b3e4fde4c305a115 | 2 dependency files |
| d3807179b5ace15c0cb96f9234da1dd845e9d52e | 40 interface/media/helper/test/documentation files |
| a41e4e80b052c7debf76fc66ddb2d5c783eea299 | 18 session/schema/test/validation documentation files |
| d5b223b647f248fd6b024f55feba81957c9da70e | 7 BFF route/modules/tests/contract documentation files |

The combined implementation range contains exactly the original 67 frontend
candidates, whose file hashes still match the initial inventory. This report adds
one file in a separate documentation commit. No staged changes remain after that
commit. Complete remaining repository status (repository-root-relative):

```text
?? backend/docs/ScrapMart_Backend_PRD_MVP_Aligned_v2.docx
```

The PRD was already untracked at entry and was not opened, modified or staged.
