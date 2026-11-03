# Batch 2C staging Buyer authentication plan

This is a local preparation plan. No provider access, connection to Neon, SQL,
secret injection, deployment, activation or real authentication request has been
made. Authentication remains disabled unless `BFF_AUTH_ENABLED` is explicitly
set to `true` with every validated setting.

## Minimum staging configuration

The frontend BFF must run on an approved HTTPS staging origin. Configure its
server-only environment with `BFF_AUTH_ENABLED`, `BFF_AUTH_ENVIRONMENT`,
`BFF_BACKEND_ORIGIN`, `BFF_BROWSER_ORIGIN`, `BFF_SESSION_DB_HOST`,
`BFF_SESSION_DB_PORT`, `BFF_SESSION_DB_NAME`, `BFF_SESSION_DB_USER`,
`BFF_SESSION_DB_PASSWORD`, `BFF_SESSION_KEY_VERSION`, and
`BFF_SESSION_KEYS_JSON`. `BFF_SESSION_DB_CA_PEM` is optional if the approved
Neon certificate chain is trusted by Node. The required staging identities are
`BFF_AUTH_ENVIRONMENT=staging`, `BFF_BACKEND_ORIGIN=https://scrapmart-api-staging.onrender.com`,
`BFF_SESSION_DB_NAME=scrapmart_bff_staging`, and
`BFF_SESSION_DB_USER=scrapmart_bff_runtime`. Keep `BFF_AUTH_ENABLED=false` or
unset until the later activation approval. Do not use `NEXT_PUBLIC_` for any
secret or put credentials in tracked files.

The backend must allow the exact frontend HTTPS origin in
`AUTH_ALLOWED_ORIGINS` and have its existing database, email identity, JWT and
Redis dependencies ready. The BFF requires a dedicated Neon database for
encrypted session records, separate from the marketplace application database.
Use a restricted runtime credential, never an owner or maintenance credential.
The frontend origin, Vercel project, Neon project and branch, deployment
revisions and backend readiness are not yet verified.

## Target-reviewed database operation, pending separate approval

Do not run `db/bff-sessions/schema.sql` unchanged: it targets a disposable local
database and contains local-only provisioning assumptions. After the exact Neon
project, branch and database are identified, prepare and review a target-specific
fresh-install script or migration. It must create or verify the dedicated
`scrapmart_bff_staging` database, `bff_sessions.sessions` schema/table and a
separate `scrapmart_bff_runtime` LOGIN role. The runtime role must have only
database CONNECT, schema USAGE, table SELECT, INSERT on
`identifier_hash, root_hash, envelope, expires_at`, and UPDATE on
`envelope, status, refresh_attempt, refresh_started_at, revoked_at`. It must
have no ownership, DDL, DELETE, TRUNCATE, grant options or privilege to change
identifiers, family links or expiry. Owner-managed expired-family cleanup needs
its own review. Review existing target objects, backups, rollback and grants
before any SQL; this plan is not permission to execute it.

## Approval sequence and acceptance

1. Separately authorize read-only metadata for each required staging provider.
   Record exact project/service, environment, revisions and frontend origin;
   do not retrieve secret values.
2. Separately authorize the exact Neon project, branch, database, role and
   reviewed SQL/provisioning operation. Verify the restricted grants and TLS.
3. Separately authorize staging-only Vercel and Render variable names and values
   through provider secret stores. Keep the BFF gate disabled.
4. Separately authorize deployment and activation after confirming backend
   readiness and database grants. Use exact revisions and origins, and activate
   only staging. Roll back by disabling BFF dispatch and restoring prior
   staging configuration; preserve keys and session data until expiry or
   separately authorized revocation.
5. Separately authorize synthetic Buyer account tests. Verify signup, BFF login,
   opaque secure cookie, dashboard reload, logout and post-logout denial, plus
   invalid credentials, outage, Origin/CSRF rejection and session expiry.
   Record expected account/session rows and cleanup before tests. No mock or
   offline result counts as staging acceptance.
