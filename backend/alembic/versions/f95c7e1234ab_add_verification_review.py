"""Explicit reviewer grants, versioned review submission and immutable decisions.

Revision ID: f95c7e1234ab
Revises: e84b6d0123fa
No permissions, submissions, approvals, or audit evidence are backfilled.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f95c7e1234ab'
down_revision = 'e84b6d0123fa'
branch_labels = None
depends_on = None


def schema():
    return op.get_context().opts.get('version_table_schema') or ('public' if op.get_context().dialect.name == 'postgresql' else None)


def upgrade():
    ns = schema()
    user_fk = f'{ns}.users.id' if ns else 'users.id'
    vendor_fk = f'{ns}.vendors.id' if ns else 'vendors.id'
    op.create_table('verification_reviewers',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey(user_fk, ondelete='RESTRICT'), primary_key=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('provisioning_reference', sa.String(200), nullable=False), schema=ns)
    op.create_table('verification_review_audit',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('vendor_id', sa.Uuid(), sa.ForeignKey(vendor_fk, ondelete='RESTRICT'), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), sa.ForeignKey(user_fk, ondelete='RESTRICT'), nullable=False),
        sa.Column('reviewer_id', sa.Uuid(), sa.ForeignKey(user_fk, ondelete='RESTRICT')),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('evidence_revision', sa.String(64), nullable=False),
        sa.Column('case_version', sa.Integer(), nullable=False),
        sa.Column('previous_status', sa.String(20), nullable=False),
        sa.Column('new_status', sa.String(20), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.CheckConstraint("action IN ('submit','approve','reject','suspend','reopen')", name='ck_review_action'),
        sa.CheckConstraint("previous_status IN ('pending','approved','rejected','suspended') AND new_status IN ('pending','approved','rejected','suspended')", name='ck_review_status'),
        sa.CheckConstraint("(action = 'submit' AND reviewer_id IS NULL) OR (action <> 'submit' AND reviewer_id IS NOT NULL AND actor_user_id = reviewer_id)", name='ck_review_actor'),
        sa.CheckConstraint('length(evidence_revision) = 64 AND case_version > 0', name='ck_review_revision'), schema=ns)
    op.create_index('ix_review_vendor_version', 'verification_review_audit', ['vendor_id','case_version'], unique=True, schema=ns)
    for column in (sa.Column('verification_submission_revision',sa.String(64)),
                   sa.Column('verification_submitted_at',sa.DateTime(timezone=True)),
                   sa.Column('review_version',sa.Integer(),nullable=False,server_default='0'),
                   sa.Column('approval_review_id',sa.Uuid())):
        op.add_column('vendors',column,schema=ns)
    install_audit_guard(ns)


def install_audit_guard(ns=None):
    if op.get_context().dialect.name == 'postgresql':
        q = op.get_context().dialect.identifier_preparer.quote_schema(ns or 'public')
        op.execute(f"""CREATE FUNCTION {q}.immutable_verification_review() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
        BEGIN RAISE EXCEPTION 'Verification review audit is immutable'; END $$""")
        op.execute(f'CREATE TRIGGER immutable_verification_review BEFORE UPDATE OR DELETE ON {q}.verification_review_audit FOR EACH ROW EXECUTE FUNCTION {q}.immutable_verification_review()')
    elif op.get_context().dialect.name == 'sqlite':
        for action in ('UPDATE','DELETE'):
            op.execute(f"CREATE TRIGGER immutable_review_{action.lower()} BEFORE {action} ON verification_review_audit BEGIN SELECT RAISE(ABORT, 'Verification review audit is immutable'); END")
    else:
        raise RuntimeError('Review audit requires PostgreSQL or isolated SQLite tests')


def downgrade():
    ns = schema()
    if op.get_context().dialect.name == 'postgresql':
        q = op.get_context().dialect.identifier_preparer.quote_schema(ns or 'public')
        op.execute(f'DROP TRIGGER immutable_verification_review ON {q}.verification_review_audit')
        op.execute(f'DROP FUNCTION {q}.immutable_verification_review()')
    else:
        op.execute('DROP TRIGGER immutable_review_update')
        op.execute('DROP TRIGGER immutable_review_delete')
    for name in ('approval_review_id','review_version','verification_submitted_at','verification_submission_revision'):
        op.drop_column('vendors',name,schema=ns)
    op.drop_index('ix_review_vendor_version',table_name='verification_review_audit',schema=ns)
    op.drop_table('verification_review_audit',schema=ns)
    op.drop_table('verification_reviewers',schema=ns)
