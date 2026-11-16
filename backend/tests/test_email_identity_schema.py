"""Offline schema contract; writer guarantees require the PostgreSQL migration."""
import importlib.util
import io
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from app.modules.auth.email_identity_models import EmailIdentityPolicyState, EmailIdentityReservation

REVISION = "c42f7d18a903"


def migration():
    path = Path(__file__).parents[1] / f"alembic/versions/{REVISION}_add_email_identity_reservations.py"
    spec = importlib.util.spec_from_file_location("email_identity_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reservation_model_contract():
    table = EmailIdentityReservation.__table__
    foreign_key = next(iter(table.foreign_key_constraints))
    assert foreign_key.deferrable and foreign_key.initially == "DEFERRED"
    assert foreign_key.ondelete == foreign_key.onupdate == "NO ACTION"
    assert table.c.id.default is not None
    assert table.c.lookup_key.type.collation == "C"
    assert {i.name for i in table.indexes} == {"ix_eir_user_id"}
    assert any(isinstance(c, sa.UniqueConstraint) and c.name == "uq_eir_lookup_key" for c in table.constraints)
    for model in (EmailIdentityReservation, EmailIdentityPolicyState):
        ddl = str(sa.schema.CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert EmailIdentityPolicyState.__table__.c.status.server_default.arg == "building"


def test_migration_sql_fail_closed_and_reversible():
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration().upgrade()
        migration().downgrade()
    sql = output.getvalue()
    assert migration().down_revision == "b81d4f2a9c06"
    for fragment in ("DEFERRABLE INITIALLY DEFERRED", "NOT DEFERRABLE FOR EACH ROW", "VOLATILE SECURITY INVOKER", "FOR SHARE", "SET search_path = pg_catalog", "REVOKE ALL", "DROP TRIGGER", "DROP FUNCTION"):
        assert fragment in sql
    assert "DEFAULT 'building'" in sql
    assert "UPDATE public.users" not in sql
    assert "CREATE ROLE" not in sql
    assert "VALUES ('00000000-0000-0000-0000-000000000001')" in sql
