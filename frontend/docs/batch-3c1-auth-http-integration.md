# Batch 3C.1 — authentication HTTP integration

Scope: implementation and offline local tests only. Required branch verified:
`feature/frontend-buyer-vendor-integration`; HEAD
`0fb6e37af284bc5995fc71536b2fa0fb30b02346`.
The BFF modules, route and HTTP test file were already present as untracked work
at entry. They were reviewed and retained; this turn corrected Python whitespace
validation (U+205F), expanded regression coverage and documented the contracts.
Existing UI, dependencies, session store, schema and PostgreSQL tests were preserved.

## Verified backend contracts

Read-only source: `/home/sallieakpan/Desktop/scrapmart-backend/backend`.
Paths below include the `/api/v1` mount verified in `app/main.py`.

| Method/path | Request | Success |
| --- | --- | --- |
| POST /api/v1/auth/buyer/signup | JSON email, password, full_name; optional phone_number (string or null) | 202 `{message: "If registration was successful, you can now sign in."}`; no tokens/cookies |
| POST /api/v1/auth/vendor/signup | Buyer fields plus required business_name | Same generic 202; creates pending Vendor only; no automatic Buyer enrollment |
| POST /api/v1/auth/buyer/login | JSON email, password | 200 `{access_token, token_type: "bearer", expires_in}` plus refresh Set-Cookie |
| POST /api/v1/auth/vendor/login | Same login shape | Same token/cookie contract; recognized pending/approved/rejected/suspended states may authenticate |
| POST /api/v1/auth/refresh | Refresh Cookie only; no body or bearer input | Same 200 token shape; rotates refresh cookie without extending absolute expiry |
| POST /api/v1/auth/logout | Refresh Cookie only; no body | Empty 204; clears refresh cookie; missing/invalid/already revoked also 204 |
| GET /api/v1/auth/capabilities | Authorization: Bearer access JWT | 200 `{buyer: boolean, vendor: boolean, vendor_verification_status: null or recognized status}` |
| GET /api/v1/auth/vendor/me | Authorization: Bearer access JWT | 200 `{business_name, verification_status, full_name, email, phone_number, created_at}` |

Input models forbid unknown fields. Registration passwords contain 15–128 Unicode
code points, valid UTF-8, no NUL and cannot consist only of Python whitespace.
Login preserves the existing 1–128 code-point password boundary, permitting short
and whitespace passwords. No password trimming/normalization occurs. full_name
is 1–150 code points; phone_number, when supplied and non-null, is nonblank and at
most 20; business_name is nonblank and 1–200. Text rejects NUL/invalid UTF-8.
New email inputs must be ASCII before boundary ASCII whitespace trimming and
ASCII case canonicalization, with maximum canonical length 255. The versioned
backend email-validator/IDNA/collision registry remains authoritative; the BFF
performs preliminary shape checks, not a replacement identity policy.

All POST operations require exactly one allowlisted Origin and exactly
`X-ScrapMart-CSRF: 1`; registration/login require application/json. Auth middleware
bounds request bodies at 16,384 bytes and applies Cache-Control: no-store.
Safe errors generally use `{detail: {code, message, fields: []}}`. Registration
returns generic 202 for reserved/duplicate identities, without linking accounts.
Validation: 422; Origin/CSRF: 403; oversize: 413; media type: 415; rate limit: 429
with Retry-After; unavailable configuration/registry/storage/limiter: 503;
unexpected failures: safe 500. Invalid login is generic 401 with
WWW-Authenticate: Bearer. Refresh invalid/replayed/expired/revoked credentials
return 401 and clear the cookie; replay revokes the backend session. Backend
refresh 503 retains its cookie, but the BFF conservatively abandons a dispatched
uncertain attempt rather than retrying. Logout 503 means backend revocation is
unconfirmed. Bearer reads return 401 for invalid/live-session failure, 403 for
missing Vendor profile or unrecognized profile state, 503 for service failure.

Backend refresh cookie: `__Secure-scrapmart_refresh`, 43-character canonical
base64url opaque value, Secure, HttpOnly, SameSite=Lax, host-only (no Domain),
Path=/api/v1/auth, Max-Age and absolute Expires. JWT lifetime is configured at
1–15 minutes. Cookie expiry is not extended on rotation.

Source evidence: `app/api/v1/{buyer_signup,buyer_login,vendor_registration,
vendor_login,buyer_sessions,vendor_account}.py`; schemas/services in
`app/modules/auth/{registration_schemas,login_schemas,vendor_schemas,
registration_service,vendor_service,login_service,vendor_login_service,
session_service,vendor_authorization,http_security,security,email_identity_policy}.py`.
Tests inspected include Buyer signup/login/session and Vendor registration/login/
account tests. Backend tests were read, never executed.
Selling still requires live backend approval and approved evidence. Login and
capability/status discovery do not grant selling/review permissions.

## HTTP implementation and security

- `src/lib/server/auth/contracts.ts`: strict payloads, bounded strings, safe
  response schemas, recognized verification states and allowlisted error fields.
- `backend.ts`: injected Request/Response transport, fixed HTTPS origin and
  endpoint paths, manual server-side refresh-cookie capture/replay, strict cookie
  validation, bounded JSON and request deadlines, no redirect following/retries.
- `bff.ts`: adapters using the validated SessionStore create/lookup/withAccess/
  refresh/revoke interface. Credentials remain encrypted server-side. Refresh
  retains the existing committed-claim, rotation, family revocation and uncertain
  outcome protocol; no session-store/security/schema changes were made.
- `src/app/api/auth/[...operation]/route.ts`: Node runtime routes. Browser paths:
  POST `/api/auth/{buyer,vendor}/signup`, POST `/api/auth/{buyer,vendor}/login`,
  GET `/api/auth/session`, GET `/api/auth/vendor/status`, POST `/api/auth/refresh`,
  POST `/api/auth/logout`. Other methods/operations fail closed.
- `runtime.ts`: dependencies deliberately unwired; no environment activation
  switch, global fetch fallback, pool construction or secret reads. Recognized
  production requests return 503 authentication_disabled. Demo forms unchanged.

Browser cookie is `__Host-scrapmart_session`, random opaque identifier only,
Secure, HttpOnly, host-only, Path=/, SameSite=Lax, bounded to backend absolute
expiry. Access/refresh tokens never enter browser JSON/JavaScript or browser
backend-cookie headers. All replies are no-store. Mutation handlers require
configured exact HTTPS Origin, matching request URL origin, CSRF header and,
when present, same-origin fetch metadata. Duplicate cookies fail closed.
No browser Authorization, forwarding headers or arbitrary upstream cookies are
passed through. Errors discard upstream text and only project known fields.
Session discovery is read-only; refresh is explicit. Account switching requires
logout. Local logout revokes the family even if backend logout fails, and reports
logout_unconfirmed rather than claiming upstream success. Already dispatched
requests cannot be recalled; expired access currently produces a fail-closed 503
from the store, while upstream 401 maps to session_refresh_required.

Vercel/Render are separate sites: browser requests target only the same-origin
BFF, which captures the backend host-only cookie and explicitly sends it on
server-to-server refresh/logout requests. This avoids dependence on cross-site
browser cookies or SameSite=None. Upstream cookies are never forwarded verbatim.

## Validation and limitations

Offline suite: 79 passed, zero failed, one PostgreSQL opt-in test skipped (80
reported tests). Includes 40 BFF HTTP tests using synthetic accounts and mock
transport, session regression tests with the explicit pg boundary double, and
existing frontend regression tests. No SQL is executed by this test path.
Coverage includes payloads, login success/failure, encrypted session creation,
cookie handoff, refresh rotation/concurrency, lost responses/commit acknowledgments,
CSRF/Origin, logout/revocation races, storage/backend outages, stalled response
bodies, role isolation, capability combinations and forbidden operations.

Command: `node --import ./tests/helpers/session-loader.mjs --test --test-isolation=none tests/*.test.mjs`.
Lint/TypeScript/build outcomes are recorded in the final report below.
No PostgreSQL/Redis/backend service tests, live account creation, staging,
provider access, provisioning, SQL, commits, pushes or deployment were performed.

Next batch must explicitly authorize runtime wiring and demo UI switching,
provide approved server-side storage/key/transport configuration, verify backend
Origin allowlisting and BFF-aware rate limiting (untrusted X-Forwarded-For is
intentionally not forwarded), and test browser HTTPS cookie delivery. Current
HTTP tests do not certify real network or PostgreSQL behavior; prior PostgreSQL
revalidation remains separate evidence. Ready for review and the next controlled
integration batch; live authentication remains disabled.

## Complete Git status

Full porcelain status below uses repository-root-relative paths and expands every
untracked file. The 15 tracked modifications and all pre-existing untracked files
were retained. No staged changes, commits or branch changes were made.

```text
 M frontend/package-lock.json
 M frontend/package.json
 M frontend/src/app/listings/[id]/page.tsx
 M frontend/src/app/login/page.tsx
 M frontend/src/app/marketplace/page.tsx
 M frontend/src/components/buyer/buyer-dashboard.tsx
 M frontend/src/components/buyer/buyer-listing-card.tsx
 M frontend/src/components/buyer/buyer-shell.tsx
 M frontend/src/components/buyer/category-grid.tsx
 M frontend/src/components/buyer/listing-details.tsx
 M frontend/src/components/buyer/marketplace-discovery.tsx
 M frontend/src/components/landing/welcome.tsx
 M frontend/src/components/marketplace/listing-card.tsx
 M frontend/src/components/marketplace/listing-photo.tsx
 M frontend/src/components/vendor/vendor-workspace.tsx
?? backend/docs/ScrapMart_Backend_PRD_MVP_Aligned_v2.docx
?? frontend/db/bff-sessions/schema.sql
?? frontend/docs/batch-2a-media-review.md
?? frontend/docs/batch-2c-nigerian-photographs.md
?? frontend/docs/batch-2d-generated-media.md
?? frontend/docs/batch-3b2-session-foundation.md
?? frontend/docs/batch-3b3-postgresql-validation.md
?? frontend/docs/batch-3b4-session-hardening.md
?? frontend/docs/batch-3b5-postgresql-revalidation.md
?? frontend/docs/batch-3c1-auth-http-integration.md
?? frontend/docs/marketplace-design-correction.md
?? frontend/public/images/generated/SOURCES.json
?? frontend/public/images/generated/aluminium.webp
?? frontend/public/images/generated/bottles.webp
?? frontend/public/images/generated/cardboard.webp
?? frontend/public/images/generated/clothes.webp
?? frontend/public/images/generated/copper.webp
?? frontend/public/images/generated/electronics.webp
?? frontend/public/images/generated/iron.webp
?? frontend/public/images/generated/tyres.webp
?? frontend/public/images/nigerian-scrap/LICENSE.txt
?? frontend/public/images/nigerian-scrap/SOURCES.json
?? frontend/public/images/nigerian-scrap/enugu-yard.webp
?? frontend/public/images/nigerian-scrap/seme-bottles.webp
?? frontend/src/app/api/auth/[...operation]/route.ts
?? frontend/src/components/buyer/buyer-orders.tsx
?? frontend/src/components/buyer/marketplace-navigation.tsx
?? frontend/src/components/marketplace/material-placeholder.tsx
?? frontend/src/components/marketplace/material-visual.tsx
?? frontend/src/lib/marketplace/buyer-actions.ts
?? frontend/src/lib/marketplace/legacy-photos.ts
?? frontend/src/lib/media/materials.ts
?? frontend/src/lib/server/auth/backend.ts
?? frontend/src/lib/server/auth/bff.ts
?? frontend/src/lib/server/auth/contracts.ts
?? frontend/src/lib/server/auth/runtime.ts
?? frontend/src/lib/server/sessions/crypto.ts
?? frontend/src/lib/server/sessions/database.ts
?? frontend/src/lib/server/sessions/index.ts
?? frontend/src/lib/server/sessions/store.ts
?? frontend/tests/bff-auth-http.test.mjs
?? frontend/tests/buyer-actions.test.mjs
?? frontend/tests/buyer-orders.test.mjs
?? frontend/tests/helpers/postgres-fixture.mjs
?? frontend/tests/helpers/postgres-pg-faults.mjs
?? frontend/tests/helpers/postgres-process-worker.mjs
?? frontend/tests/helpers/session-loader.mjs
?? frontend/tests/helpers/session-pg-double.mjs
?? frontend/tests/materials.test.mjs
?? frontend/tests/run-isolated-postgres.py
?? frontend/tests/session-store.postgres-restart.mjs
?? frontend/tests/session-store.postgres.test.mjs
?? frontend/tests/session-store.test.mjs
```

Final checks: `npm run lint` passed; `npx tsc --noEmit --incremental false`
passed; standalone BFF HTTP suite passed 40/40; `git diff --check` passed.
Two sandboxed build attempts failed because Next's TypeScript CLI subprocess
returned empty captured stdout for --showConfig (reproduced directly through
Next's CLI helper). The approved build rerun outside the sandbox compiled,
completed TypeScript and generated all 15 static pages; final exit is recorded
below. No dependency/configuration change was made to work around the sandbox.

`npm run build -- --webpack`: passed, exit 0 on the approved local rerun outside
the sandbox. Auth route is dynamic; runtime authentication remains disabled.
Final working tree: 15 modified tracked files, 53 untracked files, no staged
changes. Branch and HEAD remain as recorded above.
