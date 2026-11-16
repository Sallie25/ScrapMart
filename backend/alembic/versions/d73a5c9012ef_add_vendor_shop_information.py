"""Add nullable private Vendor shop information; preserve existing records.

Revision ID: d73a5c9012ef
Revises: c42f7d18a903
"""
from alembic import op
import sqlalchemy as sa

revision = "d73a5c9012ef"
down_revision = "c42f7d18a903"
branch_labels = None
depends_on = None


def upgrade():
    schema = op.get_context().opts.get("version_table_schema")
    op.add_column("vendors", sa.Column("shop_location", sa.String(200), nullable=True), schema=schema)
    op.add_column("vendors", sa.Column("shop_address", sa.String(500), nullable=True), schema=schema)


def downgrade():
    schema = op.get_context().opts.get("version_table_schema")
    op.drop_column("vendors", "shop_address", schema=schema)
    op.drop_column("vendors", "shop_location", schema=schema)
