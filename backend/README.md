# ScrapMart backend

Dependencies are managed with `uv` using `pyproject.toml` and `uv.lock`.
The legacy `requirements.txt` is not the dependency source for this application.

Run the commands below from the `backend/` directory, with project dependencies
already installed in `.venv`.

## Authentication security foundation (Stage 2A)

No registration, login, refresh, or logout endpoints are implemented yet.
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
Stage 1. Stage 2B adds the services described below. Cookies and authentication
HTTP endpoints are not implemented.

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
