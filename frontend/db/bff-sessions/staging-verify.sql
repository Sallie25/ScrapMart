-- READ ONLY. Run on scrapmart_bff_staging after approved provisioning.
-- A missing role/table is a failure; inspect.sql can be run before creation.
SELECT current_database() AS connected_database, current_user AS connected_role,
       pg_get_userbyid(d.datdba) AS database_owner,
       pg_get_userbyid(n.nspowner) AS schema_owner,
       pg_get_userbyid(c.relowner) AS table_owner
FROM pg_database d, pg_namespace n, pg_class c
WHERE d.datname = current_database() AND n.nspname = 'bff_sessions'
  AND c.relnamespace = n.oid AND c.relname = 'sessions';

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolinherit, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname = 'scrapmart_bff_runtime';

SELECT d.datname,
       has_database_privilege('scrapmart_bff_runtime', d.oid, 'CONNECT') AS can_connect,
       has_database_privilege('scrapmart_bff_runtime', d.oid, 'CREATE') AS can_create,
       has_database_privilege('scrapmart_bff_runtime', d.oid, 'TEMP') AS can_temp
FROM pg_database d
WHERE d.datname IN ('neondb', 'scrapmart_staging', 'scrapmart_bff_staging')
ORDER BY d.datname;

SELECT has_schema_privilege('scrapmart_bff_runtime', 'bff_sessions', 'USAGE') AS schema_usage,
       has_schema_privilege('scrapmart_bff_runtime', 'bff_sessions', 'CREATE') AS schema_create,
       has_schema_privilege('scrapmart_bff_runtime', 'public', 'USAGE') AS public_usage,
       has_schema_privilege('scrapmart_bff_runtime', 'public', 'CREATE') AS public_create,
       has_table_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', 'SELECT') AS table_select,
       has_table_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', 'DELETE') AS table_delete,
       has_table_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', 'TRUNCATE') AS table_truncate,
       has_table_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', 'REFERENCES') AS table_references,
       has_table_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', 'TRIGGER') AS table_trigger,
       has_table_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', 'SELECT WITH GRANT OPTION') AS can_grant_select;

SELECT a.attname,
       has_column_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', a.attname, 'INSERT') AS can_insert,
       has_column_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', a.attname, 'UPDATE') AS can_update,
       has_column_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', a.attname, 'INSERT WITH GRANT OPTION') AS can_grant_insert,
       has_column_privilege('scrapmart_bff_runtime', 'bff_sessions.sessions', a.attname, 'UPDATE WITH GRANT OPTION') AS can_grant_update
FROM pg_attribute a WHERE a.attrelid = 'bff_sessions.sessions'::regclass
  AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum;

SELECT parent.rolname AS granted_role, member.rolname AS member_role
FROM pg_auth_members m JOIN pg_roles parent ON parent.oid = m.roleid
JOIN pg_roles member ON member.oid = m.member
WHERE member.rolname = 'scrapmart_bff_runtime';

SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE conrelid = 'bff_sessions.sessions'::regclass
ORDER BY conname;

SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = 'bff_sessions' AND tablename = 'sessions'
ORDER BY indexname;
