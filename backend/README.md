# ScrapMart backend

Dependencies are managed with `uv` using `pyproject.toml` and `uv.lock`.
The legacy `requirements.txt` is not the dependency source for this application.

Run the commands below from the `backend/` directory, with project dependencies
already installed in `.venv`.

## Authentication security foundation (Stage 2A)

Buyer registration is implemented in Stage 2C.1 below. Login, refresh and logout
HTTP endpoints are not implemented yet.
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
implemented in Stage 2C.1; cookies and session HTTP endpoints are not implemented.

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
should display this acknowledgment and offer a login link. Login itself is not
implemented. No authentication sessions, refresh tokens or Vendor profiles are
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
allows GET/POST/OPTIONS and Content-Type/X-ScrapMart-CSRF with credentials enabled;
the only exposed custom response header is Retry-After. There are no auth cookies
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
