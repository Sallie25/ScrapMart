-- REVIEW ONLY. Batch 3B.4 fresh-install schema; not a migration. PostgreSQL 16+.
-- A separately authenticated owner creates the dedicated disposable database
-- scrapmart_bff_local_test outside this script. Connect to that database only.
BEGIN;
DO $$ BEGIN
  IF current_database() <> 'scrapmart_bff_local_test' THEN
    RAISE EXCEPTION 'Dedicated local database required';
  END IF;
END $$;
CREATE ROLE scrapmart_bff_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE ALL ON DATABASE scrapmart_bff_local_test FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA bff_sessions;
REVOKE ALL ON SCHEMA bff_sessions FROM PUBLIC;
CREATE TABLE bff_sessions.sessions (
  identifier_hash text PRIMARY KEY CHECK (identifier_hash ~ '^[0-9a-f]{64}$'),
  root_hash text NOT NULL REFERENCES bff_sessions.sessions(identifier_hash),
  envelope jsonb,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','refreshing','retired','uncertain','revoked')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  refresh_attempt uuid,
  refresh_started_at timestamptz,
  revoked_at timestamptz,
  CHECK (expires_at > created_at),
  CHECK ((status IN ('active','refreshing') AND envelope IS NOT NULL) OR
         (status IN ('retired','uncertain','revoked') AND envelope IS NULL)),
  CHECK (status <> 'refreshing' OR (refresh_attempt IS NOT NULL AND refresh_started_at IS NOT NULL)),
  CHECK (status <> 'active' OR (refresh_attempt IS NULL AND refresh_started_at IS NULL)),
  CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))
);
-- root_hash is immutable to runtime UPDATEs. The original row remains the stable
-- family revocation gate even after retirement. Completion locks that root before
-- atomically retiring an identifier and inserting its undisclosed successor.
-- Expiry cleanup must remove entire expired families, not a referenced root alone.
CREATE INDEX sessions_expiry ON bff_sessions.sessions (expires_at);
REVOKE ALL ON bff_sessions.sessions FROM PUBLIC;
GRANT CONNECT ON DATABASE scrapmart_bff_local_test TO scrapmart_bff_runtime;
GRANT USAGE ON SCHEMA bff_sessions TO scrapmart_bff_runtime;
GRANT SELECT ON bff_sessions.sessions TO scrapmart_bff_runtime;
GRANT INSERT (identifier_hash,root_hash,envelope,expires_at) ON bff_sessions.sessions TO scrapmart_bff_runtime;
GRANT UPDATE (envelope,status,refresh_attempt,refresh_started_at,revoked_at)
  ON bff_sessions.sessions TO scrapmart_bff_runtime;
ALTER ROLE scrapmart_bff_runtime IN DATABASE scrapmart_bff_local_test
  SET search_path = pg_catalog,bff_sessions,pg_temp;
COMMIT;
-- No passwords or LOGIN activation here. Owner-only expiry cleanup; runtime has
-- no DELETE, TRUNCATE, DDL, object ownership, grant options or role memberships.
