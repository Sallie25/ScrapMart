"""Future opt-in Buyer login integration setup; never inspect public relations.

Enabling BOTH flags authorizes private schema DDL and the real registry migration
for a separately approved run. Importing/collecting this module does neither.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.modules.auth.models import User
from tests import test_buyer_login as functional
from tests.test_email_identity_schema import migration


class FixtureSafetyError(RuntimeError):
    """Fail closed without exposing connection credentials."""


def require(condition, message):
    if not condition:
        raise FixtureSafetyError(message)


def enabled():
    return all(os.environ.get(flag) == "1" for flag in (
        "SCRAPMART_RUN_LOCAL_POSTGRES_TESTS",
        "SCRAPMART_RUN_BUYER_LOGIN_POSTGRES_TESTS",
    ))


def private_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"buyer_login_[0-9a-f]{32}", name):
        raise ValueError("Invalid disposable schema name")
    return name


TABLE_ORDER = ("refresh_tokens", "auth_sessions", "buyer_profiles",
               "email_identity_reservations", "email_identity_policy_state", "users")
FUNCTIONS = ("verify_user_email_reservation", "reject_user_email_change", "guard_email_reservation_update")


def no_event_triggers(db):
    require(not db.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_event_trigger WHERE evtenabled <> 'D')"
    )), "Enabled database event triggers: refusing fixture DDL")


def inventory(db, schema):
    """Only explicitly private table/function identities; never public metadata."""
    schema = private_name(schema)
    tables = db.execute(sa.text(
        "SELECT c.relname,c.oid,c.relowner,c.relkind FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=:schema AND c.relkind <> 't'"
    ), {"schema": schema}).all()
    functions = db.execute(sa.text(
        "SELECT p.proname,p.oid,p.proowner,p.pronargs FROM pg_catalog.pg_proc p "
        "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema"
    ), {"schema": schema}).all()
    require(all((row[0] in TABLE_ORDER and row[3] == 'r') or row[3] == 'i' for row in tables),
            f"Unexpected relation in {schema}; refusing cleanup")
    require(all(row[0] in FUNCTIONS and row[3] == 0 for row in functions),
            f"Unexpected function in {schema}; refusing cleanup")
    return {("table" if row[3] == "r" else "index", row[0]): tuple(row[1:]) for row in tables} | {
        ("function", row[0]): tuple(row[1:]) for row in functions}


def cleanup(db, schema, owned, marker, objects):
    schema = private_name(schema)
    no_event_triggers(db)
    actual = db.execute(sa.text(
        "SELECT oid,nspowner,pg_catalog.obj_description(oid,'pg_namespace') "
        "FROM pg_catalog.pg_namespace WHERE nspname=:schema"
    ), {"schema": schema}).one_or_none()
    require(actual is not None and tuple(actual) == (*owned, marker),
            f"Ownership changed for {schema}; refusing cleanup")
    require(inventory(db, schema) == objects,
            f"Object inventory changed for {schema}; refusing cleanup")
    # RESTRICT prevents removal of external dependent objects. The entire
    # cleanup is one transaction, so unexpected dependencies roll it all back.
    for table in TABLE_ORDER:
        if ("table", table) in objects:
            db.exec_driver_sql(f"DROP TABLE {schema}.{table} RESTRICT")
    for function in FUNCTIONS:
        if ("function", function) in objects:
            db.exec_driver_sql(f"DROP FUNCTION {schema}.{function}() RESTRICT")
    db.exec_driver_sql(f"DROP SCHEMA {schema} RESTRICT")
    require(not db.scalar(sa.text(
        "SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname=:schema"
    ), {"schema": schema}), f"Disposable schema remains: {schema}")


def create_private_schema(admin, schema, marker):
    schema = private_name(schema)
    require(bool(re.fullmatch(r"[0-9a-f]{32}", marker)), "Invalid schema ownership marker")
    try:
        with admin.begin() as db:
            db.exec_driver_sql(f"CREATE SCHEMA {schema}")
            db.exec_driver_sql(f"COMMENT ON SCHEMA {schema} IS '{marker}'")
            owned = db.execute(sa.text(
                "SELECT oid,nspowner FROM pg_catalog.pg_namespace WHERE nspname=:schema"
            ), {"schema": schema}).one()
        return owned
    except BaseException as error:
        raise FixtureSafetyError(
            f"Creation not confirmed for {schema}; no automatic cleanup; reconcile manually"
        ) from error


def install_registry(db, schema):
    """Install actual migration guards/constraints without executing ACL changes.

    Runtime grants are outside this owner-backed fixture's permission contract.
    The migration's known ACL revocations on new objects are deliberately omitted
    to honor the no-privilege-changes boundary. All other migration SQL is intact.
    """
    schema = private_name(schema)
    context = MigrationContext.configure(db, opts={"version_table_schema": schema})
    operations = Operations(context)
    quoted = db.dialect.identifier_preparer.quote_schema(schema)
    omitted = {f"REVOKE ALL ON FUNCTION {quoted}.{name}() FROM PUBLIC" for name in FUNCTIONS}
    omitted |= {f"REVOKE ALL ON TABLE {quoted}.{name} FROM PUBLIC" for name in (
        "email_identity_policy_state", "email_identity_reservations")}
    class PrivateOperations:
        def __getattr__(self, name):
            return getattr(operations, name)

        def execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql in omitted:
                return
            require(not re.search(r"\b(GRANT|REVOKE)\b", str(sql), re.I),
                    "Unexpected privilege statement in registry installation")
            return operations.execute(sql, *args, **kwargs)
    module = migration()
    module.op = PrivateOperations()
    module.upgrade()


def wait_for_blocker(engine, waiter_pid, blocker_pid, timeout=5):
    """Poll an actual blocker relationship; elapsed time never proves locking."""
    deadline = time.monotonic() + timeout
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        while time.monotonic() < deadline:
            blocked = db.scalar(sa.text(
                "SELECT :blocker = ANY(pg_catalog.pg_blocking_pids(:waiter))"
            ), {"blocker": blocker_pid, "waiter": waiter_pid})
            if blocked:
                return
            # This only bounds polling load; correctness uses pg_blocking_pids.
            time.sleep(0.01)
    raise AssertionError("Expected database lock wait was not observed")


@pytest.fixture
def login_store(encoded_password):
    if not enabled():
        pytest.skip("Requires both local PostgreSQL and Buyer login DDL opt-ins")
    require(sys.flags.optimize == 0, "Optimized Python is prohibited for fixture execution")
    inspected = subprocess.run([
        "docker", "inspect", "scrapmart-postgres-test", "--format",
        '{{json .Name}}\n{{json .Config.Image}}\n{{json .NetworkSettings.Ports}}\n{{json .NetworkSettings.Networks}}\n{{json .State.Running}}',
    ], capture_output=True, text=True, check=True, timeout=10)
    name, image, ports, networks, running = map(json.loads, inspected.stdout.splitlines())
    require(name == "/scrapmart-postgres-test" and image == "postgres:16-alpine" and running is True,
            "Disposable container identity mismatch")
    require(ports == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]},
            "Disposable container must use the approved loopback port")
    addresses = {network["IPAddress"] for network in networks.values()}
    url = sa.URL.create("postgresql+psycopg", username="scrapmart_test",
                        password="local_test_only", host="127.0.0.1", port=55432,
                        database="scrapmart_test")
    options = "-c statement_timeout=15000 -c lock_timeout=8000 -c idle_in_transaction_session_timeout=30000"
    admin = sa.create_engine(url, hide_parameters=True, connect_args={
        "connect_timeout": 5, "options": options + " -c search_path=pg_catalog",
    })
    schema, marker = private_name("buyer_login_" + uuid.uuid4().hex), uuid.uuid4().hex
    created, engine, objects = False, None, {}
    try:
        with admin.connect() as db:
            identity = db.execute(sa.text(
                "SELECT current_database(),current_user,pg_catalog.current_setting('server_version_num')::int,"
                "pg_catalog.host(pg_catalog.inet_server_addr()),pg_catalog.inet_server_port(),"
                "pg_catalog.pg_is_in_recovery()"
            )).one()
            require(identity[0] == identity[1] == "scrapmart_test", "Database/user identity mismatch")
            require(160000 <= identity[2] < 170000, "PostgreSQL version mismatch")
            require(identity[3] in addresses and identity[4] == 5432 and not identity[5],
                    "Database server identity mismatch")
            require(set(db.execute(sa.text("SELECT datname FROM pg_catalog.pg_database")).scalars()) == {
                "postgres", "template0", "template1", "scrapmart_test",
            }, "Unexpected databases in disposable cluster")
            # Namespace names only, never table metadata or data from public.
            require(not db.execute(sa.text(
                "SELECT nspname FROM pg_catalog.pg_namespace "
                "WHERE nspname NOT IN ('public','information_schema') AND nspname !~ '^pg_'"
            )).first(), "Unexpected existing schemas: stop before writes")
            no_event_triggers(db)
        owned = create_private_schema(admin, schema, marker)
        created = True  # Only after confirmed commit.
        engine = sa.create_engine(url, hide_parameters=True, execution_options={
            "schema_translate_map": {None: schema},
        }, connect_args={"connect_timeout": 5,
                         "options": options + f" -c search_path={schema},pg_catalog"})
        with engine.begin() as db:
            User.metadata.create_all(db, tables=functional.TABLES)
            pending = inventory(db, schema)
        objects = pending
        identifiers = functional.seed_users(engine, encoded_password)
        with engine.begin() as db:
            install_registry(db, schema)
            pending = inventory(db, schema)
        objects = pending
        functional.seed_registry(engine, identifiers)
        store = functional.make_store(engine, identifiers, encoded_password)
        store.schema = schema
        yield store
    finally:
        if engine is not None:
            engine.dispose()
        try:
            if created:
                try:
                    with admin.begin() as db:
                        cleanup(db, schema, owned, marker, objects)
                except BaseException as error:
                    raise FixtureSafetyError(
                        f"Cleanup not confirmed for {schema}; reconcile manually; no broader cleanup attempted"
                    ) from error
        finally:
            admin.dispose()
