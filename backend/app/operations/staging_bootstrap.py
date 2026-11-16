"""Activate only a pristine, fully migrated staging registry under a writer fence.

Populated databases and non-pristine policy state are deliberately unsupported.
This does not grant permissions, insert Users, or bypass reservation triggers.
"""
import hashlib
from sqlalchemy import text
from app.modules.auth.email_identity_models import POLICY_STATE_ID
from app.modules.auth.email_identity_policy import policy_fingerprint

HEAD = 'c28fa4567def'
FINGERPRINT = 'cbdc5198ab2b1c3f23062e5318c97f0ab4e403023a69035e355bc8e8c431e59f'


class BootstrapRejected(RuntimeError):
    def __init__(self):
        super().__init__('Empty staging bootstrap preconditions were not satisfied')


def check_target(db, database, role):
    if db.dialect.name != 'postgresql' or not database or not role:
        raise BootstrapRejected()
    if db.dialect.detect_autocommit_setting(db.connection.driver_connection):
        raise BootstrapRejected()
    actual = db.execute(text('SELECT current_database(), current_user, pg_is_in_recovery()')).one()
    if tuple(actual) != (database, role, False): raise BootstrapRejected()
    # All application migrations assume public in the normal deployment path.
    db.execute(text('SET LOCAL search_path=public,pg_catalog'))


def empty_manifest():
    source = hashlib.sha256(b'scrapmart-email-source-v1\0' + FINGERPRINT.encode('ascii')).digest()
    return hashlib.sha256(b'scrapmart-email-checkpoint-v1\0' + FINGERPRINT.encode('ascii')
                          + source + bytes(8) + bytes(16)).digest()


def activate_empty(db):
    if policy_fingerprint() != FINGERPRINT: raise BootstrapRejected()
    # Fence migrations and every identity writer until the activation commits.
    for table, mode in (('alembic_version', 'SHARE'), ('users', 'SHARE'),
                        ('email_identity_reservations', 'SHARE'),
                        ('email_identity_policy_state', 'EXCLUSIVE')):
        db.execute(text(f'LOCK TABLE public.{table} IN {mode} MODE'))
    if db.execute(text('SELECT version_num FROM public.alembic_version')).scalars().all() != [HEAD]:
        raise BootstrapRejected()
    # Require actual enabled migration guards, not just ORM-created tables.
    guards = db.execute(text("""SELECT c.relname, t.tgname FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
        JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
        WHERE n.nspname='public' AND pn.nspname='public' AND NOT t.tgisinternal
        AND t.tgenabled='O' AND NOT p.prosecdef
        AND ((t.tgname='ct_users_email_reservation' AND p.proname='verify_user_email_reservation'
              AND t.tgtype=5 AND t.tgconstraint<>0 AND NOT t.tgdeferrable)
          OR (t.tgname='tr_users_email_immutable' AND p.proname='reject_user_email_change' AND t.tgtype=17)
          OR (t.tgname='tr_email_reservation_immutable' AND p.proname='guard_email_reservation_update' AND t.tgtype=17))
        AND current_setting('session_replication_role')='origin'""")).all()
    if set(map(tuple, guards)) != {
        ('users', 'ct_users_email_reservation'), ('users', 'tr_users_email_immutable'),
        ('email_identity_reservations', 'tr_email_reservation_immutable'),
    }: raise BootstrapRejected()
    constraints = db.execute(text("""SELECT conname FROM pg_catalog.pg_constraint
        WHERE conrelid IN ('public.email_identity_reservations'::regclass,
                          'public.email_identity_policy_state'::regclass)
        AND convalidated""")).scalars().all()
    required = {'uq_eir_lookup_key', 'fk_eir_user', 'ck_eir_policy_version', 'ck_eir_ownership',
                'ck_eir_ascii_key', 'ck_eips_singleton', 'ck_eips_policy_version',
                'ck_eips_status', 'ck_eips_counts', 'ck_eips_manifest', 'ck_eips_ready'}
    if not required.issubset(constraints): raise BootstrapRejected()
    for table in ('users', 'email_identity_reservations'):
        if db.execute(text(f'SELECT EXISTS (SELECT 1 FROM public.{table})')).scalar_one():
            raise BootstrapRejected()
    rows = db.execute(text('SELECT * FROM public.email_identity_policy_state FOR UPDATE')).mappings().all()
    if len(rows) != 1: raise BootstrapRejected()
    state = rows[0]
    if (state['id'] != POLICY_STATE_ID or state['policy_version'] != 1
        or state['status'] != 'building' or state['last_user_id'] is not None
        or state['users_processed'] != 0 or state['source_count'] != 0
        or state['manifest_sha256'] is not None): raise BootstrapRejected()
    db.execute(text('SET LOCAL synchronous_commit=on'))
    result = db.execute(text("""UPDATE public.email_identity_policy_state
        SET status='ready', manifest_sha256=:manifest, updated_at=clock_timestamp()
        WHERE id=:id AND status='building' AND policy_version=1
          AND last_user_id IS NULL AND users_processed=0 AND source_count=0
          AND manifest_sha256 IS NULL"""), {'manifest': empty_manifest(), 'id': POLICY_STATE_ID})
    if result.rowcount != 1: raise BootstrapRejected()
