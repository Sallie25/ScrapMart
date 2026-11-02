"""Immutable lock identifiers and schema-qualified photo guards.

Revision ID: c28fa4567def
Revises: b17e9a3456cd
No rows, owners, database roles or existing grants on tables are changed.
"""
from alembic import op

revision = 'c28fa4567def'
down_revision = 'b17e9a3456cd'
branch_labels = None
depends_on = None


def namespace():
    return op.get_context().opts.get('version_table_schema') or 'public'


def upgrade():
    if op.get_context().dialect.name != 'postgresql':
        raise RuntimeError('Restricted runtime guards require PostgreSQL')
    q = op.get_context().dialect.identifier_preparer.quote_schema(namespace())
    op.execute(f'''CREATE FUNCTION {q}.guard_runtime_identifier() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
        BEGIN
          IF NEW.id IS DISTINCT FROM OLD.id THEN
            RAISE EXCEPTION 'Identifier is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$''')
    for table in ('buyer_profiles', 'categories', 'listings'):
        op.execute(f'''CREATE TRIGGER guard_runtime_identifier BEFORE UPDATE OF id ON {q}.{table}
            FOR EACH ROW EXECUTE FUNCTION {q}.guard_runtime_identifier()''')
    # Keep the real parent UPDATE: it invalidates stale isolation snapshots.
    op.execute(f'''CREATE OR REPLACE FUNCTION {q}.scrapmart_lock_image_listing() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
        DECLARE parent_id uuid;
        BEGIN
          FOR parent_id IN
            SELECT DISTINCT id FROM unnest(ARRAY[
              CASE WHEN TG_OP <> 'INSERT' THEN OLD.listing_id END,
              CASE WHEN TG_OP <> 'DELETE' THEN NEW.listing_id END
            ]) AS parents(id) WHERE id IS NOT NULL ORDER BY id
          LOOP
            UPDATE {q}.listings SET id=id WHERE id=parent_id;
          END LOOP;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$''')
    op.execute(f'''CREATE OR REPLACE FUNCTION {q}.scrapmart_check_listing_images() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
        DECLARE parent_id uuid; parent_ids uuid[];
        BEGIN
          IF TG_TABLE_NAME='listings' THEN parent_ids:=ARRAY[NEW.id];
          ELSE parent_ids:=ARRAY[
            CASE WHEN TG_OP <> 'INSERT' THEN OLD.listing_id END,
            CASE WHEN TG_OP <> 'DELETE' THEN NEW.listing_id END];
          END IF;
          FOREACH parent_id IN ARRAY parent_ids LOOP
            IF EXISTS (SELECT 1 FROM {q}.listings WHERE id=parent_id AND status='active')
              AND NOT EXISTS (SELECT 1 FROM {q}.listing_images WHERE listing_id=parent_id)
            THEN RAISE EXCEPTION 'Active listings require at least one image'
              USING ERRCODE='23514', CONSTRAINT='ck_listings_active_has_image';
            END IF;
          END LOOP;
          RETURN NULL;
        END $$''')
    for function in ('guard_runtime_identifier', 'scrapmart_lock_image_listing', 'scrapmart_check_listing_images'):
        op.execute(f'REVOKE ALL ON FUNCTION {q}.{function}() FROM PUBLIC')


def downgrade():
    q = op.get_context().dialect.identifier_preparer.quote_schema(namespace())
    for table in ('buyer_profiles', 'categories', 'listings'):
        op.execute(f'DROP TRIGGER guard_runtime_identifier ON {q}.{table}')
    op.execute(f'DROP FUNCTION {q}.guard_runtime_identifier()')
    # Intentionally retain schema-qualified invoker photo functions and narrowed
    # EXECUTE ACLs. Downgrade must not reintroduce the search-path vulnerability.
