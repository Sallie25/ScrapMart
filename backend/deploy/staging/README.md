# Staging preparation (not a deployment)

No cloud provider, database, Redis, storage, SMS account or HTTPS ingress is
provisioned by these files. No deployment or live migration has been executed.
Run all examples from backend/. Keep staging isolated from production.

## Images and ingress

The existing Dockerfile now has `api` (default) and `maintenance` targets. Both run
as UID 10001. Build explicitly with `docker build --target api -t scrapmart-api:RELEASE .`
and `docker build --target maintenance -t scrapmart-maintenance:RELEASE .`.
Pin RELEASE to the reviewed Git SHA and retain the previous image for rollback.
Builds install uv.lock with `--locked --no-dev`; tests are not in these images.

`deploy/staging/compose.yml` is a host example, not a provider blueprint. It uses
external PostgreSQL and Redis, a read-only root filesystem, dropped capabilities,
a temporary /tmp, and loopback-only port binding. Set STAGING_API_ENV_FILE to an
absolute path to a private environment file outside the repository. Do not use
production credentials. Do not run Compose up until staging deployment is approved.

Supply HTTPS through a trusted ingress/reverse proxy, including request/body/time
limits. Keep Uvicorn `--no-proxy-headers`; set AUTH_TRUSTED_PROXY_CIDRS only to actual
trusted ingress networks. Set AUTH_ALLOWED_ORIGINS to a JSON array of exact HTTPS
frontend origins. Same-site frontend/API domains are preferred: the host-only
refresh cookie is Secure, HttpOnly, SameSite=Lax, path /api/v1/auth. It is not a
cross-site cookie. Do not relax these defaults to make an insecure deployment work.

Liveness: GET /api/v1/health. Readiness: GET /api/v1/health/ready (database query
only). Readiness does NOT certify migrations, registry activation, Redis, storage,
SMS or secret validity; run explicit acceptance checks for those dependencies.
Database URL must be configured before using readiness. Monitor dependency failures
separately and avoid restarting the API solely to fix a Redis/provider outage.

## Required API configuration

Use a staging secret manager/private env file. DATABASE_URL must use PostgreSQL
with TLS and a non-owner runtime role. REDIS_URL must reach private authenticated
Redis (TLS where required); Redis is for limits, sessions persist in PostgreSQL.
Use independent random 32-byte canonical unpadded base64url values for
JWT_SIGNING_SECRET, SIGNUP_RATE_LIMIT_SECRET, LOGIN_RATE_LIMIT_SECRET and
PHONE_OTP_SECRET. Never print these to deployment logs or commit them. Set
APP_ENVIRONMENT=staging; it labels the environment, it does not provision security.
Keep JWT issuer/audience consistent, access lifetime at most 15 minutes and a
positive session lifetime. All workers share each environment's secrets.

## Controlled migration and empty registration activation

Use a separately authorized non-runtime maintenance role and a direct PostgreSQL
connection. Supply STAGING_MAINTENANCE_DATABASE_URL only to the maintenance process;
it is deliberately not loaded from the API's .env by this command. Do not put the
URL in command arguments. Select staging explicitly and confirm database/role
names against the operator's inventory. Flags are an assertion, not proof that a
mislabelled connection cannot be production: validate the secret's target first.

With that environment securely injected, the maintenance image accepts:

```
migrate --confirm-staging --expected-database STAGING_DB --expected-role MIGRATION_ROLE
bootstrap-empty --confirm-staging --expected-database STAGING_DB --expected-role BOOTSTRAP_ROLE
```

These are arguments to the image entrypoint, not shell commands. With Compose,
use an explicitly authorized `docker compose -f deploy/staging/compose.yml --profile
maintenance run --rm maintenance ...` invocation. Never put this in API startup,
Compose dependencies or automatic production deployment hooks. The image can also
be invoked via `python -B -m app.operations.staging` from a controlled source checkout.

`migrate` runs the eleven-revision chain to c28fa4567def, inside a controlled
connection transaction after checking actual database/user and primary status.
`bootstrap-empty` requires that exact single database revision, the approved email
policy fingerprint, enabled non-security-definer registration guards, validated
registry constraints, no Users/reservations, and exactly one pristine version-1
building policy with zero counters and no checkpoint. It locks the version table,
Users, reservations and policy until commit. It computes the same empty-source
checkpoint as the existing policy, then changes only the policy manifest, status
and update time. It inserts no accounts/reservations and leaves integrity triggers
and runtime signup guarantees intact. The API role must not have activation rights.

Activation is one-shot: repeat invocation rejects a ready policy. Missing guards,
wrong versions, populated/inconsistent state and lock failures reject activation.
There are no automatic retries. If completion is not confirmed, inspect durable
state in a separately authorized session before another invocation; a lost commit
acknowledgement may mean the operation committed. Never force/reset policy status.

### Populated database procedure: deliberately separate and not executable here

Stop on any User/reservation or partial checkpoint. Take a backup, inventory all
identity writers and existing policy state, and prepare a separately reviewed
maintenance plan covering a real writer freeze, complete source classification,
collision blocking, bounded checkpointed backfill, independent verification and
atomic finalization. Establish restricted-role checks and rollback/reconciliation
before approval. Existing IsolatedMaintenanceContext/LocalEmailIdentityFinalizer
are local-test-only and must not be repointed at staging. No populated-database
activation, automatic reset, direct status override or production bootstrap is
provided by Stage D2.

Runtime must not own schema/tables/functions, bypass triggers, modify registry
policy/state, or grant itself reviewer access. Audit inherited/PUBLIC privileges.
Reviewer provisioning uses its existing operator utility with a distinct role;
runtime has SELECT only on verification_reviewers, and SELECT/INSERT only on the
append-only review audit. Review existing README grants, including row-lock and
phone-invalidation trigger privileges, before live restricted-role tests.

Migrations do not backfill verification evidence or seed reviewers/categories.
Create required categories through a separately reviewed seed operation. Downgrades
can delete orders/messages/verification history: application rollback is not a
schema/data rollback. Rehearse backup restore and compatible forward fixes.

## Private storage, public photos and SMS

Private document implementation is unchanged. For durable_volume, provision an
encrypted persistent mount outside /app and /tmp, owned by UID 10001 with 0700 root
permissions. Add an explicit host/provider mount at that private path before
setting PRIVATE_DOCUMENT_STORAGE_BACKEND=durable_volume,
PRIVATE_DOCUMENT_STORAGE_DURABLE=true and PRIVATE_DOCUMENT_STORAGE_ROOT. The Compose
example deliberately mounts no unprovisioned storage. Exclude the mount from every
static/public/proxy route. Configure backups, retention and orphan reconciliation.
Without a suitable mount, a separately reviewed private-object adapter is required.

Public photos: LISTING_PHOTO_STORAGE_FACTORY=package.module:factory selects a
trusted packaged factory accepting Settings. It must return put/exists/public_url/
delete methods. It must store sanitized JPEGs durably and immutably under listings/
keys, return public HTTPS URLs ending in the exact key without credentials/query/
fragment, and support idempotent deletion/reconciliation. It must never use the
private identity namespace. A successful put must mean durable success, not an
asynchronous promise. Existing sanitization/URL validation remains enforced.

SMS: SMS_DELIVERY_FACTORY=package.module:factory selects a trusted packaged factory
accepting Settings and returning send_code(phone, code, *, idempotency_key). It
must honor challenge UUID retry keys, actually deliver through the selected
provider, protect recipient/code data from logs and surface uncertain/failing
send outcomes. It must never log or return OTPs. Existing code commits challenges
before delivery and invalidates failed challenges best-effort; uncertainty grants
no phone proof.

Both are disabled when unset. Invalid imports/interfaces/factory errors fail closed
with existing safe unavailable errors. Factory strings are trusted operator code
configuration, never client input. No provider is bundled and no credentials are
invented. Once a provider is selected: package the adapter, add its dependencies to
the lockfile, define dedicated SecretStr settings for its credentials and validated
endpoint/bucket/sender configuration, document least-privilege grants, then run
sandbox-provider integration and outage/idempotency tests. Do not pass provider
credentials in factory strings or reuse private-document credentials for photos.

## CI and acceptance

The GitHub workflow installs the lockfile on Python 3.13, performs source/import/
startup and eleven-revision head checks without real secrets, and runs offline tests
with all three live integration switches disabled. It has no deployment or cloud
credentials. It does not replace approved disposable PostgreSQL/Redis integration,
real adapter tests, restricted-role checks, or staging browser/cookie acceptance.

No full suite was rerun for D2. Previously: latest full messaging run 1,158 passed,
305 skipped, one SQLite concurrency-fixture failure; the fixture was fixed and
92 focused tests passed. Do not report the full post-fix suite as passing.

## Restricted runtime role (Stage D3)

See [runtime-role.md](runtime-role.md) for additive guards, explicit column ACLs,
PUBLIC privilege handling, limitations and disposable PostgreSQL validation.
