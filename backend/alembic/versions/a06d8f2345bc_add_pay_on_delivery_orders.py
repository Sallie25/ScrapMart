"""Single-listing pay-on-delivery orders with immutable agreement snapshots.

Revision ID: a06d8f2345bc
Revises: f95c7e1234ab
No existing inventory, prices, approvals or payment evidence is changed.
"""
from alembic import op
import sqlalchemy as sa

revision='a06d8f2345bc'
down_revision='f95c7e1234ab'
branch_labels=None
depends_on=None


def namespace():
    return op.get_context().opts.get('version_table_schema') or ('public' if op.get_context().dialect.name=='postgresql' else None)


def upgrade():
    ns=namespace()
    def fk(table): return f'{ns}.{table}.id' if ns else f'{table}.id'
    op.create_table('orders',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('buyer_profile_id',sa.Uuid(),sa.ForeignKey(fk('buyer_profiles'),ondelete='RESTRICT'),nullable=False),
        sa.Column('vendor_id',sa.Uuid(),sa.ForeignKey(fk('vendors'),ondelete='RESTRICT'),nullable=False),
        sa.Column('request_id',sa.Uuid(),nullable=False),sa.Column('vendor_business_name',sa.String(200),nullable=False),
        sa.Column('status',sa.String(20),nullable=False,server_default='pending'),
        sa.Column('currency',sa.String(3),nullable=False,server_default='NGN'),
        sa.Column('payment_method',sa.String(30),nullable=False,server_default='pay_on_delivery'),
        sa.Column('total_amount',sa.Numeric(26,2),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        *(sa.Column(name,sa.DateTime(timezone=True)) for name in ('accepted_at','preparing_at','delivered_at','completed_at','cancelled_at','rejected_at')),
        sa.CheckConstraint("status IN ('pending','accepted','preparing','delivered','completed','cancelled','rejected')",name='ck_orders_status'),
        sa.CheckConstraint("currency = 'NGN' AND payment_method = 'pay_on_delivery'",name='ck_orders_payment_method'),
        sa.CheckConstraint('total_amount >= 0 AND total_amount < 1000000000000000000000000',name='ck_orders_total'),
        sa.CheckConstraint("status <> 'accepted' OR accepted_at IS NOT NULL",name='ck_orders_accepted'),
        sa.CheckConstraint("status NOT IN ('preparing','delivered','completed') OR (accepted_at IS NOT NULL AND preparing_at IS NOT NULL)",name='ck_orders_preparing'),
        sa.CheckConstraint("status NOT IN ('delivered','completed') OR delivered_at IS NOT NULL",name='ck_orders_delivered'),
        sa.CheckConstraint("status <> 'completed' OR completed_at IS NOT NULL",name='ck_orders_completed'),
        sa.CheckConstraint("status <> 'cancelled' OR cancelled_at IS NOT NULL",name='ck_orders_cancelled'),
        sa.CheckConstraint("status <> 'rejected' OR rejected_at IS NOT NULL",name='ck_orders_rejected'),schema=ns)
    op.create_index('uq_orders_buyer_request','orders',['buyer_profile_id','request_id'],unique=True,schema=ns)
    op.create_index('ix_orders_buyer_created','orders',['buyer_profile_id','created_at','id'],schema=ns)
    op.create_index('ix_orders_vendor_created','orders',['vendor_id','created_at','id'],schema=ns)
    op.create_table('order_items',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('order_id',sa.Uuid(),sa.ForeignKey(fk('orders'),ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('listing_id',sa.Uuid(),sa.ForeignKey(fk('listings'),ondelete='RESTRICT'),nullable=False),
        sa.Column('listing_title',sa.String(200),nullable=False),sa.Column('quantity',sa.Numeric(14,3),nullable=False),
        sa.Column('quantity_unit',sa.String(30),nullable=False),sa.Column('listing_price',sa.Numeric(14,2),nullable=False),
        sa.Column('price_type',sa.String(20),nullable=False),sa.Column('line_total',sa.Numeric(26,2),nullable=False),
        sa.CheckConstraint('quantity > 0 AND quantity < 100000000000',name='ck_order_items_quantity'),
        sa.CheckConstraint("quantity_unit IN ('pieces','kilograms','tonnes','bundles')",name='ck_order_items_unit'),
        sa.CheckConstraint("quantity_unit <> 'pieces' OR quantity = trunc(quantity)",name='ck_order_items_pieces'),
        sa.CheckConstraint('listing_price >= 0 AND listing_price < 1000000000000',name='ck_order_items_price'),
        sa.CheckConstraint("price_type IN ('total','per_unit')",name='ck_order_items_price_type'),
        sa.CheckConstraint('line_total >= 0 AND line_total < 1000000000000000000000000',name='ck_order_items_total'),schema=ns)
    op.create_index('ix_order_items_listing','order_items',['listing_id'],schema=ns)
    install_guards(ns)


def install_guards(ns=None):
    immutable=('id','buyer_profile_id','vendor_id','request_id','vendor_business_name','currency','payment_method','total_amount','created_at')
    stamps=('accepted_at','preparing_at','delivered_at','completed_at','cancelled_at','rejected_at')
    transitions="((OLD.status = 'pending' AND NEW.status IN ('accepted','cancelled','rejected')) OR (OLD.status = 'accepted' AND NEW.status IN ('preparing','cancelled')) OR (OLD.status = 'preparing' AND NEW.status = 'delivered') OR (OLD.status = 'delivered' AND NEW.status = 'completed'))"
    if op.get_context().dialect.name=='postgresql':
        q=op.get_context().dialect.identifier_preparer.quote_schema(ns or 'public')
        frozen=' OR '.join(f'NEW.{name} IS DISTINCT FROM OLD.{name}' for name in immutable)
        timelines=' OR '.join(f'(OLD.{name} IS NOT NULL AND NEW.{name} IS DISTINCT FROM OLD.{name})' for name in stamps)
        op.execute(f"""CREATE FUNCTION {q}.guard_order_agreement() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
        BEGIN
          IF {frozen} OR {timelines} OR (NEW.status IS DISTINCT FROM OLD.status AND NOT {transitions}) THEN
            RAISE EXCEPTION 'Order agreement or transition is immutable';
          END IF;
          RETURN NEW;
        END $$""")
        op.execute(f'CREATE TRIGGER guard_order_agreement BEFORE UPDATE ON {q}.orders FOR EACH ROW EXECUTE FUNCTION {q}.guard_order_agreement()')
        op.execute(f"CREATE FUNCTION {q}.immutable_order_item() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN RAISE EXCEPTION 'Order item snapshot is immutable'; END $$")
        op.execute(f'CREATE TRIGGER immutable_order_item BEFORE UPDATE OR DELETE ON {q}.order_items FOR EACH ROW EXECUTE FUNCTION {q}.immutable_order_item()')
    elif op.get_context().dialect.name=='sqlite':
        frozen=' OR '.join(f'NEW.{name} IS NOT OLD.{name}' for name in immutable)
        timelines=' OR '.join(f'(OLD.{name} IS NOT NULL AND NEW.{name} IS NOT OLD.{name})' for name in stamps)
        op.execute(f"CREATE TRIGGER guard_order_agreement BEFORE UPDATE ON orders WHEN {frozen} OR {timelines} OR (NEW.status IS NOT OLD.status AND NOT {transitions}) BEGIN SELECT RAISE(ABORT,'Order agreement or transition is immutable'); END")
        for action in ('UPDATE','DELETE'):
            op.execute(f"CREATE TRIGGER immutable_order_item_{action.lower()} BEFORE {action} ON order_items BEGIN SELECT RAISE(ABORT,'Order item snapshot is immutable'); END")
    else: raise RuntimeError('Orders require PostgreSQL or isolated SQLite tests')


def downgrade():
    ns=namespace()
    if op.get_context().dialect.name=='postgresql':
        q=op.get_context().dialect.identifier_preparer.quote_schema(ns or 'public')
        op.execute(f'DROP TRIGGER immutable_order_item ON {q}.order_items')
        op.execute(f'DROP FUNCTION {q}.immutable_order_item()')
        op.execute(f'DROP TRIGGER guard_order_agreement ON {q}.orders')
        op.execute(f'DROP FUNCTION {q}.guard_order_agreement()')
    else:
        op.execute('DROP TRIGGER immutable_order_item_update');op.execute('DROP TRIGGER immutable_order_item_delete')
        op.execute('DROP TRIGGER guard_order_agreement')
    op.drop_table('order_items',schema=ns)
    op.drop_table('orders',schema=ns)
