-- MUTATING fresh install only. Plain SQL suitable for Neon SQL Editor.
-- Connect as the authorized owner to scrapmart_bff_staging on the named staging branch.
-- Creates a NOLOGIN role. Set its password and enable LOGIN separately after verification.
BEGIN;
DO $$ BEGIN
  IF current_database() <> 'scrapmart_bff_staging' OR current_user <> 'neondb_owner' THEN
    RAISE EXCEPTION 'Wrong database or owner';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrapmart_bff_runtime') OR
     EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'bff_sessions') THEN
    RAISE EXCEPTION 'Existing role or schema requires separate migration review';
  END IF;
END $$;
CREATE ROLE scrapmart_bff_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOINHERIT NOREPLICATION NOBYPASSRLS;
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
CREATE INDEX sessions_expiry ON bff_sessions.sessions (expires_at);
REVOKE ALL ON bff_sessions.sessions FROM PUBLIC;
GRANT CONNECT ON DATABASE scrapmart_bff_staging TO scrapmart_bff_runtime;
GRANT USAGE ON SCHEMA bff_sessions TO scrapmart_bff_runtime;
GRANT SELECT ON bff_sessions.sessions TO scrapmart_bff_runtime;
GRANT INSERT (identifier_hash,root_hash,envelope,expires_at) ON bff_sessions.sessions TO scrapmart_bff_runtime;
GRANT UPDATE (envelope,status,refresh_attempt,refresh_started_at,revoked_at)
  ON bff_sessions.sessions TO scrapmart_bff_runtime;
ALTER ROLE scrapmart_bff_runtime IN DATABASE scrapmart_bff_staging
  SET search_path = pg_catalog,bff_sessions,pg_temp;
COMMIT;
