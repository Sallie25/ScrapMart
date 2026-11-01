# ScrapMart backend

Dependencies are managed with `uv` using `pyproject.toml` and `uv.lock`.
The legacy `requirements.txt` is not the dependency source for this application.

Run the commands below from the `backend/` directory, with project dependencies
already installed in `.venv`.

## Authentication security foundation (Stage 2A)

Buyer registration, login, refresh and logout HTTP endpoints are implemented in
Stages 2C.1–2C.3. Authenticated Buyer profile and logout-all are implemented in
Stage 2C.4. See the HTTP contracts below.
The helpers in `app/modules/auth/security.py` do not access the database.
JWT validation alone does not establish a live session or account permissions.

Configure these variables through local environment configuration or deployment
secret management. Never commit actual secrets or bake them into Docker images.

| Variable | Default | Meaning |
| --- | --- | --- |
| `JWT_SIGNING_SECRET` | None | Unpadded base64url encoding of **32 cryptographically random bytes** |
| `JWT_ISSUER` | `scrapmart-backend` | Exact access-token issuer |
| `JWT_AUDIENCE` | `scrapmart-web` | Exact access-token audience |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access-token lifetime; permitted range 1–15 |
| `AUTH_SESSION_EXPIRE_DAYS` | `7` | Positive absolute authentication-session lifetime in days |

Generate a separate signing secret for each environment with:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store the output directly in your secret manager or private local environment.
Do not use a password, copied example, repeated character, or predictable string.
Validation checks format/length and rejects obvious repetition; it cannot prove
entropy. The secret **must** be randomly generated. Helpers decode the configured
value before using its 32 bytes as the HS256 key; external tooling must do the same.
The signing algorithm is fixed in code and is not selected by token headers.

Signing configuration is checked when creating/verifying tokens. Missing/invalid
signing secrets therefore fail closed for authentication without breaking health
routes or ordinary application import. Security helper errors omit secret values,
and the signing-secret configuration field uses `SecretStr`. A key change
invalidates existing tokens; key-rotation support is not implemented.

Passwords use Argon2id through `pwdlib`, with 64 MiB memory, three iterations,
parallelism one, a random salt, and a 32-byte output. New passwords must contain
15–128 characters, may include Unicode and spaces, and cannot consist entirely of
whitespace or contain null/invalid Unicode characters. They are never stripped,
normalized, or truncated. Existing-password verification does not reapply the
minimum signup length. Benchmark hashing capacity before deployment and combine
future authentication endpoints with rate limiting.

Refresh helpers generate canonical 43-character base64url tokens from 32 random
bytes. Persist only `digest_refresh_token(token)`, a 32-byte SHA-256 digest matching
the `RefreshToken.token_digest` column. Never persist the opaque bearer value or
put it in logs. `AuthSession` and `RefreshToken` persistence models exist from
Stage 1. Stage 2B adds the services described below. Buyer registration is
implemented in Stage 2C.1; login and cookie session endpoints use these services.

Focused offline checks: the 222-test subset below excludes `tests/test_health.py`
and is not the full suite. No external database or services required; database
tests use in-memory SQLite. No settings files are required.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_auth_security.py tests/test_auth_foundation.py tests/test_marketplace_models.py
```

## Authentication session services (Stage 2B)

`app/modules/auth/session_service.py` provides session creation, validation of
already cryptographically verified access claims, refresh rotation, single-session
revocation, and revocation of all unrevoked/unexpired sessions for an identity.
Construct `SessionService(engine)` with a synchronous SQLAlchemy **Engine**.
Sessions, Connections, sessionmakers and other factories are rejected immediately,
without invoking or touching them. The service constructs a new engine-bound
Session for every transaction attempt, including retries. AUTOCOMMIT connections
are rejected before service queries or writes; the driver must support detection.
Future FastAPI endpoints must pass the application Engine, never request-owned
Sessions or Connections. Configure isolation through the Engine when needed.
Each operation owns its transaction,
commits before returning a result, and rolls back on failure. A caller rollback
cannot undo a committed replay revocation. Compose these operations accordingly
when future endpoints are introduced; they are not part of a caller transaction.

Creation accepts an existing, already authenticated User UUID, rechecks activation,
and stores only the refresh digest. It does not create profiles or infer Buyer/
Vendor permissions from `User.role`. Returned credential DTOs hide their plaintext
token in `repr`; the trusted caller must still keep it out of logs and unintended
serialization. Session validation returns only identity/session metadata.

PostgreSQL mutations serialize per identity in User → AuthSession → RefreshToken
order. A value-preserving update to `User.updated_at` obtains the User row lock and
creates a row version without changing field values. This prevents logout-all from
missing a concurrently created session under stale stronger-isolation snapshots.
Serialization/deadlock failures retry the entire operation, in a fresh Session,
up to three total attempts. Database errors are returned as generic persistence
errors without returning a token. Exhausted retries require caller-level handling.

Rotation locks and re-reads the session/token, validates User activation and expiry,
consumes the old token and inserts the replacement atomically. PostgreSQL time is
sampled after locks using `clock_timestamp()`; timestamps are UTC-aware. New refresh
tokens expire at the original absolute session expiry, never a sliding extension.
Keep consumed digests until their session expires so reuse can be detected.

Presenting a consumed token revokes the whole session in a committed transaction,
then raises a generic authentication error. Concurrent refreshes of the same token
therefore produce at most one replacement and ultimately revoke that session,
including its replacement token. Clients must serialize refresh attempts; there
is deliberately no replay grace period. If revocation cannot be committed due to
a database failure, the service reports a persistence error, never a new token.

Run offline session behavior tests with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_auth_sessions.py
```

Real PostgreSQL tests are skipped unless explicitly enabled. They accept only the
disposable `scrapmart-postgres-test` Docker container at `127.0.0.1:55432`, database/
user `scrapmart_test`, PostgreSQL 16, revision `b81d4f2a9c06`, with empty application
tables. Identity/state checks precede writes. Tests use isolated temporary schemas
and remove them afterwards; public application tables and migrations are untouched.

```bash
SCRAPMART_RUN_LOCAL_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_auth_sessions_postgresql.py
```

Offline SQLite tests do not establish concurrency safety. The PostgreSQL tests
exercise rotation replay races and logout-all versus creation under Read Committed,
Repeatable Read, and Serializable isolation, plus expiry after a lock wait.

## Buyer registration API (Stage 2C.1)

`POST /api/v1/auth/buyer/signup` accepts only `application/json`:

```json
{
  "email": "buyer@example.test",
  "password": "a sufficiently long passphrase",
  "full_name": "Example Buyer",
  "phone_number": null
}
```

Email, password and full name are required. Unknown fields are rejected. Names
must be nonblank and at most 150 characters; optional phone numbers must be
nonblank when supplied and at most 20 characters. Passwords use the existing
15–128 character policy and are never trimmed or normalized. International
characters remain supported in passwords and full names.

New email addresses must be **ASCII-only across the complete input**, including
both local part and domain. Non-ASCII input is rejected before trimming or
lowercasing, so Unicode characters that lowercase to ASCII cannot bypass the
policy. Accepted input is trimmed and lowercased, limited to 255 characters, then
syntax-validated with `email-validator` without DNS/delivery checks. The same
ASCII address is used for storage and rate-limit keys. Unicode domain spellings
are rejected; valid ASCII IDNA/punycode domains are allowed. No email records are
rewritten, merged or deleted.
No government ID, email verification, notifications or recovery flow is added.

For both new and already registered valid emails, the response is **202 Accepted**:

```json
{"message":"If registration was successful, you can now sign in."}
```

Both paths return the same status, body and relevant headers, including
`Cache-Control: no-store`, without IDs, cookies, hashes or tokens. The frontend
should display this acknowledgment and offer a login link. No authentication
sessions, refresh tokens or Vendor profiles are
created by registration. An existing identity is never modified or linked, and
an existing Vendor is never silently granted a Buyer profile.

`BuyerRegistrationService(engine)` accepts only a synchronous Engine. Every
transaction attempt creates its own engine-bound Session and rejects AUTOCOMMIT.
New reservations, User and BuyerProfile records commit atomically; any insert
failure rolls back all three. Both profile timestamps use the same database time.
Legacy `User.role` is set to `buyer` only for the newly created identity and is not
a substitute for explicit profile authorization. No database schema changes are
required by Phase 3: the existing Phase 1 reservation schema is required. Signup
uses the V1 policy and bounded indexed reservation lookups, not database lowercase
or User-table scans. Previously backfilled Unicode identities remain unchanged.
For example, legacy `K@example.test` reserves `k@example.test`, dotted-I aliases
are blocked, and Unicode domains reserve canonical punycode and compatibility
aliases. Any occupied bundle key prevents creation without linking accounts.

These conservative checks avoid relying on agreement between Python and database
Unicode lowercasing. They do not define a general Unicode account-linking policy.
Existing Unicode identities remain untouched. Reservation-key uniqueness resolves
concurrent insert races. A fresh transaction must verify a durable reservation
conflict before acknowledgment; User-email uniqueness errors fail closed.
Unrelated persistence errors return a safe 503. Serialization/deadlock failures
retry at most three independent attempts; unknown commit outcomes never retry.
Future identity-creation or email-update paths must preserve this policy: the
existing case-sensitive index alone cannot prevent differently cased legacy
writes from a separate, noncompliant writer.

Every policy-valid attempt performs Argon2id hashing before the existence lookup,
including duplicates. This removes an obvious timing shortcut but does not make
execution constant-time: insert/commit work, index/cache state and concurrent
conflicts can still affect timing. The acknowledgment is enumeration-resistant,
not a guarantee that statistical timing inference is impossible.

### Browser and proxy configuration

Set `AUTH_ALLOWED_ORIGINS` to a JSON array of exact frontend origins, for example
`["http://localhost:3000"]` locally and the actual HTTPS frontend domain(s) in
production. Empty configuration denies signup. Wildcards and non-loopback HTTP
origins are rejected. No Vercel preview/domain wildcard is trusted automatically.
POST requires exactly one allowed `Origin` and `X-ScrapMart-CSRF: 1`, including for
nonbrowser clients in this phase. Form submissions are rejected. CORS explicitly
allows GET/POST/OPTIONS and Content-Type/X-ScrapMart-CSRF/Authorization with credentials enabled;
the only exposed custom response header is Retry-After. Signup does not set auth cookies
in this phase; `credentials: include` is not required for signup. Use HTTPS in
production. Browser tests must use a configured local origin during development.

Run Uvicorn with **`--no-proxy-headers`**, as the Docker command now does. This
preserves the socket peer for application-level trust checks. Never independently
configure server middleware to rewrite `scope.client`. By default forwarded
headers are ignored. Only when the actual peer belongs to explicitly configured
`AUTH_TRUSTED_PROXY_CIDRS` is X-Forwarded-For processed, from right to left through
trusted hops. The proxy must append/replace forwarding headers correctly; restrict
backend access appropriately. Do not trust arbitrary client-supplied headers or
all-address CIDRs. The standardized Forwarded header is not used.

All auth responses are non-cacheable. Validation responses contain only safe field
names, never Pydantic input values, unknown submitted field names, credential
payloads or database details. Requests are capped at 16 KiB before JSON parsing.
Status codes are 403 for Origin/CSRF rejection, 415 for unsupported media types,
413 for oversized bodies, 422 for validation, 429 for limits, and 503 for limiter
or known persistence unavailability; unexpected failures return a generic 500. Errors use `detail` containing `code`,
`message` and a list of safe field names in `fields`.

### Shared signup rate limiting

The Python `redis` client is the production boundary; in-memory doubles exist
only in offline tests. A Redis Lua script atomically enforces fixed windows across
workers: **5 attempts per hour per normalized email**, **20 per hour per client IP**.
The first counted attempt starts each 3600-second window; rejected attempts never
extend expiry. IP attempts are counted before parsing/field validation, after the
browser/content-type guard. Validly shaped email addresses count even when other
fields are invalid. Origin/media/size rejections do not consume these counters;
reverse-proxy connection/body/time limits remain necessary for broader abuse.

Configure a separate `SIGNUP_RATE_LIMIT_SECRET` using a randomly generated 32-byte
unpadded base64url value. The key has no default. Both email and IP counter keys
use domain-separated HMAC-SHA256; neither submitted identity values nor passwords
are stored in Redis keys. All workers must share the secret and Redis deployment.
Changing the secret resets effective counters; protect and coordinate rotation.
Counters are independent of database account existence. 429 responses include
Retry-After. Missing configuration, Redis failures and malformed counter state
fail closed with a safe 503 before hashing or database work. Redis calls have
one-second connect/read timeouts and no automatic retries.

`REDIS_URL` is secret-masked configuration, supporting private-network connections,
authentication and `rediss://` TLS via the Redis client. The existing Compose Redis
has no published host port. Do not expose Redis publicly. Production Redis on
Netcup remains a deployment prerequisite, not a completed deployment. Configure
access control, capacity/eviction and availability: Redis restarts, eviction or
counter loss can reset effective limits. Shared limits do not prevent distributed
abuse or intentional exhaustion of someone else's email budget.

### Validation commands

Offline tests use SQLite and a Redis boundary double, with no remote services:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q
```

PostgreSQL registration tests reuse the established fixed-container identity and
public-data preflight, check database names before writes, and use disposable
schemas with explicit cleanup. The Phase 1 migration is applied only inside those
private schemas, followed by local backfill and verified readiness; the public
schema and production databases are never migrated:

```bash
SCRAPMART_RUN_LOCAL_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_buyer_signup_postgresql.py
```

Real Lua counter tests require the existing running `scrapmart-redis` container
with image `redis:7.4-alpine` and no published port. They connect only to its
inspected container IP, use random test-key namespaces and delete only those keys:

```bash
SCRAPMART_RUN_LOCAL_REDIS_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_signup_rate_limit_redis.py
```

### Phase 1 email reservation schema (migration alone does not enable signup)

Alembic revision `c42f7d18a903` follows `b81d4f2a9c06`. It adds
`email_identity_reservations` and `email_identity_policy_state`. This is schema
preparation only: no User records are rewritten, no aliases are backfilled, and
no registration-service queries are replaced. The migration inserts the singleton
policy row in **building**, never ready. Applying it deliberately prevents new
User inserts until a separately approved backfill, completeness verification,
readiness finalization, and service integration have been completed. Do not apply
it to a live signup deployment as an independently usable registration release.
Phase 1 local validation uses disposable schemas; it does not upgrade `public`.

Reservation keys use deterministic lowercase printable ASCII and PostgreSQL `C`
collation, with an immediate unique constraint. The database checks key structure;
the future identity-policy implementation remains responsible for email syntax
and complete version-1 legacy alias generation. Reservations are either `owned`
with a User UUID or permanently `blocked` with no owner. A User can own multiple
aliases. Ownership cannot move to another User, keys and policy versions cannot
change, and blocked rows cannot become owned. Maintenance may conservatively
convert owned rows to blocked; this never authorizes account linking or login.

The User foreign key is `DEFERRABLE INITIALLY DEFERRED`, with `NO ACTION` for
delete and update. A future transaction must allocate UUIDs, insert the owned
reservation first, insert User and BuyerProfile, and commit all three together.
An orphan reservation fails at commit. A VOLATILE, SECURITY INVOKER,
nondeferrable AFTER INSERT constraint trigger requires ready policy version 1
and an exact reservation owned by that User. It sees earlier writes in the same
transaction and uses indexed key lookups, never a User-table scan. A second AFTER
UPDATE trigger rejects actual email changes, including changes introduced by
BEFORE triggers; unchanged legacy Unicode email values and Stage 2B's
value-preserving User updates remain valid.

The complete reservation-first sequence currently exercised by Phase 1 tests is:
insert the reservation (including its unique-index entry), insert the User, then
run the User insert guard. Only inside that guard is the policy row SHARE lock
obtained, followed by the matching reservation SHARE lock. Those locks remain
held until transaction end. The guard's lock order therefore does **not** establish
a policy-before-reservation order for the entire transaction.

For Phase 1, maintenance must **disable and drain all identity writers before
modifying reservation keys or readiness**. Disable every identity-writing entry
point and wait for all in-flight identity-writing transactions to finish; merely
disabling new requests or locking the policy row is insufficient. This includes
User creation/deletion, email changes, and registry writers. For example, an
in-flight registration may hold an uncommitted reservation and wait for a policy
lock held by maintenance, while maintenance waits on the same reservation's
unique-index entry. This inverted lock sequence can deadlock. PostgreSQL detects
the cycle and aborts a participant with SQLSTATE `40P01`; the caller must roll back
the entire transaction so no partial User/reservation changes persist. This
preserves consistency but is not an acceptable substitute for draining writers.
An isolated local regression deliberately exercises this unsafe overlap and
verifies the committed outcome and the aborted transaction's rollback.

Phase 2 registration integration must acquire and validate the appropriate policy
row SHARE lock **before its first reservation write**, retaining it until commit,
unless a tested alternative protocol is explicitly approved. The table-insert
order remains reservation, User, then BuyerProfile. Maintenance must follow the
corresponding policy-before-reservation protocol as well as the writer freeze.
No registration implementation or production readiness is enabled in Phase 1.

Under Repeatable Read/Serializable, a stale
policy row changed since the transaction snapshot causes serialization failure;
never retry only a statement. The future service must retry the entire transaction
in a fresh Session for SQLSTATE `40001`/`40P01` with a bounded retry count. Unique
conflicts remain subject to generic duplicate acknowledgment, after rollback;
other failures fail closed. No retry or public integration is added in Phase 1.
The identity-writer freeze and drain also apply during future backfill/finalization.
Holding the policy lock serializes state transitions; counters and a 32-byte manifest alone are **not** proof of a
complete backfill. No finalizer is included here.

#### Required database privilege boundary

Use distinct maintenance/migration and runtime roles before deploying this schema.
The runtime role must not own the database, schema, tables, or guard functions;
it must have no superuser, CREATEROLE, schema CREATE, replication, BYPASSRLS,
owner-role membership/SET ROLE path, or permission to change
`session_replication_role`. Revoking grants from a table owner does not restrict
that owner. Production role names/provisioning are deployment prerequisites, not
created by this migration. Check inherited/PUBLIC grants and role memberships,
not just direct role attributes. Migration/maintenance credentials must never be
used by the application. The migration revokes PUBLIC access to the new tables
and functions, but cannot audit or undo pre-existing broader role grants.

Required runtime grants, using the deployment's actual schema/role names:

```sql
GRANT USAGE ON SCHEMA public TO scrapmart_runtime;
GRANT SELECT ON public.email_identity_reservations,
                public.email_identity_policy_state TO scrapmart_runtime;
GRANT INSERT (id, lookup_key, user_id, state)
    ON public.email_identity_reservations TO scrapmart_runtime;
-- PostgreSQL SELECT ... FOR SHARE requires UPDATE on at least one column.
-- The singleton CHECK and reservation mutation trigger protect these ID columns.
GRANT UPDATE (id) ON public.email_identity_reservations,
                     public.email_identity_policy_state TO scrapmart_runtime;
```

User/Buyer/session CRUD grants must separately match their existing operations.
For User insertion grant the columns actually written by SQLAlchemy, including
Python-side defaults such as `role`/`is_active`. Grant Stage 2B UPDATE on
`users.updated_at`. Do not grant runtime DELETE/TRUNCATE on Users or the registry,
policy-state INSERT/DELETE/TRUNCATE, reservation state/version/owner UPDATE,
trigger DDL, or table-wide UPDATE on the registry. No runtime grant may permit
readiness activation. Trigger functions have fixed `pg_catalog` search paths and
fully qualified object references; no SECURITY DEFINER escalation is used.
PostgreSQL checks trigger-function EXECUTE at trigger creation, not each firing;
the restricted role does not need an EXECUTE grant on these functions.

Buyer signup may insert new owned and blocked reservations atomically with a new
User and BuyerProfile, using the narrow INSERT column grants above. Runtime may
not modify, delete, reassign, or unblock existing reservations, or change policy
readiness. The narrow UPDATE(id) grants support PostgreSQL FOR SHARE locking only;
the reservation guard and policy singleton CHECK reject actual ID changes.
Backfill, changes to existing reservations, readiness updates, and other maintenance
operations remain restricted to trusted maintenance. Maintenance can bypass/drop
guards as an object owner, so operational access control is essential.
Maintenance must never delete/reuse reservation keys or remove blocked history;
any exceptional destructive repair requires a separately reviewed migration and
writer freeze. Existing User deletion is additionally restricted by deferred
reservation foreign keys and existing profile/session foreign keys. Before live
rollout, audit effective privileges with the actual runtime login and validate
that forbidden DML/DDL and SET ROLE paths fail. Local tests use temporary NOLOGIN
non-owner roles, exercise permitted and forbidden operations, and remove them.

Downgrade removes guards/functions and only the two new tables, retaining Users
and existing profiles/sessions. It discards reservation/checkpoint history and
restores the previous unprotected writer behavior; do it only with writers frozen
and an audited registry export/backup, never as a way to enable public signup.
A subsequent upgrade starts again at building and requires a fresh verified
backfill. Phase 1 neither implements backfill recovery nor enables production.

Focused local validation (performs identity/revision/empty-table preflight):

```bash
SCRAPMART_RUN_LOCAL_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_email_identity_postgresql.py
```


### Buyer signup reservation integration

`POST /api/v1/auth/buyer/signup` uses the committed V1 ASCII-only email policy,
including canonical A-label domains and the complete compatibility-alias bundle.
International names and passwords remain supported. Password hashing happens
before database locks, for both new and duplicate requests. Unsupported policy
libraries/tables fail closed with a safe HTTP 503; invalid email syntax yields
credential-safe HTTP 422 validation errors.

Each attempt owns a fresh engine-bound Session. The service locks the singleton
policy row FOR SHARE and requires ready/version 1 before any reservation access.
It performs a bounded indexed key lookup, inserts reservations in sorted order,
then explicitly flushes User and BuyerProfile in the same transaction. The
reservation-to-User foreign key stays deferred; the immediate User guard remains
unchanged. Any existing owned OR blocked alias rejects the entire registration
without modifying existing data. This conservative rule can reject otherwise
distinct addresses sharing a compatibility alias. No User-table email scans,
account linking, vendor creation, automatic login, sessions, or tokens are added.

New and conflicting valid registrations return the same HTTP 202 body:
`{"message":"If registration was successful, you can now sign in."}`. The frontend
should offer a login link. Equal hashing avoids a large avoidable timing difference;
database inserts, unique-index waits, and network scheduling still differ, so
constant-time enumeration resistance is not claimed. Redis limits remain five
attempts/hour per normalized email and twenty per verified client IP, with keyed
identifier hashes, strict trusted-proxy handling, and fail-closed HTTP 503 behavior.
Origin, CSRF, explicit CORS, JSON checks, safe validation, and no-store are retained.

Confirmed serialization/deadlock aborts retry the complete transaction at most
three times. An immediate reservation-key race rolls back everything, then a fresh
attempt must recheck readiness and confirm a durable overlapping key. Other unique
violations, missing/building registry state, permission failures, lock/statement
timeouts, and unexpected inconsistencies produce safe HTTP 503. Unknown commit
outcomes discard the connection and never trigger an automatic retry. A lost
acknowledgment can mean the registration committed; no success response is emitted
without a successful commit acknowledgment.

Minimum signup runtime grants are the SELECT/USAGE and narrow UPDATE(id) locking
grants above, plus INSERT(id,lookup_key,user_id,state) on reservations. The policy
version uses its database default; runtime must not update policy state or existing
reservation state/version/owner/key. Reservation IDs cannot change because of the guard;
policy IDs cannot change because of the singleton CHECK. UPDATE(id) grants only
support FOR SHARE and do not permit an actual ID change. The runtime also needs:

```sql
GRANT SELECT ON public.users, public.buyer_profiles TO scrapmart_runtime;
GRANT INSERT (id,email,password_hash,full_name,phone_number,role,is_active)
    ON public.users TO scrapmart_runtime;
GRANT INSERT (id,user_id,created_at,signup_completed_at)
    ON public.buyer_profiles TO scrapmart_runtime;
```

These are documentation examples, not executed production grants. Keep the runtime
non-owner and non-administrative, audit inherited grants, and retain the separately
required Stage 2B session privileges. Private PostgreSQL tests install the actual
migration/guards and verify successful signup with only these signup grants,
blocked mutations, real concurrency, and rollback. SQLite tests are boundary tests
and do not prove PostgreSQL trigger/isolation behavior.

Production rollout still requires approved role provisioning, writer freeze/drain,
legacy backfill and verified readiness, and private Redis/proxy/Origin configuration.
The committed maintenance tools remain local-only; this integration does not run
production backfill or activate production readiness. Public-schema migrations and
production grants are not performed by tests or signup.

### Buyer login Phase 1A: unresolved runtime locking prerequisite

The login admission query selects `buyer_profiles.id`, filters on `user_id`, and
uses `FOR SHARE` after locking policy, reservation, and User, before inserting
session/token records. PostgreSQL requires schema USAGE, SELECT on the referenced
columns, and UPDATE on at least one column of BuyerProfile for this row lock.
See the [PostgreSQL 16 privilege documentation](https://www.postgresql.org/docs/16/ddl-priv.html).
The documented signup grants supply SELECT and INSERT on BuyerProfile, but no
UPDATE privilege. The documented locking UPDATE grants cover only policy and
reservation; Stage 2B's `users.updated_at` grant does not cover BuyerProfile.
Repository configuration therefore does not establish a sufficient restricted
runtime privilege contract for login. These examples do not establish live grants.

Deployment requires a separately reviewed BuyerProfile locking permission contract
and validation with the actual non-owner runtime role in an isolated schema.
A column-scoped UPDATE permission is narrower than table-wide UPDATE, but would
also permit actual writes to that column: unlike registry IDs, BuyerProfile IDs
have no immutable-ID guard. Do not assume UPDATE(id) is lock-only or grant it
without reviewing the mutation it allows. No roles or grants were changed by
this review.

`FOR KEY SHARE` can protect existence/key identity against DELETE and key changes,
but still requires UPDATE permission. Other row-lock strengths do too. A plain
SELECT permits concurrent profile deletion; the existing User lock alone does
not block direct BuyerProfile deletion. Advisory locks require cooperation from
every writer and do not replace the current protection. No less privileged row
locking substitute has been established that preserves this concurrency contract;
retain the current lock ordering and bounded transaction retries.

Phase 1A PostgreSQL tests were skipped because the original shared fixture read
public tables and private-schema DDL was not authorized. Buyer login now has a
separate fixture in `tests/buyer_login_postgresql_support.py`. It verifies the
fixed local Docker container/server using `pg_catalog`, qualifies application
tables into an unpredictable private schema, and excludes public from search
paths. Identity and ownership checks use explicit exceptions; optimized Python
is rejected. Cleanup compares recorded object identities and uses ordered
`RESTRICT` drops in one transaction. Unexpected objects/dependencies stop cleanup.
An uncertain creation/cleanup outcome reports the schema name for manual review;
never broaden cleanup or delete unverified resources automatically.

Only after explicit authorization of local private-schema DDL, run this module
alone, without parallel workers or other activity in the disposable environment:

```bash
SCRAPMART_RUN_LOCAL_POSTGRES_TESTS=1 SCRAPMART_RUN_BUYER_LOGIN_POSTGRES_TESTS=1 SCRAPMART_RUN_LOCAL_REDIS_TESTS=0 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_buyer_login_postgresql.py
```

Do not use these opt-ins for an unrestricted suite under a no-public-access
constraint: older PostgreSQL fixtures still read public relations. The Buyer
fixture installs the actual registry guards/constraints but omits the migration's
known ACL revocations on newly created private objects; it executes no GRANT or
REVOKE statements and creates no roles. This owner-backed validation does not
establish restricted-runtime permissions or validate the migration ACL contract.
That deployment prerequisite remains unresolved above.

Concurrency tests cover Read Committed, Repeatable Read, and Serializable,
confirm actual blocker relationships, and exercise deactivation, password
changes, logout-all, and both orderings of profile deletion/reassignment against
admission. Offline tests alone do not establish PostgreSQL correctness.

## Session refresh and logout HTTP (Stage 2C.3)

`POST /api/v1/auth/refresh` and `POST /api/v1/auth/logout` accept credentials only
from the `__Secure-scrapmart_refresh` cookie established by Buyer login. Neither
endpoint accepts tokens from JSON, query parameters, or Authorization headers.
No request body or Content-Type is required. Both require exactly one configured
Origin and `X-ScrapMart-CSRF: 1`, including nonbrowser clients. Authentication
responses, CORS preflights, and errors use `Cache-Control: no-store`. Request
bodies are bounded to 16 KiB. Rejected browser guards do not clear cookies.

Refresh returns 200 with `access_token`, `token_type: "bearer"`, and `expires_in`
(seconds), using the existing JWT signing settings and helpers. It atomically
consumes the old refresh token and stores only the replacement's digest. The new
cookie is Secure, HttpOnly, SameSite=Lax, host-only, Path=/api/v1/auth, and expires
at the original session expiry. Rotation does not extend that expiry. Missing,
malformed, ambiguous duplicate, expired, revoked, unknown, or replayed credentials
receive the same generic 401 and a matching-scope cookie deletion. Replaying a
consumed token commits revocation of the whole session before returning 401;
the replacement token also becomes unusable. Clients must serialize refreshes.

Logout returns an empty 204 and clears the cookie for valid, missing, malformed,
unknown, expired, inactive, and already-revoked credentials. A retained consumed
token may revoke its own session but never authenticate. The minimal service
extension `revoke_refresh_session` identifies the session by token digest and
retains User -> AuthSession -> RefreshToken lock ordering and bounded retries.
It does not rotate, create records, delete history, or revoke other sessions.
Protected requests must continue validating live session state after JWT checks;
logout does not alter the cryptographic validity of an already issued JWT.

Database/persistence failures return a generic 503 and retain the cookie so a
client can retry; unexpected failures return a safe 500. Signing configuration
is checked before refresh consumes a token. Logout needs no signing secret.
These lifecycle endpoints do not consume signup/login Redis budgets or introduce
a new Redis dependency; existing signup/login limits remain unchanged. Browser
clients need HTTPS and credentials-enabled requests under the same-site cookie
policy. Runtime database permissions remain a deployment prerequisite.

Run focused offline validation with external integrations disabled:

```bash
SCRAPMART_RUN_LOCAL_POSTGRES_TESTS=0 SCRAPMART_RUN_BUYER_LOGIN_POSTGRES_TESTS=0 SCRAPMART_RUN_LOCAL_REDIS_TESTS=0 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_buyer_sessions_http.py tests/test_auth_sessions.py tests/test_buyer_login_http.py tests/test_buyer_signup.py
```

The concurrent HTTP test uses separate SQLite connections to verify HTTP outcome
and persisted replay revocation; it does not establish PostgreSQL isolation
correctness. No PostgreSQL or Redis integration run is implied by offline success.

## Authenticated Buyer profile and logout-all (Stage 2C.4)

Both endpoints require exactly one `Authorization: Bearer <access JWT>` header.
The existing verifier checks signature, fixed algorithm, issuer, audience, token
type, canonical identifiers, and expiry. Cookies, request bodies, and query
parameters cannot substitute for bearer authentication or select another user.
Every request checks live User activation, session ownership/revocation/expiry,
and an explicit BuyerProfile. `User.role` is not proof of Buyer eligibility; a
vendor-role identity with a BuyerProfile is allowed, as with Buyer login.

`GET /api/v1/auth/me` returns 200 with exactly `email`, `full_name`, nullable
`phone_number`, and `signup_completed_at` (an ISO 8601 UTC timestamp). The response
contains no user/profile/session identifiers, password hashes, tokens, or other
database fields. A single joined read checks eligibility and session state while
projecting approved account fields; it does not load password hashes or mutate
records. No Origin/CSRF header is required for this read-only bearer request.
Browser CORS remains restricted to configured exact origins and now permits the
Authorization header for both authenticated endpoints.

`POST /api/v1/auth/logout-all` additionally requires the existing Origin and
`X-ScrapMart-CSRF: 1` protections. No request body or Content-Type is required.
Authorization and revocation occur in one transaction: User version update,
current session lock, BuyerProfile SHARE lock, then the existing logout-all bulk
update. Current-session and JWT expiry are rechecked after lock acquisition.
The existing bounded serialization/deadlock retry policy is retained. This
prevents an already-revoked credential from revoking later sessions after a
User lock wait. All unrevoked, unexpired sessions for that Buyer, including the
current session, are revoked; other users and refresh-token history are untouched.
Success is an empty 204 with refresh-cookie deletion using the established scope
and security flags. A repeated request with the revoked access token returns 401.

Both endpoints use `Cache-Control: no-store`. Missing/malformed/duplicate bearer
headers, invalid JWTs, invalid live sessions, and ineligible accounts receive the
same generic 401 with `WWW-Authenticate: Bearer`. Authentication and infrastructure
errors do not clear cookies; persistence/configuration failures return generic
503 responses, and unexpected failures return safe 500 responses. Existing Redis
limits and cookie-only refresh/logout behavior are unchanged. BuyerProfile locking
permissions remain the previously documented deployment prerequisite; this stage
does not provision roles or grants.

Focused offline validation (external integrations disabled):

```bash
SCRAPMART_RUN_LOCAL_POSTGRES_TESTS=0 SCRAPMART_RUN_BUYER_LOGIN_POSTGRES_TESTS=0 SCRAPMART_RUN_LOCAL_REDIS_TESTS=0 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_buyer_account_http.py tests/test_auth_sessions.py tests/test_buyer_signup.py tests/test_buyer_login_http.py tests/test_buyer_sessions_http.py
```

SQLite regression tests include controlled overlap with current-session revocation
at the User lock boundary. They do not establish PostgreSQL isolation correctness;
no live PostgreSQL or Redis integration execution is implied by this validation.

## Vendor registration and enrollment (Stage 2D.3)

`POST /api/v1/auth/vendor/signup` accepts required `email`, `password`,
`full_name`, and `business_name`, plus optional `phone_number`. It uses the
existing Buyer field/password policy, ASCII V1 identity registry, signup IP/email
budgets, Origin/CSRF checks, and 16 KiB request limit. Business names are nonblank
UTF-8 text of at most 200 characters without null characters. Unknown fields,
including role, ownership and verification status, are rejected.

New reservations, User (`role=vendor`) and Vendor (`verification_status=pending`)
commit atomically. No BuyerProfile, session or token is created. Existing or
reserved identities receive the same generic 202 acknowledgment, without account
linking or modification. The shared reservation-first registration transaction
retains its collision handling, readiness checks and ambiguous-commit behavior.

`POST /api/v1/auth/vendor/enroll` accepts `business_name` and `current_password`.
It requires the existing bearer access JWT, exact allowed Origin,
`X-ScrapMart-CSRF: 1`, application/json, and an active User/live session with an
explicit BuyerProfile. Current-password verification uses existing login input
boundaries, including support for older passwords; it holds no row locks.
Admission then locks User, session and BuyerProfile, rechecking activation,
session/JWT expiry, revocation and the verified password hash before inserting a
missing pending Vendor. The User lock serializes concurrent enrollments. An
existing Vendor is left entirely unchanged, including its name and status.
Success is an empty 204, with no cookies or tokens. Authentication/password
failures use the generic invalid-session 401; infrastructure failures are safe
503 responses. Every response uses Cache-Control: no-store.

Enrollment uses the existing login IP budget and a second HMAC-protected,
User-ID-bound budget using the existing email counter capacity. The latter is
independent of a client-supplied email and bounds distributed reauthentication
attempts. Redis failure denies the operation. Neither endpoint grants approved
selling permissions, collects verification documents, changes Buyer behavior, or
introduces a migration.

Offline Vendor concurrency tests use separate SQLite connections and synchronized
workers. They verify uniqueness and rollback behavior, but do not establish
PostgreSQL isolation guarantees. Live PostgreSQL and Redis tests are separate.

## Vendor login and session admission (Stage 2D.4)

`POST /api/v1/auth/vendor/login` accepts the existing strict email/password login
input. It requires an active User and an explicit Vendor record; `User.role` and
BuyerProfile do not grant Vendor eligibility. Pending, approved and rejected
Vendors may authenticate. Suspended Vendors may provisionally authenticate for
restricted status access. Login does not approve verification or grant listing,
order, selling or review permissions. Future Vendor operations must check live
verification status, explicit operation permissions and ownership independently.

The credential lookup uses the ready ASCII V1 registry and requires an owned
reservation matching the stored email. Argon2 verification runs after that read
transaction ends, with existing dummy work for unknown/ineligible identities or
unusable hashes. Admission then rechecks readiness, reservation ownership, stored
email, unchanged verified password hash, activation and Vendor status using the
existing transaction runner. Lock order is policy SHARE, reservation SHARE,
User version update, then Vendor SHARE. Locks remain held through session commit;
new session time is sampled after locks. The runtime database role must support
Vendor SHARE locking with appropriate least-privilege grants before deployment;
this change does not provision database roles or permissions.

The endpoint reuses the Buyer login HTTP parser and guards, including the exact
same Redis IP/email counters. Alternating Buyer/Vendor login endpoints does not
multiply the existing budgets. Origin/CSRF checks, trusted-proxy handling, strict
JSON input, 16 KiB body limit, no-store responses and sanitized errors remain in
force. Invalid credentials receive the same generic 401; required infrastructure
failures fail closed without issuing credentials.

Success returns the existing access-token response and sets the same host-only
Secure/HttpOnly/SameSite=Lax refresh cookie at `/api/v1/auth`. JWTs contain identity
and session claims, without verification permissions. Session tables, expiry,
rotation/replay detection, refresh, logout and user-wide revocation are unchanged.
A dual-profile identity retains Buyer access; Vendor-only identities do not gain
BuyerProfile. The shared browser cookie represents the most recent login, not
separate simultaneous Buyer/Vendor cookie sessions.

Vendor tests use disposable SQLite and Redis doubles. Mutable-state tests commit
changes between password verification and admission and verify rejection or the
current recognized status. These tests do not establish live PostgreSQL lock or
isolation guarantees; live PostgreSQL/Redis validation remains separate.

## Vendor profile, authorization and account selection (Stage 2D.5)

`GET /api/v1/auth/vendor/me` requires the existing bearer JWT, an active User,
a live owned session and an explicit Vendor. It returns exactly `business_name`,
`verification_status`, `full_name`, `email`, nullable `phone_number`, and
`created_at` (the Vendor registration timestamp in UTC). Pending, approved,
rejected and provisionally suspended Vendors may read their profile/status.
Neither legacy User.role nor token claims establish profile or selling eligibility.

`GET /api/v1/auth/capabilities` returns exactly `buyer`, `vendor` (profile-existence
booleans), and nullable `vendor_verification_status`. Both endpoints use live
joined reads, validate JWT expiry again against service time, project safe fields
without loading password hashes, and send Cache-Control: no-store. Invalid
credentials/live sessions receive generic 401; a valid identity without a Vendor
receives generic 403 on Vendor profile access. Infrastructure failures receive
safe 503 responses. No Origin/CSRF header is required for these bearer-only reads.

Account selection is client presentation state: a shared session can access each
existing profile, regardless of which login endpoint issued it. Capabilities are
a snapshot for account selection, not an authorization grant. Reading/selecting
an experience does not create profiles, link emails, modify role/status, issue
credentials, or persist a selected mode. Vendor-only identities still fail the
existing Buyer /me and logout-all eligibility checks. Buyer logout-all retains its
user-wide revocation behavior, including sessions used for Vendor access.

`VendorAuthorizationService.get_vendor_profile` provides authenticated profile
access. `require_approved_vendor` provides live approved-only authorization for
reads and returns internal User/Vendor identity for resource ownership checks.
Pending, rejected and suspended Vendors cannot pass selling authorization.
Verification changes take effect on the next operation with the same JWT.

Future protected mutations must use `run_approved_vendor_operation(claims,
operation)`, not authorize in one transaction and write in another. This helper
uses the shared transaction runner, bounded retries and User row-version update;
locks User, then session, then Vendor FOR SHARE; and samples time after admission
locks before invoking the callback. The callback receives that same database
Session and internal identity. It must check resource ownership/operation rules,
lock resources after the admission locks, and perform all writes on that Session.
It must not commit, roll back, use another transaction, return ORM objects, or
perform external effects because the entire operation may be retried.

Verification writers must update the same Vendor row, conflicting with its SHARE
lock until the operation commits. Writers that also lock User must follow the
User-before-Vendor order. Session revocation already follows the shared User and
session lock order. The runtime role needs the appropriate least-privilege grants
for Vendor SHARE locks; no grants or migrations are introduced here. Read snapshots
do not claim mutation race safety. Offline tests inspect the PostgreSQL lock SQL
and transaction behavior; they do not prove PostgreSQL concurrency semantics.
No listing/order endpoints or verification collection are added in this stage.

## Vendor session lifecycle (Stage 2D.6)

Vendor and dual-profile logins use the existing `POST /api/v1/auth/refresh` and
`POST /api/v1/auth/logout`. No alternate endpoints, cookies or token tables are
needed. Rotation keeps the same session expiry. Reuse of a consumed refresh token
revokes the session, invalidating its access tokens in both account experiences.
Logout revokes only the cookie's session and retains refresh history. Expired or
inactive identities may still use cookie logout, as before. Refresh checks live
User activation and session expiry/revocation; it grants no profile or selling
permission. Verification restrictions are enforced separately by live Vendor
authorization, even after refresh or account selection.

`POST /api/v1/auth/vendor/logout-all` requires the existing bearer access JWT,
allowed Origin and `X-ScrapMart-CSRF: 1`. It needs no body or Content-Type and
accepts pending, approved, rejected and suspended Vendor profiles. In one shared
transaction it locks User (version update), current session, then Vendor SHARE;
rechecks activation, live session and JWT expiry after all locks; and revokes all
unrevoked, unexpired sessions belonging to that User across both experiences.
It clears the shared refresh cookie and returns empty 204 only after commit.
Other users and refresh-token history are unaffected. A revoked caller cannot
repeat the operation to revoke later sessions. Valid sessions without a Vendor
receive 403; invalid authentication receives generic 401. Authentication,
permission and infrastructure failures do not clear the cookie; persistence
failures return safe 503 responses so clients can retry. The endpoint has the
existing 16 KiB request bound and no-store behavior.

Buyer /me and logout-all retain their explicit BuyerProfile checks and user-wide
revocation semantics. Vendor-only identities cannot use those Buyer operations;
Buyer-only identities cannot use Vendor profile/logout-all operations. Dual-profile
identities may use either experience without acquiring verification approval.
Suspension takes effect on the next selling authorization check with the same JWT.

Offline tests exercise Vendor/dual-profile rotation, logout, cross-account
revocation, replay, live status changes, safe failures and post-lock expiry checks.
A concurrent Vendor refresh test uses separate SQLite connections and verifies
one successful rotation, one replay rejection, and committed session revocation.
SQLite results do not establish PostgreSQL isolation guarantees. Live PostgreSQL
and Redis integrations remain separate; no migrations or grants are applied here.

## Vendor shop information and verification foundation (Stage 2D.7A)

`GET /api/v1/auth/vendor/onboarding` returns only `business_name`, nullable
`shop_location`, nullable `shop_address`, and current `verification_status` for
the authenticated Vendor. The `/auth/vendor` convention keeps onboarding inside
the existing bearer authentication, safe-error and no-store boundary. Shop address
and location are private onboarding information, not consent to publish a location.
Existing Vendor /me and capability responses do not include them.

`PATCH /api/v1/auth/vendor/onboarding` accepts a nonempty partial object containing
only business_name (up to 200 characters), shop_location (up to 200), and
shop_address (up to 500). Supplied values must be nonblank strings; null cannot
clear fields. Values are normalized to NFC and collapsed single spaces. Invalid
UTF-8, control/format characters, empty patches and unknown fields are rejected
with sanitized 422 errors. Business name updates reuse the existing Vendor column.
The mutation requires JSON, the existing exact Origin and CSRF header, live bearer
credentials, and the 16 KiB request bound. CORS now permits PATCH for allowed
origins. Every response, including errors, is no-store.

Pending and rejected Vendors may edit drafts; their status is preserved and an
edit does not submit/resubmit verification. Approved and suspended Vendors may
read but receive 403 on every edit, including name-only edits. Approved information
cannot change silently while retaining approval: audited re-review is not yet
implemented. Suspension remains operator-controlled. Mutation lock order is User
version update, current session UPDATE, Vendor UPDATE; session/JWT expiry is
rechecked after all locks. Status checks and changes share the same transaction,
so concurrent approval/suspension updates cannot bypass the edit policy. The
shared retry/rollback and activation/revocation protections are retained.

Migration `d73a5c9012ef` follows `c42f7d18a903` and adds only nullable
`vendors.shop_location` and `vendors.shop_address`. Existing rows remain valid and
existing statuses are unchanged. There are no new tables, duplicate names,
verification booleans or submission timestamps. Apply the migration through a
separately authorized deployment before using code that queries the new columns;
no shared/production migration was run. Downgrade removes shop information.

`VendorOnboardingService.get_verification_readiness` checks shop completeness and
reports the outstanding secure-government-ID-document and verified-phone-ownership
requirements. Neither evidence system exists yet, so can_submit is always false.
`require_verification_submission` authenticates and fails closed; no submission
endpoint, fake evidence, upload, SMS integration or approval path exists here.
Future submission must atomically recheck persisted trusted evidence and record a
submission revision; completion additionally requires authorized reviewer approval.
Government ID type/document collection, phone proof, reviewer permissions/audit and
re-review transitions belong to subsequent stages. Existing approved-only selling
checks remain authoritative; shop completion never grants selling access.

Focused tests cover private projections, profile isolation, edit/status policy,
normalization, injection, locks/expiry, readiness and rollback. Migration validation
uses generated PostgreSQL SQL and a disposable SQLite table with historical rows;
this does not establish live PostgreSQL concurrency or deployment correctness.

## Private identity documents and shared phone OTP (Stage 2D.7B)

`POST /api/v1/auth/vendor/identity-document?identification_type=...` requires a
live Vendor bearer session plus the existing Origin/CSRF headers. Send a raw
`image/jpeg` or `image/png` body, not multipart or a storage URL. Supported API ID
type codes are `national_id`, `passport`, `drivers_license`, and `voter_id`; final
product display labels can map to these codes. No ID number is requested. The
body is limited to 3 MiB before parsing/copying; decoded images are limited to
10 million pixels and 8192 pixels per dimension. Pillow verifies and decodes the
actual content, rejects animated/unsupported/corrupt images, and re-encodes clean
JPEG pixels without EXIF or appended payloads. PDF/SVG/GIF are not supported.

A random 256-bit opaque storage key is generated server-side. Only ID type, private
key, submission time and `submitted` status are persisted on Vendor. Uploading is
not identity approval. Only pending/rejected Vendors may upload or replace a
document, with status preserved. Authorization and state are rechecked after
storage under User -> session -> Vendor locks before metadata commit. External
storage writes are outside transaction retries. Known rollback removes the new
object; ambiguous commit outcomes reconcile the current reference before deletion.
If reconciliation/deletion fails, private orphans can remain for restricted
operator retention cleanup. They are never public and no retrieval route or URL
is created. Obsolete objects are deleted best-effort after replacement commits.

Storage is disabled by default. The opt-in `durable_volume` adapter requires all
of PRIVATE_DOCUMENT_STORAGE_BACKEND=durable_volume,
PRIVATE_DOCUMENT_STORAGE_DURABLE=true, and an absolute PRIVATE_DOCUMENT_STORAGE_ROOT.
The root must already exist, be owned by the process, have owner-only permissions,
and be outside the source tree and /tmp. Objects use 0600 permissions and fsync.
The operator must supply an encrypted durable volume, exclude it from all HTTP,
static/media and proxy routes, and configure backups/retention/reconciliation.
This is not a serverless temporary-filesystem fallback. Serverless deployments
without such a mount need an approved private-object-storage adapter implementing
PrivateDocumentStorage; missing configuration returns safe 503 responses. No
public bucket, document bytes, storage key, or signed URL is returned by the API.

`POST /api/v1/auth/phone/send-code` accepts `{}` and uses the authenticated User's
stored phone number, strictly E.164 (`+` and 8–15 digits). It never accepts a
client-selected target. A missing/invalid current phone receives the same generic
202 acknowledgment without delivery. `POST /api/v1/auth/phone/verify-code` accepts
`{"code":"<six digits>"}` and returns empty 204 only on successful one-time proof;
incorrect/expired/consumed codes return generic 400. Both endpoints require live
bearer authentication, JSON, Origin/CSRF, no-store and the existing 16 KiB bound.
They serve Buyer, Vendor and dual-profile identities using the same User evidence.

Codes use secrets.randbelow, a five-minute TTL, a fresh challenge nonce, and a
separate PHONE_OTP_SECRET (canonical base64url encoding of 32 random bytes). Only
HMAC-SHA256 digests bound to User, nonce, current phone and code are stored. The
secret is never stored in the database. Codes are never returned/logged. Each
challenge allows five guesses; failed guesses commit their counters. Consumption
and sending serialize through the existing User lock. Resends invalidate the old
challenge, require 60 seconds, and allow at most six sends per User/hour even
across phone changes. Existing atomic Redis/HMAC counters additionally limit send
requests to 10/IP/hour and verify requests to 60/IP/hour, failing closed on Redis
or secret configuration failure. Changing the phone invalidates both proof and
challenge via a migration-installed database trigger, including change-away-and-
back. Storing a phone number alone is never proof. Retrying verification cannot
reuse a consumed code. A fresh send requires fresh proof.

There is no SMS provider integration or demo code. get_sms_delivery fails closed
until an approved SmsDelivery adapter is supplied. That adapter must keep code/
phone data out of logs and honor challenge UUID idempotency keys. Delivery happens
after challenge commit, outside retryable transactions. Failure invalidates that
challenge best-effort and never marks a phone verified; unsuccessful/uncertain
pending challenges expire and are not ownership evidence. No paid provider is
selected. Offline tests inject capturing SMS and in-memory private storage only
within their isolated fixtures; there is no production test-mode switch.

Migration `e84b6d0123fa` follows and preserves `d73a5c9012ef`. It adds four nullable
Vendor document metadata columns, an all-or-none document constraint, one shared
phone_verifications row per User, and phone-change invalidation triggers. It
backfills no phone proof, document, challenge or approval. Runtime permissions must
allow the User phone-change trigger to invalidate the phone row; direct table
writes remain trusted backend operations. Metadata.create_all alone does not
install the trigger. Downgrade deletes verification metadata/challenges. No live
migration has been run.

Readiness now requires complete shop fields, a submitted document whose private
object exists, and verified ownership of the current phone. Pending/rejected
accounts with all evidence may pass the readiness check; approved/suspended
accounts cannot submit a new review through it. Readiness is a snapshot, never a
mutation grant. Future reviewer submission must atomically snapshot/recheck the
evidence under the established locks. Authorized review alone may approve a
Vendor. Existing approved-only selling guards and private profile projections
remain unchanged; document upload or phone proof grants no selling permission.

The deployment blockers are durable private storage, an approved SMS adapter,
PHONE_OTP_SECRET/Redis configuration, and separately authorized migrations. Tests
exercise provider failures, rollback, historical rows, triggers, content decoding,
code races, limits, status restrictions, and readiness using isolated SQLite and
offline PostgreSQL SQL. They do not prove live PostgreSQL isolation or provider
availability. pyproject.toml/uv.lock include Pillow for real image decoding; the
historical desktop requirements.txt is not the application's dependency source.

## Restricted verification review and approval (Stage 2D.8)

A Vendor explicitly submits complete evidence using
`POST /api/v1/auth/vendor/verification/submit` with `{}`. The live User/session,
shop fields, private submitted document and current phone proof are checked under
User -> session -> Vendor locks. Submission stores an evidence digest and timestamp,
creates an audit event, and leaves/returns the case to pending. Identical pending
submissions are idempotent. Uploading a document alone is not this review submission.

Restricted reviewer endpoints are:

- `GET /api/v1/auth/verification/cases?status=pending&limit=25&after=<vendor-uuid>`
- `GET /api/v1/auth/verification/cases/{vendor_id}`
- `GET /api/v1/auth/verification/cases/{vendor_id}/document`
- `GET /api/v1/auth/verification/cases/{vendor_id}/history?after=0&limit=100`
- `POST /api/v1/auth/verification/cases/{vendor_id}/approve`
- `POST /api/v1/auth/verification/cases/{vendor_id}/reject`
- `POST /api/v1/auth/verification/cases/{vendor_id}/suspend`
- `POST /api/v1/auth/verification/cases/{vendor_id}/reopen`

Every decision requires `expected_version`, `expected_evidence_revision` (from
case detail), and a nonblank reason of at most 500 characters. Unknown fields,
client reviewer IDs/roles/status flags, and control characters are rejected.
Mutations require JSON, exact Origin/CSRF headers and the existing 16 KiB bound.
All reads require bearer authentication; all responses are no-store. Invalid
credentials receive 401, insufficient permission/self-review 403, unavailable
cases 404, stale evidence/version or invalid transitions 409, sanitized validation
422, and infrastructure failure 503. Lists are bounded with UUID cursors, history
uses case-version cursors, and neither list nor case metadata returns storage keys. Case detail exposes a document_available
flag; unavailable/corrupt evidence cannot be approved. Metadata remains available
for suspension/rejection during storage outages, while document downloads fail 503.
History includes owner submission events with no reviewer ID, and explicit human
decisions with the authenticated reviewer ID and reason.

Reviewer authority comes exclusively from an unrevoked verification_reviewers
row plus a live, active User/session. User.role=admin, BuyerProfile, Vendor, public
signup or request fields grant no reviewer permission. Grants cover all Vendor
cases for this MVP, except the reviewer's own Vendor: own cases are excluded from
lists and denied for detail, document, history and decisions. Case-specific document
access resolves the current private key server-side from the authorized Vendor;
there is no arbitrary-key retrieval, signed/public URL, or public media route.
Documents are bounded, validated JPEG downloads with attachment/nosniff/CSP headers;
storage unavailability fails closed. Storage adapters must implement read as well
as put/exists/delete and keep opaque keys immutable. Evidence reads may be retried;
no external write/delivery occurs inside review transaction retries.

There is no default reviewer, reviewer signup, or public permission API. Provision
an existing authenticated identity with the trusted operator utility:
`python -m app.modules.vendors.reviewer_provisioning --user-id <existing-user-uuid> --reference <operator-ticket>`.
Use `--revoke` to revoke the permission. Run it only with a separately authorized
provisioning database role via the normal database configuration; never use public
request inputs or publish its credentials. References must identify an operator/
ticket, not contain identity documents or credentials. All grant/revoke writers
must take the reviewer User version lock through this utility. Runtime must have
SELECT only on verification_reviewers (no INSERT/UPDATE/DELETE), SELECT/INSERT
only on verification_review_audit, and the established User/session/Vendor lock
privileges. The separate provisioning role needs permission-table writes and the
User lock privilege. Database ownership/superuser credentials must not serve HTTP.
No roles, grants, identities, or permissions are provisioned automatically here.
A reviewer can authenticate using their existing Buyer/Vendor profile session;
review permission is separate from those experiences and never enables self-review.

Valid transitions are pending -> approved/rejected, approved -> suspended, and
suspended -> pending (reopen). Only a complete explicit owner submission returns
rejected -> pending. Reopening clears the submission snapshot; owner resubmission
is required before another approval. Approval requires current complete evidence
matching the submitted revision, not just an uploaded file or client status.
Rejection can record a reason against currently viewed incomplete/changed evidence.
No approved information is silently editable through owner onboarding routes.

Decisions lock both reviewer and target User rows in UUID order, then the reviewer
session, then Vendor; permission reads are serialized with trusted provisioning
through the reviewer User lock. Current activation, revocation and JWT expiry are
rechecked after lock waits and private evidence checks. Case versions and current
evidence digests reject stale/conflicting decisions. User phone/evidence writers
use the established User-first locking order. Each status change and its audit
record commit together or roll back together. Audit records contain Vendor, actor,
reviewer where applicable, action, evidence revision, version, previous/new status,
database decision time and reason. Evidence revisions also bind a canonical document
content checksum; database triggers reject audit UPDATE/DELETE.

Selling authorization now requires a real approval audit associated with that
Vendor AND an exact match to current verified evidence, plus current complete
shop fields, phone proof and a private document whose decoded content checksum
still matches the approved object. The approval pointer
is a logical audit reference checked by vendor ID/action/status, avoiding a cyclic
foreign key. Evidence digests bind full name, shop data, immutable private document
key/type/submission time, current phone/proof/time/challenge nonce and User activation. Missing
approval history, phone changes/re-verification, material evidence changes, missing
objects or storage outages fail closed without executing a protected mutation.
Historical approved flags are not backfilled as trusted approval. Operators must
suspend/reopen those cases and obtain explicit submission/review before selling.
Reviewer revocation does not retroactively erase legitimate historical decisions.
Suspension immediately blocks subsequent selling checks while leaving Buyer access
intact unless the shared User is deactivated. Status may remain approved when
proof becomes invalid, but status alone can never authorize selling. Corrupt or
replaced object content also fails the checksum check. Re-encoding/library changes
that change canonical checksums require re-review rather than granting stale access.

Read selling checks are snapshots. Mutation callbacks share the User/session/
Vendor locks and recheck live evidence before executing, including a fresh expiry
check after storage access. Private-object existence is checked per operation;
external operator/storage deletion cannot be transactionally locked by PostgreSQL,
so storage keys must remain immutable and metadata changes coordinated through
the service. No guarantee is made about an already-authorized in-flight operation
after an external object deletion. Subsequent operations fail closed.

Migration f95c7e1234ab follows and preserves e84b6d0123fa and d73a5c9012ef. It adds
reviewer grants, immutable review audit, submission revision/time, case version,
and approval-audit reference. It seeds no permissions or approvals. Apply it and
runtime/provisioning grants only through separately authorized operations. Existing
private storage/SMS/OTP/Redis deployment requirements still apply. No live migration,
provider call or provisioning was performed. Offline concurrency uses separate
SQLite connections and cannot establish live PostgreSQL isolation guarantees.

## Marketplace listings MVP (Stage 3A)

Vendor endpoints under `/api/v1/vendor/listings`:

- POST creates a draft; GET lists own listings (`limit` 1–50, keyset `cursor`,
  optional status). GET/PATCH `/{listing_id}` retrieve/edit an owned listing.
- POST `/{listing_id}/publish` requires `{"public_location_consent":true}`.
- POST `/{listing_id}/pause` and `/sold` accept an empty request or `{}`.
- DELETE `/{listing_id}` safely archives as the existing internal `removed` state.
- POST `/{listing_id}/photos?public_consent=true` accepts raw JPEG/PNG bytes;
  DELETE `/{listing_id}/photos/{image_id}` removes an owned photo.

Every Vendor listing operation requires an active identity/live bearer session and
an explicitly approved Vendor with current matching approval audit and evidence,
not User.role. Mutations use the existing transaction-bound authorization callback,
User -> session -> Vendor -> listing -> category/resource lock order, ownership
checks, rollback/retry protections, and fresh JWT/session time after resource waits.
Origin/CSRF protects mutations. Unknown/mass-assigned fields are rejected; errors
are sanitized and all marketplace responses use no-store. Pending/rejected/
suspended or evidence-invalid Vendors cannot manage listings. Buyer login/profile,
Vendor verification and shared session behavior are preserved.

Inputs reuse the existing model vocabulary: title, category_id, description,
condition (`good_condition`, `used`, `faulty`, `damaged`, `for_parts`), quantity and
unit (`pieces`, `kilograms`, `tonnes`, `bundles`), price_type (`total`, `per_unit`),
is_negotiable, location_summary, lga, area, latitude/longitude, location_visibility,
and directions_allowed. Category must exist and be active. Drafts may be partial
but require a nonblank title. Text is NFC-normalized and bounded; single-line
fields collapse whitespace. Description permits ordinary line breaks. Prices are
NGN decimal strings or integers, nonnegative and below 1e12, at most two decimal
places; JSON floats, exponent strings and silent monetary rounding are rejected.
Quantity is a positive decimal string/integer below 1e11 with at most three places;
pieces must be whole. Responses use exact price/quantity strings. Currency, owner,
status, timestamps, image references and verification fields are not writable.

Publication preserves all existing database requirements: active category,
description, price, quantity/unit, condition, public location summary, paired
coordinates, non-hidden visibility, publication timestamp and at least one stored
photo. Approximate coordinates are rounded to two decimal degrees before storage;
precise coordinates/directions require the explicit public_site visibility and
publication consent. Active location edits require renewed public_location_consent.
The API never copies private onboarding shop/address data into public listing
locations. Vendors must enter only location information they intend to publish.

Lifecycle is draft/inactive -> active (publish), active -> inactive (pause),
active/inactive -> sold, and any nonremoved state -> removed (archive). Sold and
removed records cannot be edited/reactivated. Archiving is idempotent and retains
the listing and images for future references; there is no physical listing DELETE.
Photo changes require draft/inactive status: pause first. Existing deferred image
triggers and constraints remain unchanged. Pause/sold/archive do not depend on
public-photo delivery availability; they still require live Vendor evidence.

Public GET `/api/v1/listings` supports q (literal case-insensitive title/description
search), category_id, location (public summary/LGA/area), condition, min_price,
max_price, verified_only, sort=recent, limit and cursor. GET `/api/v1/listings/{id}`
returns active eligible details only; hidden/ineligible records return generic 404.
GET `/api/v1/categories` lists active categories with bounded UUID pagination
(`after`, `limit` up to 100). Category creation/provisioning is not public.

All public listings must belong to currently active, approved Vendors whose real
audit/evidence still match, regardless of verified_only=false. Public results include
business name, a true verified badge after checks, and a shop_location display
**derived from the listing's consented public location summary**, never private
Vendor.shop_location/shop_address. No owner email/phone, government-ID key/content,
OTP, audit or internal evidence appears. Photo storage keys are not returned.
Missing photos hide a listing; unavailable required infrastructure fails closed.

Public listing pages return at most 20 records, ordered by published_at DESC and
UUID DESC, with a keyset next_cursor. At most 25 SQL candidates (plus one lookahead)
and 25 unique Vendor evidence checks are scanned per request; an underfilled or
empty page may have a continuation cursor when invalid candidates were skipped.
Per-request evidence reuse avoids duplicate checks for one Vendor, without a cache
across requests. Queries have bounded results and public PostgreSQL browse queries
use a five-second statement timeout. These are read snapshots: status changes after
an in-flight read's authorization point may race its response, but subsequent reads
check live state. Mutation authorization remains locked through commit.

There is no configured durable public-photo provider. ListingPhotoStorage is a
separate put/exists/public_url/delete contract whose default factory fails 503.
An approved deployment adapter must provide immutable durable public product-photo
objects and HTTPS URLs in the listings/ namespace, in a separate location/bucket
from government IDs. There is no public local filesystem/static fallback, client
URL/key input or new paid provider. Photos are expressly public upon upload (even
for drafts), requiring public_consent=true. They are capped at 3 MiB, decoded as
JPEG/PNG with the existing bounded Pillow raster validator (10M pixels/8192 per
axis), stripped/re-encoded to JPEG, and assigned opaque server keys. At most five
photos are stored, with server-selected positions. Format/size validation uses
actual bytes, not MIME or filename alone.

External photo writes/deletes occur outside retryable database transactions.
Admission/ownership/status are rechecked after upload before image metadata commits.
Known rollback cleans up the new object; ambiguous outcomes preserve potentially
committed references, and failed reconciliation/deletion can leave unadvertised
public orphans requiring provider-side retention cleanup. Explicit photo consent
covers this public storage behavior. No URL is returned before metadata commit.
Deletion checks for other metadata references before removing a shared legacy
object. Product-photo URLs may remain in public/CDN caches after archival/removal;
no private-document URL is ever produced or placed in product-photo storage.

No tables or migrations are added. Existing Listing, ListingImage, Category and
marketplace migration a7c92e4b610f are reused. Durable public-photo storage and
active category data must be configured before publication; existing private
verification storage/reviewer/SMS/OTP deployment requirements remain. Offline tests
use real evidence review and separate product-photo doubles; they cannot establish
PostgreSQL trigger/isolation or real provider durability guarantees. No live
migration, provider provisioning, order/messaging/payment integration or deployment
has been performed.

## Pay-on-delivery orders MVP (Stage 3B)

No previous Order/OrderItem implementation existed. This stage adds one Order
and one immutable OrderItem per request, reusing User, BuyerProfile, Vendor,
Listing, categories, shared sessions and the existing approved-evidence guards.
There is no cart, payment gateway, messaging integration or payment-received flag.
Delivery is the Vendor's report; completion is the Buyer's receipt confirmation.
Neither event asserts that cash was collected.

Buyer endpoints:

- POST `/api/v1/buyer/orders` accepts only listing_id, quantity, and a client UUID
  request_id. The latter is an idempotency key scoped to the authenticated
  BuyerProfile. Identical retries return the existing order; reusing the key with
  a different listing or quantity receives 409, even after the price changes.
- GET `/api/v1/buyer/orders` and `/{order_id}` return only that Buyer's orders.
- POST `/api/v1/buyer/orders/{order_id}/cancel` permits pending/accepted orders,
  before preparation. POST `/{order_id}/complete` permits delivered orders only.

Vendor endpoints:

- GET `/api/v1/vendor/orders` and `/{order_id}` return only orders for that Vendor.
  Active Vendor identities in all recognized verification states may read their
  historical obligations; reads do not grant selling permissions.
- POST `/api/v1/vendor/orders/{order_id}/accept`, `/reject`, `/prepare`, `/deliver`
  require current approved evidence and ownership. There is no Vendor completion
  endpoint, Buyer receipt override, or payment-status mutation.

All endpoints require an active User/live bearer session and the relevant explicit
profile, never User.role. Buyer ineligibility uses the existing generic 401;
Vendor ineligibility is 403. Cross-owner or missing records receive generic 404,
stock/state/idempotency conflicts 409, invalid quantities/fields 422, and unavailable
infrastructure 503. Mutations require existing Origin/CSRF and bounded JSON inputs;
unknown price, Vendor/Buyer identity, status and payment fields are rejected. Empty
transition requests or {} are accepted. Every response is no-store. Lists use
bounded keyset pagination (limit 1–50, default 20), most recent first.

Lifecycle:

- pending -> accepted -> preparing -> delivered -> completed
- Buyer: pending/accepted -> cancelled, delivered -> completed
- Vendor: pending -> rejected; only the Vendor advances acceptance/preparation/
  delivery, and only the Buyer confirms completion.

Repeated transitions are safely rejected with 409. Self-ordering is rejected.
Read/cancellation/receipt confirmation for existing Buyer orders does not require
current Vendor approval or storage availability. Suspension therefore blocks new
selling transitions but does not remove Buyer access or the ability to cancel an
eligible order/confirm delivered goods. Inactive shared Users still fail their own
authentication. Returns/disputes and cancellations after preparation are not modeled.

Placement checks an active listing, active category, available stored photos,
current approved Vendor evidence, quantity and pricing basis inside one transaction.
It locks Buyer/Vendor User rows in UUID order, the Buyer session/profile, Vendor,
Listing and category, rechecking expiry after waits/evidence I/O. Reservation changes
and Vendor transitions lock Listing before Order. The shared User row-version lock
and bounded serialization/deadlock retries remain in force. No external writes
occur in retried order transactions. Public photo infrastructure is needed for new
placement, not for existing-order history or fulfillment transitions.

Inventory uses the authoritative sum of pending, accepted, preparing, delivered
and completed item quantities under the Listing/owner locks. Only cancellation or
rejection releases a reservation. Completed quantities remain consumed. Listing
quantity remains the total offered stock rather than being decremented to zero,
which would violate its existing positive-quantity constraint. Marketplace output
adds exact available_quantity and public browsing excludes fully committed stock.
Increasing a per-unit listing's total is restocking; decreasing it below reserved/
fulfilled quantities is forbidden. Ordered units/pricing basis cannot change after
any order history exists. A committed total-price lot cannot change quantity;
a fulfilled lot should be archived and restocked through a new listing.

Prices come from the locked listing, not the client. listing_price, price_type,
quantity/unit, title, line total, NGN currency and Vendor display name are immutable
agreement snapshots. Per-unit totals are calculated with Decimal and rounded once
HALF_UP to NGN cents; positive prices cannot produce a zero-cost rounded order.
A total-price listing is an indivisible lot: quantity must equal the full listed
quantity and the listing price is the entire lot price, not multiplied again.
The API returns price/quantity strings. The Buyer receives the locked current price
at creation and may cancel before preparation; a separate quote/negotiation flow
is not introduced. No online payment or cash-receipt status is inferred.

Listing archival retains the referenced Listing and its images. OrderItem FKs
restrict physical listing deletion; history uses snapshots, not current listing
price/title or media. Cancellation/rejection frees inventory without automatically
reactivating a sold/archived listing. BuyerProfile/Vendor references also restrict
history deletion. There are no public order listings or automatic contact/identity-
document disclosures in receipts.

Migration a06d8f2345bc follows f95c7e1234ab and adds orders/order_items, scoped request
uniqueness, ownership/pagination/inventory indexes, valid-state/amount constraints,
and immutable snapshot/state-transition triggers. No existing stock, approval or
prices are changed/backfilled. OrderItem UPDATE/DELETE is blocked, and Order
agreement fields/timestamps cannot be rewritten. Schema migrations must be applied
through separately authorized operations before deploying code that queries these
tables, including the new marketplace availability projection. Downgrade removes
order history and requires an appropriate backup/retention decision; it is not a
runtime API operation. No live migration was performed.

Offline tests use isolated SQLite/storage doubles and real existing verification
workflows. Concurrent placement/request-key tests verify reservation/idempotency
behavior across separate connections; offline PostgreSQL SQL checks do not establish
live PostgreSQL isolation or provider readiness. Existing private/public storage,
SMS/OTP/Redis/reviewer deployment prerequisites remain. No payment, order messages,
front-end, production operation, commit, push or deployment was performed here.

## Buyer–Vendor messaging MVP (Stage 3C)

No existing messaging tables were present. Migration `b17e9a3456cd` follows
`a06d8f2345bc` and adds `conversations` and `messages`. It has not been applied
against a live database. Apply it through separately authorized operations before
running the messaging APIs. Conversation participants are immutable, and listing,
profile and message foreign keys restrict physical deletion, retaining history.

Authenticated HTTP endpoints (under `/api/v1`):

- POST `/conversations`: `{ "listing_id": "UUID" }`; start or retrieve the Buyer's
  conversation with the listing's actual Vendor. Only an explicit Buyer profile
  can initiate. New conversations require an active listing, active owner, and
  current approved Vendor evidence. Self-conversations are rejected.
- GET `/conversations`: participant conversations, including per-conversation
  `unread_count`; GET `/conversations/unread`: total incoming unread count.
- GET `/conversations/{id}/messages`: message history.
- POST `/conversations/{id}/messages`: `{ "content": "text", "request_id": "UUID" }`.
  Optional request_id deduplicates retries per conversation and sender. A retry
  with different content returns 409. Without it, each successful POST is new.
- POST `/conversations/{id}/read`: `{ "message_id": "UUID" }`; marks only that
  incoming message read, idempotently. Reading history alone does not mark read.

Lists use newest-first `(created_at, id)` keyset ordering, default limit 20,
maximum 50 conversations or 100 messages, and an opaque `next_cursor`. Clients
poll and render content as plain text. Text is retained exactly, with 1–4000
Unicode characters, nonblank content, no unpaired surrogates, NUL or control
characters other than tabs and line endings. Unknown input fields are rejected.
No client sender, recipient, Buyer or Vendor IDs are accepted.

Every request checks a live active User/session and explicit participant profiles,
never User.role. Existing participants can read, reply, and acknowledge incoming
messages after listing inactivity, sale or archival, Vendor suspension or evidence
expiry. New initiation remains subject to current authorization. Existing reuse
requires no evidence-storage lookup. Cross-participant requests return generic 404;
invalid fields 422, initiation/idempotency conflicts 409, Vendor ineligibility 403,
authentication failures 401, and unavailable infrastructure 503. Shared Origin/CSRF,
bounded JSON bodies and no-store handling apply. Responses explicitly project only
conversation identifiers, timestamps, counts and message text/sender side; they do
not disclose contact details or verification data.

Shared User/session locks, conversation locks, database uniqueness and transaction
rollback protect creation, retries and read receipts. Tests use SQLite and offline
PostgreSQL DDL; they do not establish live PostgreSQL locking behavior. Operational
requirements are the existing database, authentication and private evidence-storage
configuration for new initiation. No messaging provider, WebSockets, Redis Pub/Sub,
voice calling, push service, frontend or payment integration is required.

## Staging preparation (Stage D2)

See [the staging runbook](deploy/staging/README.md) for the separate migration
image, explicit empty-database registration activation, provider factory contracts,
HTTPS/secrets/role requirements and the offline CI workflow. No provider has been
provisioned and no live migration or deployment has been performed.

## Restricted runtime compatibility (Stage D3)

Migration `c28fa4567def` follows `b17e9a3456cd`, preserving rows while guarding
Buyer-profile/category/listing identifiers and hardening photo-function search
paths. The [runtime role runbook](deploy/staging/runtime-role.md) documents the
staging-only provisioner, explicit column grants, PUBLIC privilege handling and
trusted-backend authorization limits. No Neon or Render changes were performed.
