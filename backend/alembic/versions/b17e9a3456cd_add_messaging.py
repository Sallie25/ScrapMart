"""Listing-scoped Buyer–Vendor conversations and text messages.

Revision ID: b17e9a3456cd
Revises: a06d8f2345bc
"""
from alembic import op
import sqlalchemy as sa

revision = 'b17e9a3456cd'
down_revision = 'a06d8f2345bc'
branch_labels = None
depends_on = None


def upgrade():
    ns = op.get_context().opts.get('version_table_schema')
    def fk(table): return f'{ns}.{table}.id' if ns else f'{table}.id'
    op.create_table('conversations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('listing_id', sa.Uuid(), sa.ForeignKey(fk('listings'), ondelete='RESTRICT'), nullable=False),
        sa.Column('buyer_profile_id', sa.Uuid(), sa.ForeignKey(fk('buyer_profiles'), ondelete='RESTRICT'), nullable=False),
        sa.Column('vendor_id', sa.Uuid(), sa.ForeignKey(fk('vendors'), ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('buyer_profile_id', 'listing_id', name='uq_conversation_buyer_listing'), schema=ns)
    for side in ('buyer', 'vendor'):
        op.create_index(f'ix_conversation_{side}_created', 'conversations',
                        ['buyer_profile_id' if side == 'buyer' else 'vendor_id', 'created_at', 'id'], schema=ns)
    op.create_table('messages',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('conversation_id', sa.Uuid(), sa.ForeignKey(fk('conversations'), ondelete='RESTRICT'), nullable=False),
        sa.Column('sender_side', sa.String(6), nullable=False),
        sa.Column('request_id', sa.Uuid()),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('read_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('conversation_id', 'sender_side', 'request_id', name='uq_message_request'),
        sa.CheckConstraint("sender_side IN ('buyer', 'vendor')", name='ck_message_sender'),
        sa.CheckConstraint('length(trim(content)) BETWEEN 1 AND 4000', name='ck_message_content'), schema=ns)
    op.create_index('ix_message_history', 'messages', ['conversation_id', 'created_at', 'id'], schema=ns)
    op.create_index('ix_message_unread', 'messages', ['conversation_id', 'sender_side', 'read_at'], schema=ns)
    install_guards(ns)


def install_guards(ns=None):
    if op.get_context().dialect.name == 'postgresql':
        q = op.get_context().dialect.identifier_preparer.quote_schema(ns or 'public')
        op.execute(f'''CREATE FUNCTION {q}.guard_conversation() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
        BEGIN
          IF TG_OP = 'UPDATE' THEN
            IF ROW(NEW.id, NEW.listing_id, NEW.buyer_profile_id, NEW.vendor_id, NEW.created_at)
              IS DISTINCT FROM ROW(OLD.id, OLD.listing_id, OLD.buyer_profile_id, OLD.vendor_id, OLD.created_at)
            THEN RAISE EXCEPTION 'Conversation participants are immutable'; END IF;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM {q}.listings l JOIN {q}.vendors v ON v.id=l.vendor_id
            JOIN {q}.buyer_profiles b ON b.id=NEW.buyer_profile_id
            WHERE l.id=NEW.listing_id AND l.vendor_id=NEW.vendor_id AND b.user_id<>v.user_id)
          THEN RAISE EXCEPTION 'Invalid conversation participants'; END IF;
          RETURN NEW;
        END $$''')
        op.execute(f'CREATE TRIGGER guard_conversation BEFORE INSERT OR UPDATE ON {q}.conversations FOR EACH ROW EXECUTE FUNCTION {q}.guard_conversation()')
    elif op.get_context().dialect.name == 'sqlite':
        op.execute('''CREATE TRIGGER guard_conversation_insert BEFORE INSERT ON conversations WHEN NOT EXISTS (
          SELECT 1 FROM listings l JOIN vendors v ON v.id=l.vendor_id JOIN buyer_profiles b ON b.id=NEW.buyer_profile_id
          WHERE l.id=NEW.listing_id AND l.vendor_id=NEW.vendor_id AND b.user_id<>v.user_id)
          BEGIN SELECT RAISE(ABORT,'Invalid conversation participants'); END''')
        op.execute("CREATE TRIGGER guard_conversation_update BEFORE UPDATE ON conversations BEGIN SELECT RAISE(ABORT,'Conversation is immutable'); END")
    else:
        raise RuntimeError('Messaging requires PostgreSQL or isolated SQLite tests')


def downgrade():
    ns = op.get_context().opts.get('version_table_schema')
    op.drop_table('messages', schema=ns)
    op.drop_table('conversations', schema=ns)
    if op.get_context().dialect.name == 'postgresql':
        q = op.get_context().dialect.identifier_preparer.quote_schema(ns or 'public')
        op.execute(f'DROP FUNCTION {q}.guard_conversation()')
