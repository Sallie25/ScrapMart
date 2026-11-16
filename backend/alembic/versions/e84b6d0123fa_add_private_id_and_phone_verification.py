"""Private document metadata and shared one-time phone challenges.

Revision ID: e84b6d0123fa
Revises: d73a5c9012ef
No document bytes, phone evidence, challenges or approval are backfilled.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e84b6d0123fa'
down_revision = 'd73a5c9012ef'
branch_labels = None
depends_on = None
DOCUMENT_CHECK = "(identity_document_key IS NULL AND identification_type IS NULL AND identity_document_submitted_at IS NULL AND identity_document_status IS NULL) OR (identity_document_key IS NOT NULL AND length(identity_document_key) = 64 AND identification_type IS NOT NULL AND identification_type IN ('national_id', 'passport', 'drivers_license', 'voter_id') AND identity_document_submitted_at IS NOT NULL AND identity_document_status IS NOT NULL AND identity_document_status = 'submitted')"


def namespace():
    ctx = op.get_context()
    return ctx.opts.get('version_table_schema') or ('public' if ctx.dialect.name == 'postgresql' else None)


def upgrade():
    schema = namespace()
    for column in [sa.Column('identification_type', sa.String(32)), sa.Column('identity_document_key', sa.String(64)),
                   sa.Column('identity_document_submitted_at', sa.DateTime(timezone=True)), sa.Column('identity_document_status', sa.String(20))]:
        op.add_column('vendors', column, schema=schema)
    with op.batch_alter_table('vendors', schema=schema) as batch:
        batch.create_check_constraint('ck_vendor_identity_document', DOCUMENT_CHECK)
    op.create_table('phone_verifications',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey(f'{schema}.users.id' if schema else 'users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('phone_number', sa.String(20)), sa.Column('nonce', sa.Uuid()),
        sa.Column('code_digest', sa.LargeBinary(32)), sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent_at', sa.DateTime(timezone=True)), sa.Column('window_start', sa.DateTime(timezone=True)),
        sa.Column('sends', sa.Integer(), nullable=False, server_default='0'), sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('attempts BETWEEN 0 AND 5', name='ck_phone_attempts'),
        sa.CheckConstraint('sends BETWEEN 0 AND 6', name='ck_phone_sends'),
        sa.CheckConstraint('code_digest IS NULL OR length(code_digest) = 32', name='ck_phone_digest'),
        sa.CheckConstraint('code_digest IS NULL OR (phone_number IS NOT NULL AND nonce IS NOT NULL AND expires_at IS NOT NULL)', name='ck_phone_challenge'),
        sa.CheckConstraint('verified_at IS NULL OR (phone_number IS NOT NULL AND code_digest IS NULL)', name='ck_phone_verified'), schema=schema)
    install_phone_change_trigger(schema)


def install_phone_change_trigger(schema=None):
    if op.get_context().dialect.name == 'postgresql':
        q = op.get_context().dialect.identifier_preparer.quote_schema(schema or 'public')
        op.execute(f'''CREATE FUNCTION {q}.invalidate_phone_verification() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
          UPDATE {q}.phone_verifications SET phone_number = NULL, code_digest = NULL, expires_at = NULL, verified_at = NULL
          WHERE user_id = NEW.id;
          RETURN NEW;
        END $$''')
        op.execute(f'''CREATE TRIGGER invalidate_phone_verification AFTER UPDATE OF phone_number ON {q}.users
        FOR EACH ROW WHEN (OLD.phone_number IS DISTINCT FROM NEW.phone_number)
        EXECUTE FUNCTION {q}.invalidate_phone_verification()''')
    elif op.get_context().dialect.name == 'sqlite':
        op.execute('''CREATE TRIGGER invalidate_phone_verification AFTER UPDATE OF phone_number ON users
        WHEN OLD.phone_number IS NOT NEW.phone_number BEGIN
        UPDATE phone_verifications SET phone_number=NULL, code_digest=NULL, expires_at=NULL, verified_at=NULL WHERE user_id=NEW.id; END''')
    else:
        raise RuntimeError('Phone invalidation requires PostgreSQL or isolated SQLite tests')


def downgrade():
    schema = namespace()
    if op.get_context().dialect.name == 'postgresql':
        q = op.get_context().dialect.identifier_preparer.quote_schema(schema or 'public')
        op.execute(f'DROP TRIGGER invalidate_phone_verification ON {q}.users')
        op.execute(f'DROP FUNCTION {q}.invalidate_phone_verification()')
    else:
        op.execute('DROP TRIGGER invalidate_phone_verification')
    op.drop_table('phone_verifications', schema=schema)
    with op.batch_alter_table('vendors', schema=schema) as batch:
        batch.drop_constraint('ck_vendor_identity_document', type_='check')
    for name in ('identity_document_status', 'identity_document_submitted_at', 'identity_document_key', 'identification_type'):
        op.drop_column('vendors', name, schema=schema)
