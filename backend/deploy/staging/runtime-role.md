# D3 restricted staging API role

This is ordinary trusted-backend least privilege. The shared API credential can
read application rows, write phone evidence and perform reviewer decisions through
the existing services. It is not a database security boundary against full API
compromise, forged direct SQL review records or cross-user direct SQL reads. No
RLS/per-user isolation, new services or SECURITY DEFINER escalation is introduced.
Application-side session, ownership, reviewer and approved-evidence checks remain.

## Required rollout order (separately authorized, never performed on Neon by D3)

1. Verify the Neon **staging primary endpoint**, scrapmart_staging database and
   operator role independently. Stop if the connected target cannot be confirmed.
2. Review backups and the additive c28fa4567def migration. It follows b17e9a3456cd;
   preserve the existing ready registration policy and all rows. Existing API/owner
   credentials still function. No role/owner/database grants are changed by it.
3. Apply the migration through the existing explicit staging maintenance job only
   after approval. The maintenance job's new target is c28fa4567def (eleven revisions).
   Never roll out the restricted credential before the guards exist.
4. Inspect PUBLIC privileges on the staging database/schema and other users before
   choosing whether to authorize --harden-public. See the scope below.
5. Securely inject STAGING_MAINTENANCE_DATABASE_URL into the maintenance process,
   APP_ENVIRONMENT=staging, then invoke its entrypoint with:

   ```
   provision-runtime --confirm-staging --expected-database scrapmart_staging --expected-role OPERATOR_ROLE
   ```

   OPERATOR_ROLE is the independently verified existing maintenance role, not the
   new runtime role. Use --harden-public only with explicit approval to remove the
   staging PUBLIC CREATE/TEMP privileges described below. No password or URL is
   accepted on the command line. The API never receives this maintenance variable.
6. Inspect the results using the restricted role and approved staging acceptance
   tests. The provisioner creates scrapmart_staging_api NOLOGIN, with no password.
   Establish its authentication and enable LOGIN through separately approved secret
   handling; the provisioner deliberately does neither and never resets passwords.
7. Only after approval, update DATABASE_URL on the **staging Render service alone**
   using protected service environment configuration, staging endpoint/database,
   TLS and this login. Do not use shared production environment groups or expose
   credentials in chat, commands, images or source. Activation requires a separate
   authorized deployment. Preserve migration/reviewer-provisioning credentials.

Do not blindly retry an uncertain commit. Inspect durable state first. All role
creation/ACL changes use one transaction, lock migration/policy state and serialize
provisioning. There is no automatic startup operation or automatic drift repair.

## Guard and function changes

The additive migration guards BuyerProfile, Category and Listing IDs against real
changes. UPDATE(id=id) remains valid for SELECT FOR UPDATE/SHARE privileges and the
photo trigger's parent version update. It keeps stale-snapshot protection. Both
photo trigger functions now qualify table references and use SECURITY INVOKER with
search_path=pg_catalog. PUBLIC EXECUTE is removed from the affected/new functions;
existing triggers continue firing without direct runtime EXECUTE grants. Functions
cannot elevate runtime permissions. Guard functions use SQLSTATE 23514 on ID change.

Downgrade removes identifier guards but intentionally retains hardened photo
functions/EXECUTE ACLs. Before downgrade, stop restricted runtime use and revoke its
identifier UPDATE grants through a separately reviewed rollback plan; leaving those
grants without guards would make real identifier updates possible. D3 never rewrites
historical migrations. Model metadata.create_all does not install database guards.

## Exact ACL manifest and prerequisites

app/operations/runtime_role.py is the frozen, explicit column inventory/manifest.
Unknown tables/columns or excess effective privileges reject provisioning. There
are 17 application tables plus alembic_version, and no application sequences.
Table-wide SELECT/INSERT/UPDATE grants are rejected even if all current columns
would be allowed, avoiding automatic permission expansion when columns are added.

- Database CONNECT and public schema USAGE only. No schema/database CREATE, TEMP,
  TRIGGER, REFERENCES, TRUNCATE, ownership, grant options, elevated attributes or
  outward role memberships. No runtime permissions on alembic_version.
- SELECT current columns on application tables, narrowed to id/status/policy_version
  for policy state and id/lookup_key/state/user_id/policy_version for reservations.
- INSERT current ORM columns on users, Buyer profiles, sessions, refresh tokens,
  reservations, phone evidence, Vendors, review audit, listings/images, orders/items,
  conversations/messages. Explicit lists exclude unused server timestamp columns.
  Nullable columns actually emitted by ORM remain included.
- UPDATE users.updated_at only; auth_sessions.revoked_at; refresh_tokens.consumed_at.
- UPDATE(id) on Buyer profiles, categories, policy state, reservations and conversations;
  immutability guards/singleton constraints protect semantic changes. Listings also
  require UPDATE(id) for the actual parent-lock trigger.
- UPDATE phone evidence except user_id; Vendor shop/document/submission/status/review
  fields and updated_at (never Vendor id/user_id/created_at); Listing content,
  status/publication fields/id/updated_at (never vendor_id/currency/created_at).
- UPDATE order lifecycle status/timestamps only; messages.read_at only.
- DELETE listing_images only, for legitimate photo removal. Listing archival is an
  UPDATE; it does not need physical listing deletion.
- verification_reviewers is SELECT-only. Audit is SELECT/INSERT, never UPDATE/DELETE.
  No policy status, count, checkpoint, manifest, version or time mutation is granted.

The role must own no shared objects and have no memberships in other roles. The
only incoming membership accepted is the invoking operator's ADMIN-only grant
(INHERIT FALSE, SET FALSE), which PostgreSQL 16+ automatically creates for a
non-superuser CREATEROLE operator. It does not give the API elevated membership.
Unexpected members, settings, ownership, grant options, custom executable SECURITY
DEFINER functions and session_replication_role permissions cause rejection. Existing
roles must carry the expected D3 marker; unrelated same-name roles are not reused.

If PUBLIC already grants CREATE on public or CREATE/TEMP on scrapmart_staging,
revoking only from this role cannot remove those inherited rights. Without the
flag, provisioning fails and rolls back. Explicit --harden-public removes only
PUBLIC CREATE on public and PUBLIC CREATE/TEMP on scrapmart_staging. It does not
revoke CONNECT, table rights, default privileges, memberships, existing owner
privileges, other named-role privileges, or anything in another database/branch.
Owners retain their rights. Inventory non-owner consumers first and separately
restore any justified named grants before rollout. Other unexpected PUBLIC rights
cause rejection rather than broad revocation. Roles can retain ordinary PUBLIC
CONNECT to other databases on the same staging branch; this procedure does not
claim to change cluster-wide access policy or production branch credentials.

## Disposable validation

D3 uses a **new** labelled local Docker PostgreSQL 16 container, not Neon and not
historical test fixtures. tests/test_runtime_role_postgresql.py checks its label,
image and localhost-only port 55439 before connecting; it accepts no arbitrary URL.
The scratch database must be empty on each run. The first fixture applies all
migrations, activates the empty registry and provisions the role, then connects as
that actual restricted login (local test-only trust authentication, no embedded
password). Storage/SMS use explicit in-memory test doubles only in this fixture.

Run only after authorizing disposable setup:

```
SCRAPMART_RUN_D3_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_runtime_role_postgresql.py
```

The tests cover real ORM signup/login, refresh/revoke, Vendor row locks, OTP/document
verification, reviewer approval, image INSERT/DELETE and commit-time guard rollback,
concurrent stock reservations, fulfillment, messaging participants/retries/read
receipts, forbidden policy/reviewer/DDL operations, identifier immutability,
PUBLIC/column/settings/membership/ownership/schema drift and idempotency. The suite
is skipped by default and must stay disabled in ordinary offline CI. After a run,
stop/remove only the verified disposable container; never reset existing databases
or repoint historical fixtures. PostgreSQL/Neon version, network and provider
acceptance remain staging operator checks; local tests do not prove live grants.
