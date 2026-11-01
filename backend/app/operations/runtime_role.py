"""Staging-only explicit column ACLs for an ordinary trusted API process.

No passwords, login enablement, ownership changes or automatic privilege repair.
Caller owns a transaction and must authenticate/verify the staging endpoint first.
"""
from sqlalchemy import text

HEAD = 'c28fa4567def'
ROLE = 'scrapmart_staging_api'
DATABASE = 'scrapmart_staging'
SEARCH_PATH = 'search_path=pg_catalog, public, pg_temp'
# Frozen column inventories: reject schema drift instead of granting new columns.
COLUMNS = {
    'users': 'id email role password_hash full_name phone_number is_active created_at updated_at',
    'buyer_profiles': 'id user_id created_at signup_completed_at',
    'auth_sessions': 'id user_id created_at expires_at revoked_at',
    'refresh_tokens': 'id session_id token_digest created_at expires_at consumed_at',
    'email_identity_policy_state': 'id policy_version status last_user_id users_processed source_count manifest_sha256 updated_at',
    'email_identity_reservations': 'id lookup_key state user_id policy_version created_at',
    'phone_verifications': 'user_id phone_number nonce code_digest expires_at attempts sent_at window_start sends verified_at',
    'vendors': 'id user_id business_name shop_location shop_address identification_type identity_document_key identity_document_submitted_at identity_document_status verification_submission_revision verification_submitted_at review_version approval_review_id verification_status created_at updated_at',
    'verification_reviewers': 'user_id granted_at revoked_at provisioning_reference',
    'verification_review_audit': 'id vendor_id actor_user_id reviewer_id action evidence_revision case_version previous_status new_status decided_at reason',
    'categories': 'id name slug is_active created_at updated_at',
    'listings': 'id vendor_id category_id title description price currency price_type is_negotiable quantity quantity_unit condition status location_summary lga area latitude longitude location_visibility directions_allowed published_at created_at updated_at',
    'listing_images': 'id listing_id object_key position content_type size_bytes width height created_at',
    'orders': 'id buyer_profile_id vendor_id request_id vendor_business_name status currency payment_method total_amount created_at updated_at accepted_at preparing_at delivered_at completed_at cancelled_at rejected_at',
    'order_items': 'id order_id listing_id listing_title quantity quantity_unit listing_price price_type line_total',
    'conversations': 'id listing_id buyer_profile_id vendor_id created_at',
    'messages': 'id conversation_id sender_side request_id content created_at read_at',
}
COLUMNS = {table: set(columns.split()) for table, columns in COLUMNS.items()}
SELECT = {table: set(columns) for table, columns in COLUMNS.items()}
SELECT['email_identity_policy_state'] = {'id', 'status', 'policy_version'}
SELECT['email_identity_reservations'] -= {'created_at'}
INSERT = {table: set(COLUMNS[table]) for table in (
    'buyer_profiles', 'auth_sessions', 'refresh_tokens', 'phone_verifications',
    'verification_review_audit', 'orders', 'order_items', 'conversations', 'messages')}
INSERT['users'] = COLUMNS['users'] - {'created_at', 'updated_at'}
INSERT['email_identity_reservations'] = {'id', 'lookup_key', 'state', 'user_id'}
for _table in ('vendors', 'listings'):
    INSERT[_table] = COLUMNS[_table] - {'created_at', 'updated_at'}
INSERT['listing_images'] = COLUMNS['listing_images'] - {'created_at'}
UPDATE = {
    'users': {'updated_at'}, 'buyer_profiles': {'id'}, 'categories': {'id'},
    'email_identity_policy_state': {'id'}, 'email_identity_reservations': {'id'},
    'auth_sessions': {'revoked_at'}, 'refresh_tokens': {'consumed_at'},
    'phone_verifications': COLUMNS['phone_verifications'] - {'user_id'},
    'vendors': COLUMNS['vendors'] - {'id', 'user_id', 'created_at'},
    'listings': COLUMNS['listings'] - {'vendor_id', 'currency', 'created_at'},
    'orders': set('status updated_at accepted_at preparing_at delivered_at completed_at cancelled_at rejected_at'.split()),
    'conversations': {'id'}, 'messages': {'read_at'},
}
MANIFEST = {'SELECT': SELECT, 'INSERT': INSERT, 'UPDATE': UPDATE}


class RuntimeRoleRejected(RuntimeError):
    def __init__(self):
        super().__init__('Runtime role preconditions or privilege audit failed')


def require(condition):
    if not condition: raise RuntimeRoleRejected()


def audit_database_privileges(db, role_oid):
    """TEMP is allowed only via PUBLIC, never a direct runtime ACL or membership.

    acldefault handles the normal PostgreSQL NULL datacl representation. Owners
    and outward memberships are independently rejected by audit(). No ACLs on
    PUBLIC or provider-managed roles are changed by this provisioner.
    """
    acl = db.execute(text("""SELECT a.grantee,a.privilege_type,a.is_grantable
        FROM pg_catalog.pg_database d
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(d.datacl,pg_catalog.acldefault('d',d.datdba))) a
        WHERE d.datname=current_database()""")).all()
    require(all(privilege == 'CONNECT' and not grantable
                for grantee, privilege, grantable in acl if grantee == role_oid))
    public_temp = any(grantee == 0 and privilege == 'TEMPORARY' and not grantable
                      for grantee, privilege, grantable in acl)
    require(not db.execute(text("SELECT has_database_privilege(:role,current_database(),'CREATE')"), {'role': ROLE}).scalar_one())
    effective_temp = db.execute(text("SELECT has_database_privilege(:role,current_database(),'TEMPORARY')"), {'role': ROLE}).scalar_one()
    require(effective_temp == public_temp)
    require(not db.execute(text("SELECT has_database_privilege(:role,current_database(),'TEMPORARY WITH GRANT OPTION')"), {'role': ROLE}).scalar_one())


def audit(db, *, require_complete=False):
    """Reject excess effective ACLs, PUBLIC paths, grant options and role drift."""
    role = db.execute(text('''SELECT oid, rolsuper, rolcreatedb, rolcreaterole, rolinherit,
        rolreplication, rolbypassrls, rolconfig FROM pg_catalog.pg_roles WHERE rolname=:role'''), {'role': ROLE}).one()
    oid = role[0]
    require(not any(role[1:7]))
    require(role[7] is None or role[7] == [SEARCH_PATH])
    configs = db.execute(text('''SELECT setconfig FROM pg_catalog.pg_db_role_setting
        WHERE setrole=:oid AND (setdatabase=0 OR setdatabase=(SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()))'''), {'oid': oid}).scalars().all()
    require(all(config == [SEARCH_PATH] for config in configs))
    require(not db.execute(text("SELECT has_database_privilege(:role,current_database(),'CONNECT WITH GRANT OPTION')"), {'role': ROLE}).scalar_one())
    require(not db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE has_schema_privilege(:role,oid,'USAGE WITH GRANT OPTION'))"), {'role': ROLE}).scalar_one())
    require(db.execute(text("SELECT pg_catalog.shobj_description(:oid,'pg_authid')"), {'oid': oid}).scalar_one() == 'ScrapMart staging API ACL manifest D3')
    require(not db.execute(text('SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=:oid)'), {'oid': oid}).scalar_one())
    # PostgreSQL 16+ automatically gives a non-superuser role creator ADMIN on
    # the new role. Permit only that operator's admin-only reverse membership;
    # it grants no elevated membership to the runtime role itself.
    require(not db.execute(text('''SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members
        WHERE roleid=:oid AND NOT (member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)
        AND admin_option AND NOT inherit_option AND NOT set_option))'''), {'oid': oid}).scalar_one())
    require(not db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=:oid AND deptype='o')"), {'oid': oid}).scalar_one())
    audit_database_privileges(db, oid)
    # Reject CREATE in every schema, including privilege inherited from PUBLIC.
    require(not db.execute(text('SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE has_schema_privilege(:role,oid,\'CREATE\'))'), {'role': ROLE}).scalar_one())
    objects = db.execute(text("""SELECT c.oid,n.nspname,c.relname,c.relkind FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
          AND n.nspname NOT LIKE 'pg_temp%' AND c.relkind IN ('r','p','v','m','f','S')""")).all()
    for object_id, schema, table, kind in objects:
        if kind == 'S':
            require(not db.execute(text("SELECT has_sequence_privilege(:role,:id,'USAGE,SELECT,UPDATE')"), {'role': ROLE, 'id': object_id}).scalar_one())
            continue
        permitted = schema == 'public' and table in COLUMNS
        for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
            allowed = permitted and table == 'listing_images' and privilege == 'DELETE'
            actual = db.execute(text('SELECT has_table_privilege(:role,:id,:p)'), {'role': ROLE, 'id': object_id, 'p': privilege}).scalar_one()
            require(not actual or allowed)
            if require_complete and allowed: require(actual)
            require(not db.execute(text('SELECT has_table_privilege(:role,:id,:p)'), {'role': ROLE, 'id': object_id, 'p': privilege+' WITH GRANT OPTION'}).scalar_one())
        columns = db.execute(text('SELECT attnum,attname FROM pg_catalog.pg_attribute WHERE attrelid=:id AND attnum>0 AND NOT attisdropped'), {'id': object_id}).all()
        if permitted: require({name for _, name in columns} == COLUMNS[table])
        for number, name in columns:
            for privilege in ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES'):
                allowed = permitted and name in MANIFEST.get(privilege, {}).get(table, set())
                actual = db.execute(text('SELECT has_column_privilege(:role,:id,:n,:p)'), {'role': ROLE, 'id': object_id, 'n': number, 'p': privilege}).scalar_one()
                require(not actual or allowed)
                if require_complete and allowed: require(actual)
                require(not db.execute(text('SELECT has_column_privilege(:role,:id,:n,:p)'), {'role': ROLE, 'id': object_id, 'n': number, 'p': privilege+' WITH GRANT OPTION'}).scalar_one())
    # Privileged custom routines may create an escalation path outside table ACLs.
    require(not db.execute(text("""SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND p.prosecdef
        AND has_function_privilege(:role,p.oid,'EXECUTE'))"""), {'role': ROLE}).scalar_one())
    require(not db.execute(text("SELECT has_parameter_privilege(:role,'session_replication_role','SET,ALTER SYSTEM')"), {'role': ROLE}).scalar_one())


def provision(db):
    require(db.dialect.name == 'postgresql' and db.in_transaction())
    require(not db.dialect.detect_autocommit_setting(db.connection.driver_connection))
    identity = db.execute(text('SELECT current_database(),pg_is_in_recovery(),current_user')).one()
    require(identity[0] == DATABASE and identity[1] is False and identity[2] != ROLE)
    db.execute(text('LOCK TABLE public.alembic_version IN SHARE MODE'))
    db.execute(text('LOCK TABLE public.email_identity_policy_state IN SHARE MODE'))
    require(db.execute(text('SELECT version_num FROM public.alembic_version')).scalars().all() == [HEAD])
    require(db.execute(text("SELECT count(*) FROM public.email_identity_policy_state WHERE status='ready' AND policy_version=1")).scalar_one() == 1)
    db.execute(text("SELECT pg_advisory_xact_lock(754031893245)"))
    if not db.execute(text('SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=:role)'), {'role': ROLE}).scalar_one():
        db.execute(text("SET LOCAL createrole_self_grant=''"))
        db.execute(text(f'CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'))
        db.execute(text(f"COMMENT ON ROLE {ROLE} IS 'ScrapMart staging API ACL manifest D3'"))
    audit(db)  # Existing unexpected privileges are rejected, never silently revoked.
    objects = db.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")).scalars().all()
    require(set(objects) == set(COLUMNS) | {'alembic_version'})
    # Verify the new identifier fences are present/enabled before granting locks.
    guards = db.execute(text("""SELECT c.relname FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
        WHERE n.nspname='public' AND pn.nspname='public' AND t.tgname='guard_runtime_identifier'
        AND t.tgenabled='O' AND t.tgtype=19 AND t.tgattr::text='1'
        AND p.proname='guard_runtime_identifier' AND NOT p.prosecdef AND p.proconfig=ARRAY['search_path=pg_catalog']""")).scalars().all()
    require(set(guards) == {'buyer_profiles', 'categories', 'listings'})
    functions = db.execute(text("""SELECT p.proname FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
        AND p.proname IN ('scrapmart_lock_image_listing','scrapmart_check_listing_images')
        AND NOT p.prosecdef AND p.proconfig=ARRAY['search_path=pg_catalog']""")).scalars().all()
    require(set(functions) == {'scrapmart_lock_image_listing', 'scrapmart_check_listing_images'})
    db.execute(text(f'GRANT CONNECT ON DATABASE {DATABASE} TO {ROLE}'))
    db.execute(text(f'GRANT USAGE ON SCHEMA public TO {ROLE}'))
    for privilege, tables in MANIFEST.items():
        for table, columns in tables.items():
            db.execute(text(f'GRANT {privilege} ({", ".join(sorted(columns))}) ON public.{table} TO {ROLE}'))
    db.execute(text(f'GRANT DELETE ON public.listing_images TO {ROLE}'))
    db.execute(text(f'ALTER ROLE {ROLE} IN DATABASE {DATABASE} SET search_path=pg_catalog,public,pg_temp'))
    audit(db, require_complete=True)
