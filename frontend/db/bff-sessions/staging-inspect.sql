-- READ ONLY. Run on the existing scrapmart_bff_staging database.
-- Confirm the Neon project/branch and connection identity outside SQL first.
SELECT current_database() AS connected_database, current_user AS connected_role,
       current_setting('server_version') AS server_version;

SELECT datname, pg_get_userbyid(datdba) AS owner, datacl
FROM pg_database
WHERE datname IN ('neondb', 'scrapmart_staging', 'scrapmart_bff_staging')
ORDER BY datname;

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolinherit, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname IN ('neondb_owner', 'scrapmart_bff_runtime')
ORDER BY rolname;

SELECT parent.rolname AS granted_role, member.rolname AS member_role
FROM pg_auth_members m
JOIN pg_roles parent ON parent.oid = m.roleid
JOIN pg_roles member ON member.oid = m.member
WHERE member.rolname = 'scrapmart_bff_runtime';

SELECT n.nspname AS schema_name, pg_get_userbyid(n.nspowner) AS owner, n.nspacl
FROM pg_namespace n WHERE n.nspname IN ('public', 'bff_sessions');

SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner) AS owner, c.relacl
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'bff_sessions';

SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS data_type,
       a.attnotnull AS not_null, a.attacl
FROM pg_attribute a WHERE a.attrelid = to_regclass('bff_sessions.sessions')
  AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum;
