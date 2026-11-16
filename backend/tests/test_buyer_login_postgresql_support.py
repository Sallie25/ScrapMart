"""Offline checks of the integration fixture's fail-closed entry boundary."""
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.modules.auth.models import User
from tests import buyer_login_postgresql_support as support


@pytest.mark.parametrize("general,buyer", [(None, None), ("1", None), (None, "1"), ("0", "1"), ("1", "0")])
def test_fixture_requires_both_opt_ins_before_any_external_access(monkeypatch, general, buyer):
    for flag, value in (("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS", general),
                        ("SCRAPMART_RUN_BUYER_LOGIN_POSTGRES_TESTS", buyer)):
        if value is None:
            monkeypatch.delenv(flag, raising=False)
        else:
            monkeypatch.setenv(flag, value)
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled fixture attempted external access")
    monkeypatch.setattr(support.subprocess, "run", forbidden)
    monkeypatch.setattr(support.sa, "create_engine", forbidden)
    with pytest.raises(pytest.skip.Exception):
        next(support.login_store.__wrapped__("unused"))


@pytest.mark.parametrize("field,value", [
    (0, "/other-container"), (1, "postgres:17-alpine"),
    (2, {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "55432"}]}),
    (2, {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5432"}]}),
    (4, False),
])
def test_fixture_rejects_container_mismatch_before_database_access(monkeypatch, field, value):
    monkeypatch.setenv("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS", "1")
    monkeypatch.setenv("SCRAPMART_RUN_BUYER_LOGIN_POSTGRES_TESTS", "1")
    identity = ["/scrapmart-postgres-test", "postgres:16-alpine",
                {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]},
                {"bridge": {"IPAddress": "172.17.0.2"}}, True]
    identity[field] = value
    monkeypatch.setattr(support.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="\n".join(json.dumps(part) for part in identity)))
    def forbidden(*args, **kwargs):
        pytest.fail("Unverified container reached database setup")
    monkeypatch.setattr(support.sa, "create_engine", forbidden)
    with pytest.raises(support.FixtureSafetyError):
        next(support.login_store.__wrapped__("unused"))


@pytest.mark.parametrize("name", ["public", "buyer_login_", "buyer_login_" + "a" * 31,
                                  "buyer_login_" + "a" * 32 + ";DROP SCHEMA x"])
def test_private_schema_identifier_validation(name):
    with pytest.raises(ValueError):
        support.private_name(name)


def test_orm_schema_translation_explicitly_qualifies_private_table():
    schema = support.private_name("buyer_login_" + "a" * 32)
    compiled = sa.select(User.id).compile(dialect=postgresql.dialect(),
                                         schema_translate_map={None: schema}, render_schema_translate=True)
    assert f"FROM {schema}.users" in str(compiled)


def test_optimized_python_rejected_before_external_access(monkeypatch):
    monkeypatch.setenv("SCRAPMART_RUN_LOCAL_POSTGRES_TESTS", "1")
    monkeypatch.setenv("SCRAPMART_RUN_BUYER_LOGIN_POSTGRES_TESTS", "1")
    monkeypatch.setattr(support.sys, "flags", SimpleNamespace(optimize=1))
    def forbidden(*args, **kwargs):
        pytest.fail("Optimized execution reached external access")
    monkeypatch.setattr(support.subprocess, "run", forbidden)
    with pytest.raises(support.FixtureSafetyError, match="Optimized"):
        next(support.login_store.__wrapped__("unused"))


SCHEMA = "buyer_login_" + "a" * 32
MARKER = "b" * 32


class CatalogConnection:
    def __init__(self):
        self.ddl = []
        self.ownership = (10, 20, MARKER)
        self.tables = [("users", 30, 20, "r")]
        self.functions = []
        self.events = False
        self.dependency_error = False

    def execute(self, sql, parameters=None):
        sql = str(sql)
        if "obj_description" in sql:
            return SimpleNamespace(one_or_none=lambda: self.ownership)
        if "SELECT oid,nspowner" in sql:
            return SimpleNamespace(one=lambda: self.ownership[:2])
        if "pg_class c" in sql:
            return SimpleNamespace(all=lambda: self.tables)
        if "pg_proc p" in sql:
            return SimpleNamespace(all=lambda: self.functions)
        pytest.fail(f"Unexpected catalog query: {sql}")

    def scalar(self, sql, parameters=None):
        return self.events if "pg_event_trigger" in str(sql) else 0

    def exec_driver_sql(self, sql):
        self.ddl.append(sql)
        if self.dependency_error and sql.startswith("DROP TABLE"):
            raise RuntimeError("external dependent object")


def test_cleanup_uses_only_private_restrictive_drops():
    db = CatalogConnection()
    support.cleanup(db, SCHEMA, (10, 20), MARKER, support.inventory(db, SCHEMA))
    assert db.ddl == [f"DROP TABLE {SCHEMA}.users RESTRICT", f"DROP SCHEMA {SCHEMA} RESTRICT"]


@pytest.mark.parametrize("mismatch", ["owner", "oid", "marker", "table", "function", "index", "event"])
def test_cleanup_refuses_changed_resources_before_any_drop(mismatch):
    db = CatalogConnection()
    expected = support.inventory(db, SCHEMA)
    if mismatch == "owner":
        db.ownership = (10, 21, MARKER)
    elif mismatch == "oid":
        db.ownership = (11, 20, MARKER)
    elif mismatch == "marker":
        db.ownership = (10, 20, "different")
    elif mismatch == "table":
        db.tables.append(("unrelated", 31, 20, "r"))
    elif mismatch == "function":
        db.functions.append(("unrelated", 31, 20, 0))
    elif mismatch == "index":
        db.tables.append(("unexpected_index", 31, 20, "i"))
    else:
        db.events = True
    with pytest.raises(support.FixtureSafetyError):
        support.cleanup(db, SCHEMA, (10, 20), MARKER, expected)
    assert db.ddl == []


def test_cleanup_does_not_retry_or_cascade_on_dependency_failure():
    db = CatalogConnection()
    db.dependency_error = True
    with pytest.raises(RuntimeError, match="dependent"):
        support.cleanup(db, SCHEMA, (10, 20), MARKER, support.inventory(db, SCHEMA))
    assert db.ddl == [f"DROP TABLE {SCHEMA}.users RESTRICT"]


def test_uncertain_schema_creation_reports_name_without_cleanup():
    db = CatalogConnection()
    class UncertainAdmin:
        @contextmanager
        def begin(self):
            yield db
            raise OSError("commit confirmation lost")
    with pytest.raises(support.FixtureSafetyError, match=SCHEMA):
        support.create_private_schema(UncertainAdmin(), SCHEMA, MARKER)
    assert len(db.ddl) == 2
    assert not any("DROP" in sql for sql in db.ddl)


def test_registry_installer_preserves_private_guards_without_acl_changes(monkeypatch):
    from alembic.migration import MigrationContext
    import io
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={
        "as_sql": True, "output_buffer": output, "version_table_schema": SCHEMA,
    })
    monkeypatch.setattr(support.MigrationContext, "configure", lambda *a, **k: context)
    support.install_registry(SimpleNamespace(dialect=postgresql.dialect()), SCHEMA)
    sql = output.getvalue()
    assert "GRANT" not in sql and "REVOKE" not in sql
    assert "public." not in sql
    assert f"CREATE TABLE {SCHEMA}.email_identity_reservations" in sql
    assert f"CREATE FUNCTION {SCHEMA}.verify_user_email_reservation()" in sql
    assert f"AFTER INSERT ON {SCHEMA}.users" in sql
    assert "SET search_path = pg_catalog" in sql
