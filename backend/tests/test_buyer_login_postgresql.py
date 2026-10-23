"""Buyer login with actual Phase 1 guards in verified disposable schemas only."""
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.modules.auth.email_identity_models import EmailIdentityPolicyState as Policy, EmailIdentityReservation as Reservation
from app.modules.auth.login_policy import InvalidBuyerCredentials
from app.modules.auth.login_service import BuyerLoginService
from app.modules.auth.models import User
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionService
from app.modules.buyers.models import BuyerProfile
from tests import test_buyer_login as functional
from tests.buyer_login_postgresql_support import enabled, login_store, wait_for_blocker
from tests.test_buyer_login import encoded_password

pytestmark = pytest.mark.skipif(
    not enabled(), reason="Requires both isolated Buyer login PostgreSQL opt-ins",
)

ISOLATIONS = ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"]


def is_user_update(statement):
    return statement.startswith("UPDATE ") and ".users SET " in statement


@pytest.mark.parametrize("name,args", [
    ("test_valid_buyer_preserves_profiles_and_uses_stage2b", ()),
    ("test_legacy_ascii_casing", ()),
    *[("test_credential_rejections_indistinguishable", args) for args in [
        ("buyer@example.test", "wrong password"), ("unknown@example.test", functional.PASSWORD),
        ("inactive@example.test", functional.PASSWORD), ("missing@example.test", functional.PASSWORD),
        ("k@example.test", functional.PASSWORD), ("unicode@xn--bcher-kva.test", functional.PASSWORD),
        ("buyer@example.test", functional.PASSWORD.strip()),
    ]],
    *[("test_ineligible_uses_valid_dummy_argon2", (email,)) for email in (
        "unknown@example.test", "inactive@example.test", "missing@example.test", "k@example.test", "unicode@xn--bcher-kva.test",
    )],
    *[("test_registry_fails_closed", (state,)) for state in ("missing", "building", "version", "fingerprint", "libraries")],
    *[("test_admission_rechecks_after_verification", (change,)) for change in (
        "password", "inactive", "profile", "reservation", "registry", "fingerprint",
    )],
    *[("test_admission_retry_only_confirmed_aborts", (state,)) for state in ("40001", "40P01", "08006", None)],
    *[("test_uncertain_commit_never_retried", (persisted,)) for persisted in (False, True)],
    ("test_partial_session_write_rolls_back", ()),
    ("test_dummy_password_cannot_authenticate_unknown_account", ()),
    ("test_login_rejects_autocommit_for_all_accounts", ()),
    ("test_exhausted_admission_retries_roll_back", ()),
    *[("test_unusable_account_hash_runs_dummy_and_rejects", (encoded,)) for encoded in (
        "", "not-a-hash", "$2b$12$unsupported", "$argon2id$broken",
        "$argon2id$v=19$m=65536,t=3,p=1$bad$bad",
        functional._DUMMY_HASH.replace("m=65536", "m=0"),
        functional._DUMMY_HASH.replace("v=19", "v=999"),
        functional._DUMMY_HASH.rsplit("$", 1)[0],
        functional._DUMMY_HASH.rsplit("$", 1)[0] + "$***invalid-base64***",
        functional._DUMMY_HASH + "雪",
        functional._DUMMY_HASH.replace("v=19", "v=16").replace("m=65536", "m=0"),
    )],
    *[("test_supported_hashes_verify_once_without_dummy", (variant, version, correct))
      for variant in ("ID", "I", "D") for version in (16, 19) for correct in (True, False)],
])
def test_functional_postgresql(login_store, monkeypatch, caplog, name, args):
    function = getattr(functional, name)
    parameters = inspect.signature(function).parameters
    kwargs = dict(zip((name for name in parameters if name not in {"login_store", "monkeypatch", "caplog"}), args))
    if "monkeypatch" in parameters:
        kwargs["monkeypatch"] = monkeypatch
    if "caplog" in parameters:
        kwargs["caplog"] = caplog
    function(login_store, **kwargs)


def test_actual_phase1_guards_installed(login_store):
    with login_store.engine.connect() as db:
        triggers = db.execute(sa.text(
            "SELECT tgname FROM pg_catalog.pg_trigger WHERE tgrelid IN "
            "(CAST(:users AS regclass), CAST(:reservations AS regclass))"
        ), {"users": f"{login_store.schema}.users",
            "reservations": f"{login_store.schema}.email_identity_reservations"}).scalars().all()
        assert {"ct_users_email_reservation", "tr_users_email_immutable", "tr_email_reservation_immutable"} <= set(triggers)
    with pytest.raises(sa.exc.DBAPIError) as caught, login_store.engine.begin() as db:
        db.execute(sa.update(User).where(User.id == login_store.ids["buyer"]).values(email="changed@example.test"))
    assert caught.value.orig.sqlstate == "23514"


@pytest.mark.parametrize("isolation", ISOLATIONS)
@pytest.mark.parametrize("first", ["admission", "logout"])
def test_logout_all_serializes_with_admission(login_store, monkeypatch, isolation, first):
    engine = login_store.engine.execution_options(isolation_level=isolation)
    sessions = SessionService(engine, settings=login_store.settings)
    old = sessions.create_session(login_store.ids["buyer"])
    login = BuyerLoginService(engine, settings=login_store.settings)
    holding, waiting, release = threading.Event(), threading.Event(), threading.Event()
    pids = {}
    class ConcurrentSession(Session):
        pass
    monkeypatch.setattr("app.modules.auth.session_service.Session", ConcurrentSession)
    @sa.event.listens_for(ConcurrentSession, "before_commit")
    def hold(db):
        if threading.current_thread().name == "login-first":
            db.flush()
            pids["first"] = db.connection().exec_driver_sql("SELECT pg_catalog.pg_backend_pid()").scalar_one()
            holding.set()
            assert release.wait(10)
    def observe(connection, cursor, statement, parameters, context, many):
        if threading.current_thread().name == "login-second" and is_user_update(statement):
            pids["second"] = connection.exec_driver_sql("SELECT pg_catalog.pg_backend_pid()").scalar_one()
            waiting.set()
    def run(label, operation):
        threading.current_thread().name = label
        return operation()
    admission = lambda: login.login(functional.request())
    logout = lambda: sessions.revoke_all_sessions(login_store.ids["buyer"])
    sa.event.listen(login_store.engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            leading = pool.submit(run, "login-first", admission if first == "admission" else logout)
            try:
                assert holding.wait(10)
                trailing = pool.submit(run, "login-second", logout if first == "admission" else admission)
                assert waiting.wait(10)
                wait_for_blocker(engine, pids["second"], pids["first"])
            finally:
                release.set()
            first_result, second_result = leading.result(timeout=30), trailing.result(timeout=30)
    finally:
        release.set()
        sa.event.remove(login_store.engine, "before_cursor_execute", observe)
    admitted, revoked = (first_result, second_result) if first == "admission" else (second_result, first_result)
    assert revoked == (2 if first == "admission" else 1)
    assert functional.counts(login_store)[2:] == [2, 2]
    with Session(engine) as db:
        assert db.get(AuthSession, old.session_id).revoked_at is not None
        assert (db.get(AuthSession, admitted.session_id).revoked_at is not None) == (first == "admission")


def change_account(db, store, change):
    if change in {"password", "deactivation"}:
        values = {"password_hash": "new credential"} if change == "password" else {"is_active": False}
        db.execute(sa.update(User).where(User.id == store.ids["buyer"]).values(**values))
    elif change == "profile_delete":
        db.execute(sa.delete(BuyerProfile).where(BuyerProfile.user_id == store.ids["buyer"]))
    else:
        assert change == "profile_reassign"
        # The existing 'missing' User has no BuyerProfile.
        db.execute(sa.update(BuyerProfile).where(BuyerProfile.user_id == store.ids["buyer"]).values(user_id=store.ids["missing"]))


@pytest.mark.parametrize("isolation", ISOLATIONS)
@pytest.mark.parametrize("change", ["password", "deactivation", "profile_delete", "profile_reassign"])
@pytest.mark.parametrize("entry", ["admission", "login"])
def test_concurrent_change_rejects_admission(login_store, monkeypatch, isolation, change, entry):
    from app.modules.auth.session_service import SessionAuthenticationError
    engine = login_store.engine.execution_options(isolation_level=isolation)
    service = SessionService(engine, settings=login_store.settings)
    login = BuyerLoginService(engine, settings=login_store.settings)
    waiting, verified = threading.Event(), threading.Event()
    backend_pids, attempts = [], []
    original_verify = functional.verify_password
    def verify(*args, **kwargs):
        result = original_verify(*args, **kwargs)
        if result:
            verified.set()
        return result
    monkeypatch.setattr("app.modules.auth.login_service.verify_password", verify)
    def observe(connection, cursor, statement, parameters, context, many):
        if threading.current_thread().name != "identity-admission":
            return
        if is_user_update(statement):
            attempts.append(connection)
        relevant = is_user_update(statement) if change in {"password", "deactivation"} else (
            "buyer_profiles" in statement and "FOR SHARE" in statement
        )
        if relevant:
            backend_pids.append(connection.exec_driver_sql("SELECT pg_catalog.pg_backend_pid()").scalar_one())
            waiting.set()
    def admit():
        threading.current_thread().name = "identity-admission"
        if entry == "login":
            return login.login(functional.request())
        assert verify(functional.PASSWORD, login_store.encoded_password)
        return service.admit_buyer_session(login_store.ids["buyer"], "buyer@example.test", login_store.encoded_password)
    sa.event.listen(login_store.engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            # The writer holds the relevant row before admission starts. Initial
            # credential lookup sees its old committed version under MVCC.
            with login_store.engine.begin() as db:
                change_account(db, login_store, change)
                blocker = db.exec_driver_sql("SELECT pg_catalog.pg_backend_pid()").scalar_one()
                future = pool.submit(admit)
                assert waiting.wait(10) and verified.is_set()
                wait_for_blocker(engine, backend_pids[0], blocker)
            error = InvalidBuyerCredentials if entry == "login" else SessionAuthenticationError
            with pytest.raises(error) as caught:
                future.result(timeout=30)
            assert str(caught.value) == ("Invalid email or password" if entry == "login" else "Authentication session is invalid")
    finally:
        sa.event.remove(login_store.engine, "before_cursor_execute", observe)
    assert len(attempts) == (1 if isolation == "READ COMMITTED" else 2)
    with Session(login_store.engine) as db:
        user = db.get(User, login_store.ids["buyer"])
        if change == "deactivation":
            assert user.is_active is False
        elif change == "password":
            assert user.password_hash == "new credential"
        else:
            assert db.scalar(sa.select(BuyerProfile.id).where(BuyerProfile.user_id == user.id)) is None
            if change == "profile_reassign":
                assert db.scalar(sa.select(BuyerProfile.id).where(BuyerProfile.user_id == login_store.ids["missing"])) is not None
    assert functional.counts(login_store)[2:] == [0, 0]


@pytest.mark.parametrize("isolation", ISOLATIONS)
@pytest.mark.parametrize("change", ["profile_delete", "profile_reassign"])
def test_admission_precedes_profile_change(login_store, monkeypatch, isolation, change):
    engine = login_store.engine.execution_options(isolation_level=isolation)
    login = BuyerLoginService(engine, settings=login_store.settings)
    holding, waiting, release = threading.Event(), threading.Event(), threading.Event()
    pids = {}
    class HeldSession(Session):
        pass
    monkeypatch.setattr("app.modules.auth.session_service.Session", HeldSession)
    @sa.event.listens_for(HeldSession, "before_commit")
    def hold(db):
        db.flush()
        pids["admission"] = db.connection().exec_driver_sql("SELECT pg_catalog.pg_backend_pid()").scalar_one()
        holding.set()
        assert release.wait(10)
    def observe(connection, cursor, statement, parameters, context, many):
        if threading.current_thread().name == "profile-writer" and "buyer_profiles" in statement:
            pids["writer"] = connection.exec_driver_sql("SELECT pg_catalog.pg_backend_pid()").scalar_one()
            waiting.set()
    def mutate():
        threading.current_thread().name = "profile-writer"
        with login_store.engine.begin() as db:
            change_account(db, login_store, change)
    sa.event.listen(login_store.engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            admission = pool.submit(login.login, functional.request())
            try:
                assert holding.wait(10)
                mutation = pool.submit(mutate)
                assert waiting.wait(10)
                wait_for_blocker(engine, pids["writer"], pids["admission"])
            finally:
                release.set()
            credentials = admission.result(timeout=30)
            mutation.result(timeout=30)
    finally:
        release.set()
        sa.event.remove(login_store.engine, "before_cursor_execute", observe)
    # A subsequent profile change is permitted; this is not session revocation.
    assert functional.counts(login_store)[2:] == [1, 1]
    with Session(engine) as db:
        assert db.get(AuthSession, credentials.session_id).user_id == login_store.ids["buyer"]
        assert db.scalar(sa.select(BuyerProfile.id).where(BuyerProfile.user_id == login_store.ids["buyer"])) is None
    with pytest.raises(InvalidBuyerCredentials, match="^Invalid email or password$"):
        login.login(functional.request())
    assert functional.counts(login_store)[2:] == [1, 1]


@pytest.mark.parametrize("resource", ["policy", "reservation", "user", "profile"])
def test_admission_locks_survive_until_commit(login_store, resource):
    observations = []
    def before_insert(mapper, connection, target):
        def compete():
            with pytest.raises(sa.exc.DBAPIError) as caught, login_store.engine.begin() as db:
                db.exec_driver_sql("SET LOCAL lock_timeout='100ms'")
                if resource == "policy":
                    db.execute(sa.update(Policy).values(status="building"))
                elif resource == "reservation":
                    db.execute(sa.update(Reservation).where(Reservation.lookup_key == "buyer@example.test").values(state="blocked", user_id=None))
                elif resource == "user":
                    db.execute(sa.update(User).where(User.id == login_store.ids["buyer"]).values(password_hash="changed"))
                else:
                    db.execute(sa.delete(BuyerProfile).where(BuyerProfile.user_id == login_store.ids["buyer"]))
            observations.append(caught.value.orig.sqlstate)
        with ThreadPoolExecutor() as pool:
            pool.submit(compete).result(timeout=10)
    sa.event.listen(RefreshToken, "before_insert", before_insert)
    try:
        login_store.service.login(functional.request())
    finally:
        sa.event.remove(RefreshToken, "before_insert", before_insert)
    assert observations == ["55P03"]


def test_lock_order_and_indexed_reservation_lookup(login_store):
    statements = []
    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    sa.event.listen(login_store.engine, "before_cursor_execute", observe)
    try:
        login_store.service.login(functional.request())
    finally:
        sa.event.remove(login_store.engine, "before_cursor_execute", observe)
    policy = max(i for i, sql in enumerate(statements) if "email_identity_policy_state" in sql and "FOR SHARE" in sql)
    reservation = next(i for i, sql in enumerate(statements) if "email_identity_reservations" in sql and "FOR SHARE" in sql)
    user = next(i for i, sql in enumerate(statements) if is_user_update(sql))
    buyer = next(i for i, sql in enumerate(statements) if "buyer_profiles" in sql and "FOR SHARE" in sql)
    session = next(i for i, sql in enumerate(statements) if sql.startswith("INSERT INTO ") and ".auth_sessions " in sql)
    token = next(i for i, sql in enumerate(statements) if sql.startswith("INSERT INTO ") and ".refresh_tokens " in sql)
    assert policy < reservation < user < buyer < session < token
    with login_store.engine.begin() as db:
        db.exec_driver_sql("SET LOCAL enable_seqscan=off")
        plan = db.exec_driver_sql(f"EXPLAIN SELECT id FROM {login_store.schema}.email_identity_reservations WHERE lookup_key='buyer@example.test'").all()
    assert "uq_eir_lookup_key" in str(plan)
