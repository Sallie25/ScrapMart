"""Offline Buyer login/admission contracts; PostgreSQL reuses these checks."""
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.email_identity_models import EmailIdentityPolicyState as Policy, EmailIdentityReservation as Reservation, POLICY_STATE_ID
from app.modules.auth.email_identity_policy import legacy_email_identity
from app.modules.auth.login_policy import BuyerLoginUnavailableError, InvalidBuyerCredentials
from app.modules.auth.login_schemas import BuyerLoginRequest
from app.modules.auth.login_service import BuyerLoginService, _DUMMY_HASH
from app.modules.auth.models import User
from app.modules.auth.security import digest_refresh_token, verify_password
from app.modules.auth import security
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import SessionService
from app.modules.buyers.models import BuyerProfile

PASSWORD = "  legacy 雪  "  # Accepted by the existing verifier, below signup minimum.
TABLES = [User.__table__, BuyerProfile.__table__, AuthSession.__table__, RefreshToken.__table__]
EMAILS = {
    "buyer": "buyer@example.test", "inactive": "inactive@example.test",
    "missing": "missing@example.test", "legacy": "LEGACY@Example.Test",
    "unicode": "unicode@bücher.test", "blocked": "K@example.test",
}


@pytest.fixture(scope="session")
def encoded_password():
    return PasswordHash((Argon2Hasher(parallelism=1),)).hash(PASSWORD)


def seed_users(engine, encoded_password):
    identifiers = {name: uuid.uuid4() for name in EMAILS}
    with Session(engine) as db, db.begin():
        for name, email in EMAILS.items():
            # A vendor-role identity with a BuyerProfile must be allowed.
            db.add(User(id=identifiers[name], email=email, full_name="Existing user",
                        password_hash=encoded_password, role="buyer" if name == "missing" else "vendor", is_active=name != "inactive"))
        db.flush()
        now = db.scalar(sa.select(sa.func.current_timestamp()))
        for name, identifier in identifiers.items():
            if name != "missing":
                db.add(BuyerProfile(user_id=identifier, created_at=now, signup_completed_at=now))
    return identifiers


def seed_registry(engine, identifiers):
    with Session(engine) as db, db.begin():
        state = db.get(Policy, POLICY_STATE_ID)
        if state is None:
            state = Policy(id=POLICY_STATE_ID)
            db.add(state)
        state.status, state.manifest_sha256 = "ready", bytes(32)
        for name, email in EMAILS.items():
            for alias in legacy_email_identity(email).aliases:
                db.add(Reservation(lookup_key=alias.key, state=alias.disposition.value,
                                   user_id=identifiers[name] if alias.disposition.value == "owned" else None))


def make_store(engine, identifiers, encoded_password):
    settings = Settings(_env_file=None, _secrets_dir=None)
    return SimpleNamespace(engine=engine, ids=identifiers, encoded_password=encoded_password,
                           settings=settings, service=BuyerLoginService(engine, settings=settings))


@pytest.fixture
def login_store(encoded_password):
    engine = sa.create_engine("sqlite://")
    @sa.event.listens_for(engine, "connect")
    def setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("now", 0, lambda: "2026-10-23 00:00:00")
    User.metadata.create_all(engine, tables=TABLES + [Reservation.__table__])
    policy = Policy.__table__.to_metadata(sa.MetaData())
    for constraint in policy.constraints:
        if constraint.name == "ck_eips_singleton":
            constraint.sqltext = sa.text(f"id = '{POLICY_STATE_ID.hex}'")
    policy.create(engine)
    identifiers = seed_users(engine, encoded_password)
    seed_registry(engine, identifiers)
    yield make_store(engine, identifiers, encoded_password)
    engine.dispose()


def request(email="buyer@example.test", password=PASSWORD):
    return BuyerLoginRequest(email=email, password=password)


def counts(store):
    with Session(store.engine) as db:
        return [db.scalar(sa.select(sa.func.count()).select_from(model))
                for model in (User, BuyerProfile, AuthSession, RefreshToken)]


def test_valid_buyer_preserves_profiles_and_uses_stage2b(login_store):
    before = counts(login_store)
    credentials = login_store.service.login(request())
    assert credentials.user_id == login_store.ids["buyer"]
    assert credentials.refresh_token not in repr(credentials)
    assert counts(login_store) == before[:2] + [1, 1]
    with Session(login_store.engine) as db:
        assert db.scalar(sa.select(User.role).where(User.id == credentials.user_id)) == "vendor"
        assert db.scalar(sa.select(RefreshToken.token_digest)) == digest_refresh_token(credentials.refresh_token)
    sessions = SessionService(login_store.engine, settings=login_store.settings)
    replacement = sessions.rotate_refresh_token(credentials.refresh_token)
    from app.modules.auth.session_service import SessionAuthenticationError
    with pytest.raises(SessionAuthenticationError):
        sessions.rotate_refresh_token(credentials.refresh_token)
    with pytest.raises(SessionAuthenticationError):
        sessions.rotate_refresh_token(replacement.refresh_token)


@pytest.mark.parametrize("email,password", [
    ("buyer@example.test", "wrong password"), ("unknown@example.test", PASSWORD),
    ("inactive@example.test", PASSWORD), ("missing@example.test", PASSWORD),
    ("k@example.test", PASSWORD), ("unicode@xn--bcher-kva.test", PASSWORD),
    ("buyer@example.test", PASSWORD.strip()),
])
def test_credential_rejections_indistinguishable(login_store, email, password):
    before = counts(login_store)
    with pytest.raises(InvalidBuyerCredentials) as caught:
        login_store.service.login(request(email, password))
    assert str(caught.value) == "Invalid email or password"
    assert email not in repr(caught.value) and password not in repr(caught.value)
    assert counts(login_store) == before


def test_legacy_ascii_casing(login_store):
    result = login_store.service.login(request(" \tLegacy@EXAMPLE.TEST\r\n"))
    assert result.user_id == login_store.ids["legacy"]
    with Session(login_store.engine) as db:
        assert db.get(User, result.user_id).email == EMAILS["legacy"]


@pytest.mark.parametrize("email", ["unknown@example.test", "inactive@example.test", "missing@example.test", "k@example.test", "unicode@xn--bcher-kva.test"])
def test_ineligible_uses_valid_dummy_argon2(login_store, monkeypatch, email):
    observed = []
    def verify(password, encoded):
        observed.append((password, encoded))
        return verify_password(password, encoded)
    monkeypatch.setattr("app.modules.auth.login_service.verify_password", verify)
    with pytest.raises(InvalidBuyerCredentials):
        login_store.service.login(request(email))
    assert observed == [(PASSWORD, _DUMMY_HASH)]
    assert _DUMMY_HASH.startswith("$argon2id$v=19$m=65536,t=3,p=1$")
    assert verify_password("ScrapMart dummy login verification only", _DUMMY_HASH)


@pytest.mark.parametrize("email", ["K@example.test", "buyer@bücher.test", "İ@example.test"])
def test_request_rejects_unicode_aliases(email):
    with pytest.raises(ValidationError):
        request(email)


@pytest.mark.parametrize("password", ["x", " " * 128, "é" * 128, PASSWORD])
def test_request_accepts_existing_verifier_lengths_without_changes(password):
    value = request(password=password)
    assert value.password.get_secret_value() == password
    assert password not in repr(value)


@pytest.mark.parametrize("password", ["", "x" * 129, "a\x00b", "\ud800"])
def test_request_rejects_invalid_verifier_inputs(password):
    with pytest.raises(ValidationError):
        request(password=password)


@pytest.mark.parametrize("state", ["missing", "building", "version", "fingerprint", "libraries"])
def test_registry_fails_closed(login_store, monkeypatch, state):
    if state in {"fingerprint", "libraries"}:
        def unsupported():
            if state == "libraries":
                from app.modules.auth.email_identity_policy import PolicyVersionMismatch
                raise PolicyVersionMismatch()
            return "unsupported"
        monkeypatch.setattr("app.modules.auth.login_policy.policy_fingerprint", unsupported)
    else:
        with login_store.engine.begin() as db:
            if state == "version":
                if db.dialect.name == "postgresql":
                    table = "email_identity_policy_state"
                    if hasattr(login_store, "schema"):
                        table = f"{login_store.schema}.{table}"
                    db.exec_driver_sql(f"ALTER TABLE {table} DROP CONSTRAINT ck_eips_policy_version")
                else:
                    db.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
                db.execute(Policy.__table__.update().values(policy_version=2))
            elif state == "missing":
                db.execute(Policy.__table__.delete())
            else:
                db.execute(Policy.__table__.update().values(status="building"))
    before = counts(login_store)
    for email in ("buyer@example.test", "unknown@example.test"):
        with pytest.raises(BuyerLoginUnavailableError):
            login_store.service.login(request(email))
    assert counts(login_store) == before


@pytest.mark.parametrize("change", ["password", "inactive", "profile", "reservation", "registry", "fingerprint"])
def test_admission_rechecks_after_verification(login_store, monkeypatch, change):
    original = login_store.service._sessions.admit_buyer_session
    def admit(*args):
        if change == "fingerprint":
            monkeypatch.setattr("app.modules.auth.login_policy.policy_fingerprint", lambda: "unsupported")
        else:
            with Session(login_store.engine) as db, db.begin():
                if change == "password":
                    db.get(User, login_store.ids["buyer"]).password_hash = "changed hash"
                elif change == "inactive":
                    db.get(User, login_store.ids["buyer"]).is_active = False
                elif change == "profile":
                    db.execute(sa.delete(BuyerProfile).where(BuyerProfile.user_id == login_store.ids["buyer"]))
                elif change == "reservation":
                    db.execute(sa.update(Reservation).where(Reservation.lookup_key == "buyer@example.test").values(state="blocked", user_id=None))
                else:
                    db.execute(sa.update(Policy).values(status="building"))
        return original(*args)
    monkeypatch.setattr(login_store.service._sessions, "admit_buyer_session", admit)
    error = BuyerLoginUnavailableError if change in {"registry", "fingerprint"} else InvalidBuyerCredentials
    with pytest.raises(error):
        login_store.service.login(request())
    assert counts(login_store)[2:] == [0, 0]


@pytest.mark.parametrize("sqlstate", ["40001", "40P01", "08006", None])
def test_admission_retry_only_confirmed_aborts(login_store, monkeypatch, sqlstate):
    attempts, committed = [], []
    class ObservedSession(Session):
        pass
    class Failure(Exception):
        pass
    @sa.event.listens_for(ObservedSession, "before_commit")
    def fail(db):
        attempts.append(db)
        db.flush()
        if len(attempts) == 1:
            error = Failure()
            error.sqlstate = sqlstate
            raise sa.exc.DBAPIError("commit", None, error)
    @sa.event.listens_for(ObservedSession, "after_commit")
    def success(db):
        committed.append(db)
    monkeypatch.setattr("app.modules.auth.session_service.Session", ObservedSession)
    if sqlstate in {"40001", "40P01"}:
        credentials = login_store.service.login(request())
        assert len(attempts) == 2 and attempts[0] is not attempts[1]
        assert committed == [attempts[1]]
        assert counts(login_store)[2:] == [1, 1]
        with Session(login_store.engine) as db:
            assert db.get(AuthSession, credentials.session_id) is not None
    else:
        with pytest.raises(BuyerLoginUnavailableError):
            login_store.service.login(request())
        assert len(attempts) == 1 and not committed
        assert counts(login_store)[2:] == [0, 0]


@pytest.mark.parametrize("persisted", [False, True])
def test_uncertain_commit_never_retried(login_store, monkeypatch, persisted):
    original = login_store.engine.dialect.do_commit
    commits = []
    def commit(connection):
        # Lookup's read transaction also commits; target only admission writes.
        commits.append(1)
        if len(commits) == 2:
            if persisted:
                original(connection)
            raise OSError("uncertain commit outcome")
        return original(connection)
    monkeypatch.setattr(login_store.engine.dialect, "do_commit", commit)
    with pytest.raises(BuyerLoginUnavailableError) as caught:
        login_store.service.login(request())
    assert "uncertain" not in str(caught.value)
    assert len(commits) == 2
    monkeypatch.undo()
    assert counts(login_store)[2:] == ([1, 1] if persisted else [0, 0])


def test_partial_session_write_rolls_back(login_store, monkeypatch):
    def fail(mapper, connection, target):
        raise sa.exc.OperationalError("insert", None, Exception("private database details"))
    sa.event.listen(RefreshToken, "before_insert", fail)
    try:
        with pytest.raises(BuyerLoginUnavailableError) as caught:
            login_store.service.login(request())
        assert "private" not in str(caught.value)
        assert counts(login_store)[2:] == [0, 0]
    finally:
        sa.event.remove(RefreshToken, "before_insert", fail)


def test_dummy_password_cannot_authenticate_unknown_account(login_store):
    with pytest.raises(InvalidBuyerCredentials):
        login_store.service.login(request("unknown@example.test", "ScrapMart dummy login verification only"))
    assert counts(login_store)[2:] == [0, 0]


def test_login_rejects_autocommit_for_all_accounts(login_store):
    service = BuyerLoginService(login_store.engine.execution_options(isolation_level="AUTOCOMMIT"))
    for email in ("buyer@example.test", "unknown@example.test"):
        with pytest.raises(BuyerLoginUnavailableError):
            service.login(request(email))
    assert counts(login_store)[2:] == [0, 0]


def test_exhausted_admission_retries_roll_back(login_store, monkeypatch):
    attempts = []
    class AbortedSession(Session):
        pass
    class Conflict(Exception):
        sqlstate = "40001"
    @sa.event.listens_for(AbortedSession, "before_commit")
    def abort(db):
        attempts.append(db)
        db.flush()
        raise sa.exc.DBAPIError("commit", None, Conflict())
    monkeypatch.setattr("app.modules.auth.session_service.Session", AbortedSession)
    with pytest.raises(BuyerLoginUnavailableError):
        login_store.service.login(request())
    assert len(attempts) == len({id(db) for db in attempts}) == 3
    assert counts(login_store)[2:] == [0, 0]


@pytest.mark.parametrize("stored_hash", [
    "", "not-a-hash", "$2b$12$unsupported", "$argon2id$broken",
    "$argon2id$v=19$m=65536,t=3,p=1$bad$bad",
    _DUMMY_HASH.replace("m=65536", "m=0"),
    _DUMMY_HASH.replace("v=19", "v=999"),
    _DUMMY_HASH.rsplit("$", 1)[0],
    _DUMMY_HASH.rsplit("$", 1)[0] + "$***invalid-base64***",
    _DUMMY_HASH + "雪",
    _DUMMY_HASH.replace("v=19", "v=16").replace("m=65536", "m=0"),
])
def test_unusable_account_hash_runs_dummy_and_rejects(login_store, monkeypatch, caplog, stored_hash):
    with Session(login_store.engine) as db, db.begin():
        db.get(User, login_store.ids["buyer"]).password_hash = stored_hash
    observed = []
    original = security._password_hasher.verify
    def observe(password, encoded):
        observed.append((password, encoded))
        return original(password, encoded)
    monkeypatch.setattr(security._password_hasher, "verify", observe)
    # Even the dummy's actual password cannot turn fallback into authentication.
    password = "ScrapMart dummy login verification only"
    before = counts(login_store)
    with pytest.raises(InvalidBuyerCredentials) as caught:
        login_store.service.login(request(password=password))
    assert str(caught.value) == "Invalid email or password"
    assert observed == [(password, _DUMMY_HASH)]
    assert counts(login_store) == before
    assert password not in caplog.text
    assert _DUMMY_HASH not in caplog.text
    if stored_hash:
        assert stored_hash not in caplog.text


@pytest.mark.parametrize("variant", ["ID", "I", "D"])
@pytest.mark.parametrize("version", [16, 19])
@pytest.mark.parametrize("correct", [True, False])
def test_supported_hashes_verify_once_without_dummy(login_store, monkeypatch, variant, version, correct):
    from argon2.low_level import Type, hash_secret
    encoded = hash_secret(
        PASSWORD.encode("utf-8"), b"legacy-test-salt", time_cost=1,
        memory_cost=8192, parallelism=1, hash_len=32, type=getattr(Type, variant), version=version,
    ).decode("ascii")
    assert verify_password(PASSWORD, encoded)
    with Session(login_store.engine) as db, db.begin():
        db.get(User, login_store.ids["buyer"]).password_hash = encoded
    calls = []
    original = security._argon2_login_verifier
    class ObservedVerifier:
        def verify(self, encoded, password):
            calls.append((encoded, password))
            return original.verify(encoded, password)
    def unexpected_dummy(*args, **kwargs):
        pytest.fail("Supported account hash must not trigger a second expensive verification")
    monkeypatch.setattr(security, "_argon2_login_verifier", ObservedVerifier())
    monkeypatch.setattr(security._password_hasher, "verify", unexpected_dummy)
    password = PASSWORD if correct else "wrong password"
    if correct:
        assert login_store.service.login(request(password=password)).user_id == login_store.ids["buyer"]
        assert counts(login_store)[2:] == [1, 1]
    else:
        with pytest.raises(InvalidBuyerCredentials, match="^Invalid email or password$"):
            login_store.service.login(request(password=password))
        assert counts(login_store)[2:] == [0, 0]
    assert calls == [(encoded, password)]


@pytest.mark.parametrize("stored_hash", [None, b"hash", "x" * 1025, "\ud800"])
def test_dummy_fallback_for_unusable_hash_inputs(monkeypatch, stored_hash):
    calls = []
    original = security._password_hasher.verify
    def observe(password, encoded):
        calls.append(encoded)
        return original(password, encoded)
    monkeypatch.setattr(security._password_hasher, "verify", observe)
    assert not verify_password(PASSWORD, stored_hash, dummy_hash=_DUMMY_HASH)
    assert calls == [_DUMMY_HASH]
