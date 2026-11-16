"""Add fail-closed email identity registry and PostgreSQL writer guards.

Revision ID: c42f7d18a903
Revises: b81d4f2a9c06

No User data is changed and no registry readiness is activated. Deployment must
use a restricted non-owner runtime role; see README before applying this revision.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c42f7d18a903"
down_revision = "b81d4f2a9c06"
branch_labels = None
depends_on = None

STATE_ID = "00000000-0000-0000-0000-000000000001"


def namespace():
    # Explicit schema option permits isolated local validation. Production is
    # public; never resolve security objects using the runtime search_path.
    schema = op.get_context().opts.get("version_table_schema") or "public"
    return schema, postgresql.dialect().identifier_preparer.quote_schema(schema)


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        raise RuntimeError("Email identity writer guards require PostgreSQL")
    schema, q = namespace()
    op.create_table(
        "email_identity_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lookup_key", sa.String(255, collation="C"), nullable=False),
        sa.Column("state", sa.String(7), nullable=False, server_default="owned"),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("policy_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], [f"{schema}.users.id"], name="fk_eir_user",
                                ondelete="NO ACTION", onupdate="NO ACTION", deferrable=True, initially="DEFERRED"),
        sa.UniqueConstraint("lookup_key", name="uq_eir_lookup_key"),
        sa.CheckConstraint("policy_version = 1", name="ck_eir_policy_version"),
        sa.CheckConstraint("(state = 'owned' AND user_id IS NOT NULL) OR (state = 'blocked' AND user_id IS NULL)", name="ck_eir_ownership"),
        sa.CheckConstraint(
            "char_length(lookup_key) BETWEEN 3 AND 255 AND lookup_key COLLATE \"C\" ~ '^[!-~]+$' "
            "AND lookup_key = translate(lookup_key, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') "
            "AND char_length(lookup_key) - char_length(replace(lookup_key, '@', '')) = 1 "
            "AND position('@' in lookup_key) > 1 AND position('@' in lookup_key) < char_length(lookup_key)", name="ck_eir_ascii_key"),
        schema=schema,
    )
    op.create_index("ix_eir_user_id", "email_identity_reservations", ["user_id"], schema=schema)
    op.create_table(
        "email_identity_policy_state",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("policy_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(8), nullable=False, server_default="building"),
        sa.Column("last_user_id", sa.Uuid(), nullable=True),
        sa.Column("users_processed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("manifest_sha256", sa.LargeBinary(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"id = '{STATE_ID}'", name="ck_eips_singleton"),
        sa.CheckConstraint("policy_version = 1", name="ck_eips_policy_version"),
        sa.CheckConstraint("status IN ('building', 'ready')", name="ck_eips_status"),
        sa.CheckConstraint("users_processed >= 0 AND source_count >= 0", name="ck_eips_counts"),
        sa.CheckConstraint("manifest_sha256 IS NULL OR length(manifest_sha256) = 32", name="ck_eips_manifest"),
        sa.CheckConstraint("status <> 'ready' OR (users_processed = source_count AND manifest_sha256 IS NOT NULL)", name="ck_eips_ready"),
        schema=schema,
    )
    op.execute(f"INSERT INTO {q}.email_identity_policy_state(id) VALUES ('{STATE_ID}')")
    op.execute(f"""
CREATE FUNCTION {q}.verify_user_email_reservation() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path = pg_catalog AS $$
DECLARE registry_status text; registry_version smallint;
BEGIN
    SELECT status, policy_version INTO registry_status, registry_version
      FROM {q}.email_identity_policy_state WHERE id = '{STATE_ID}' FOR SHARE;
    IF NOT FOUND OR registry_status IS DISTINCT FROM 'ready' OR registry_version IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'Registration is unavailable';
    END IF;
    IF NEW.email COLLATE "C" !~ '^[!-~]+$' OR
       NEW.email IS DISTINCT FROM translate(NEW.email, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Email reservation requirement failed';
    END IF;
    PERFORM 1 FROM {q}.email_identity_reservations
      WHERE lookup_key = NEW.email COLLATE "C" AND state = 'owned'
        AND user_id = NEW.id AND policy_version = 1 FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Email reservation requirement failed';
    END IF;
    RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER ct_users_email_reservation AFTER INSERT ON {q}.users
    NOT DEFERRABLE FOR EACH ROW EXECUTE FUNCTION {q}.verify_user_email_reservation();
CREATE FUNCTION {q}.reject_user_email_change() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Email identity changes are unavailable';
END $$;
CREATE TRIGGER tr_users_email_immutable AFTER UPDATE ON {q}.users
    FOR EACH ROW WHEN (OLD.email COLLATE "C" IS DISTINCT FROM NEW.email COLLATE "C")
    EXECUTE FUNCTION {q}.reject_user_email_change();
CREATE FUNCTION {q}.guard_email_reservation_update() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF OLD.id IS DISTINCT FROM NEW.id OR OLD.lookup_key IS DISTINCT FROM NEW.lookup_key
       OR OLD.policy_version IS DISTINCT FROM NEW.policy_version
       OR OLD.created_at IS DISTINCT FROM NEW.created_at
       OR (OLD.state = 'blocked' AND (NEW.state <> 'blocked' OR NEW.user_id IS NOT NULL))
       OR (OLD.state = 'owned' AND NEW.state = 'owned' AND OLD.user_id IS DISTINCT FROM NEW.user_id) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Email reservation transition is unavailable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER tr_email_reservation_immutable AFTER UPDATE ON {q}.email_identity_reservations
    FOR EACH ROW EXECUTE FUNCTION {q}.guard_email_reservation_update();
""")
    # No runtime roles are invented here. Owner/superuser privileges cannot be
    # removed with REVOKE. Restricted-role grants are a deployment prerequisite.
    for name in ("verify_user_email_reservation", "reject_user_email_change", "guard_email_reservation_update"):
        op.execute(f"REVOKE ALL ON FUNCTION {q}.{name}() FROM PUBLIC")
    for table in ("email_identity_policy_state", "email_identity_reservations"):
        op.execute(f"REVOKE ALL ON TABLE {q}.{table} FROM PUBLIC")


def downgrade():
    schema, q = namespace()
    op.execute(f"DROP TRIGGER ct_users_email_reservation ON {q}.users")
    op.execute(f"DROP TRIGGER tr_users_email_immutable ON {q}.users")
    op.execute(f"DROP TRIGGER tr_email_reservation_immutable ON {q}.email_identity_reservations")
    for name in ("verify_user_email_reservation", "reject_user_email_change", "guard_email_reservation_update"):
        op.execute(f"DROP FUNCTION {q}.{name}()")
    op.drop_table("email_identity_policy_state", schema=schema)
    op.drop_index("ix_eir_user_id", table_name="email_identity_reservations", schema=schema)
    op.drop_table("email_identity_reservations", schema=schema)
