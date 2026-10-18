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
put it in logs. `AuthSession` and `RefreshToken` persistence models already exist
from Stage 1. Session persistence workflows, rotation, reuse handling, cookies,
and HTTP endpoints are not yet implemented and are outside Stage 2A.

Focused offline checks: the 222-test subset below excludes `tests/test_health.py`
and is not the full suite. No external database or services required; database
tests use in-memory SQLite. No settings files are required.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_auth_security.py tests/test_auth_foundation.py tests/test_marketplace_models.py
```
