# Batch 2D: proposed Neon BFF session setup

Preparation only. The dedicated database was reported created on the staging
branch; none of the role/schema SQL here has been run against Neon. Target supplied
for review: ScrapMart project `misty-star-68634503`, staging branch
`br-still-wildflower-b4kltqfa`. The databases are reported as `neondb`,
`scrapmart_staging`, and `scrapmart_bff_staging`; confirm the selected branch,
database, and owner before running SQL. Do not create the database again.
The runtime role is
`scrapmart_bff_runtime`. Keep `BFF_AUTH_ENABLED` unset or `false` throughout.

## Order and approval boundaries

1. **Read only, next step:** In the Neon Console, select the specified project,
   `staging` branch and `scrapmart_bff_staging` database. Confirm the selected
   role is `neondb_owner`. Run `db/bff-sessions/staging-inspect.sql` in the SQL
   Editor. Expect that the BFF database exists and is owned by `neondb_owner`,
   and the BFF role and schema are absent. Inspect existing `public` schema
   grants without changing them. Any existing BFF object or unexpected owner
   requires a fresh review.
2. **Write, separate approval:** In that same Console SQL Editor target, run
   `staging-provision.sql` as one script. It guards the database and current
   role, refuses existing BFF role/schema, and creates the `NOLOGIN` role,
   session objects and narrow grants in one transaction. It does not contain a
   password or psql commands. Check that the Editor accepts the whole script
   as a transaction; stop on any error and inspect before retrying.
3. **Read only:** Run `staging-verify.sql` in the SQL Editor. Expect a `NOLOGIN`
   role without memberships or ownership, the table/column grants below, and
   no BFF schema CREATE, DELETE or TRUNCATE. Compare the table constraints and
   index with the local fresh-install schema. Review PUBLIC grants and any
   unexpected inherited privileges before allowing a runtime login.
4. **Write, separate approval:** Use an interactive, TLS-verified `psql` client
   connected as the owner to this database. Run `\password scrapmart_bff_runtime`
   to enter a newly generated, high-entropy password without putting its clear
   text in a SQL file, SQL Editor history, command arguments or shell history.
   Then run `ALTER ROLE scrapmart_bff_runtime LOGIN;` only after the privilege
   checks pass. `\password` is a psql command and cannot run in the Neon SQL
   Editor. The BFF runtime secret belongs in an approved secret store; never
   deploy the owner credential. Re-run verification and test a direct TLS
   connection as runtime under separate authorization.

The next operation requiring explicit approval is **read-only Neon SQL Editor
inspection** in step 1. No provider operation is authorized by this
document. Every write step needs its own reviewed approval and target check.

## Exact runtime privilege matrix

| Object | Allowed | Denied |
| --- | --- | --- |
| `scrapmart_bff_staging` database | CONNECT | CREATE, ownership, grant option; TEMP may be inherited from PUBLIC and must be checked |
| `bff_sessions` schema | USAGE | CREATE, ownership, grant option |
| `bff_sessions.sessions` table | SELECT all columns; INSERT only `identifier_hash`, `root_hash`, `envelope`, `expires_at`; UPDATE only `envelope`, `status`, `refresh_attempt`, `refresh_started_at`, `revoked_at` | DELETE, TRUNCATE, REFERENCES, TRIGGER, ownership, grant option, UPDATE of identifier/family/expiry/creation columns |
| Role | NOLOGIN during provisioning; LOGIN only after separate password step, no memberships | SUPERUSER, CREATEDB, CREATEROLE, INHERIT, REPLICATION, BYPASSRLS |

No DELETE/cleanup privilege is given to runtime. Expired family cleanup is a
future owner-managed task. The role password is only for runtime; the owner
credential must never be deployed as the BFF connection credential.

## Managed-service checks and rollback

The provisioning script does not alter `neondb`, `scrapmart_staging`,
`neondb_owner`, the BFF database ACL, existing `public` schema grants, Neon
managed roles or global grants. It revokes PUBLIC access only on the new BFF
schema and table. PostgreSQL may give every role PUBLIC CONNECT or TEMP on a
database and USAGE on `public`; the verification queries show effective access.
Eliminating inherited access would require broader ACL changes and a separate
impact review. Object access in the other databases must be checked before
deployment; this script alone cannot guarantee isolation across the branch.

Neon-created Console/API roles inherit `neon_superuser` membership, so do not
create the runtime role through the Roles UI or API. SQL-created roles do not
receive that membership. If SQL `CREATE ROLE` fails, stop rather than changing
the role-creation method. Use a direct, TLS-verified PostgreSQL endpoint for
the later password step. The BFF runtime requires a DNS host, verified TLS and the exact
database/user names; no URL or owner account is accepted by its configuration.

If provisioning fails, leave authentication disabled and inspect the database.
The provisioning transaction should roll back its role and objects together.
Drop the role or BFF objects only after confirming ownership, zero sessions and
no other consumers under a separate destructive-operation approval. If sessions
exist, retain keys and encrypted records until an explicit migration or
revocation plan is approved. Do not retry a partially applied or pre-existing
schema as a fresh install.
