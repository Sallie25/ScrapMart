"""Session behavior tests using SQLite; concurrency is tested on PostgreSQL only."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.auth.security import AccessTokenClaims, SecurityConfigurationError, digest_refresh_token
from app.modules.auth.session_models import AuthSession, RefreshToken
from app.modules.auth.session_service import (
    SessionAuthenticationError, SessionPersistenceError, SessionService,
)
from app.modules.buyers.models import BuyerProfile


NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def make_store(engine):
    factory = sessionmaker(engine)
    with factory.begin() as db:
        first = User(email="first@example.test", password_hash="test-only", full_name="First", role="vendor")
        second = User(email="second@example.test", password_hash="test-only", full_name="Second", role="buyer")
        db.add_all([first, second])
        db.flush()
        user_id, other_id = first.id, second.id
    clock = [NOW]
    settings = Settings(_env_file=None, _secrets_dir=None, auth_session_expire_days=7)
    return SimpleNamespace(
        engine=engine, factory=factory, user_id=user_id, other_id=other_id,
        clock=clock, settings=settings,
        service=SessionService(engine, settings=settings, clock=lambda: clock[0]),
    )


@pytest.fixture
def store():
    engine = sa.create_engine("sqlite://")

    @sa.event.listens_for(engine, "connect")
    def setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("now", 0, lambda: "2026-10-18 00:00:00")

    Base.metadata.create_all(engine, tables=[User.__table__, BuyerProfile.__table__, AuthSession.__table__, RefreshToken.__table__])
    yield make_store(engine)
    engine.dispose()


def access_claims(credentials, **changes):
    values = dict(user_id=credentials.user_id, session_id=credentials.session_id,
                  token_id=uuid.uuid4(), issued_at=NOW, not_before=NOW,
                  expires_at=NOW + timedelta(minutes=15))
    values.update(changes)
    return AccessTokenClaims(**values)


def token_row(db, plaintext):
    return db.scalar(sa.select(RefreshToken).where(RefreshToken.token_digest == digest_refresh_token(plaintext)))


def test_create_commits_digest_only_absolute_expiry_and_no_profile(store):
    credentials = store.service.create_session(store.user_id)
    assert credentials.expires_at == NOW + timedelta(days=7)
    assert credentials.expires_at.tzinfo == timezone.utc
    assert credentials.refresh_token not in repr(credentials)
    with store.factory() as db:
        session = db.get(AuthSession, credentials.session_id)
        token = token_row(db, credentials.refresh_token)
        assert session.user_id == store.user_id and token.session_id == session.id
        assert token.expires_at == session.expires_at
        assert token.token_digest == digest_refresh_token(credentials.refresh_token)
        assert not db.scalar(sa.select(sa.func.count()).select_from(BuyerProfile))
        assert db.get(User, store.user_id).role == "vendor"


def test_configurable_lifetime(store):
    store.settings.auth_session_expire_days = 3
    assert store.service.create_session(store.user_id).expires_at == NOW + timedelta(days=3)


@pytest.mark.parametrize("days", [0, -1, True, 10**20])
def test_invalid_lifetime(store, days):
    store.settings.auth_session_expire_days = days
    with pytest.raises(SecurityConfigurationError):
        store.service.create_session(store.user_id)


@pytest.mark.parametrize("user_id", [None, "not-a-uuid", uuid.uuid4()])
def test_create_requires_existing_uuid_identity(store, user_id):
    with pytest.raises(SessionAuthenticationError):
        store.service.create_session(user_id)


def test_inactive_identity_rejected_everywhere(store):
    credentials = store.service.create_session(store.user_id)
    with store.factory.begin() as db:
        db.get(User, store.user_id).is_active = False
    operations = [
        lambda: store.service.create_session(store.user_id),
        lambda: store.service.validate_access_session(access_claims(credentials)),
        lambda: store.service.rotate_refresh_token(credentials.refresh_token),
        lambda: store.service.revoke_session(store.user_id, credentials.session_id),
        lambda: store.service.revoke_all_sessions(store.user_id),
    ]
    for operation in operations:
        with pytest.raises(SessionAuthenticationError):
            operation()


def test_access_identity_and_ownership(store):
    credentials = store.service.create_session(store.user_id)
    identity = store.service.validate_access_session(access_claims(credentials))
    assert identity.user_id == store.user_id
    assert identity.session_id == credentials.session_id
    for changes in [dict(user_id=store.other_id), dict(user_id=uuid.uuid4()), dict(session_id=uuid.uuid4()), dict(user_id=None), dict(session_id=None), dict(user_id=str(store.user_id))]:
        with pytest.raises(SessionAuthenticationError):
            store.service.validate_access_session(access_claims(credentials, **changes))
    for invalid in [None, {}, {"sub": store.user_id}]:
        with pytest.raises(SessionAuthenticationError):
            store.service.validate_access_session(invalid)


@pytest.mark.parametrize("state", ["expired", "revoked", "future"])
def test_ineligible_sessions_reject_access_and_rotation(store, state):
    credentials = store.service.create_session(store.user_id)
    if state == "expired":
        store.clock[0] = credentials.expires_at
    elif state == "future":
        store.clock[0] = NOW - timedelta(seconds=1)
    else:
        store.service.revoke_session(store.user_id, credentials.session_id)
    with pytest.raises(SessionAuthenticationError):
        store.service.validate_access_session(access_claims(credentials))
    with pytest.raises(SessionAuthenticationError):
        store.service.rotate_refresh_token(credentials.refresh_token)


def test_rotation_retains_consumed_digest_without_extending_expiry(store):
    first = store.service.create_session(store.user_id)
    store.clock[0] += timedelta(days=2)
    second = store.service.rotate_refresh_token(first.refresh_token)
    store.clock[0] += timedelta(days=2)
    third = store.service.rotate_refresh_token(second.refresh_token)
    assert third.session_id == second.session_id == first.session_id
    assert third.expires_at == second.expires_at == first.expires_at
    with store.factory() as db:
        tokens = db.scalars(sa.select(RefreshToken)).all()
        assert len(tokens) == 3
        assert sum(token.consumed_at is not None for token in tokens) == 2
        assert token_row(db, third.refresh_token).consumed_at is None


@pytest.mark.parametrize("state", ["expired", "future", "beyond_session"])
def test_invalid_refresh_record_rejected(store, state):
    credentials = store.service.create_session(store.user_id)
    with store.factory.begin() as db:
        token = token_row(db, credentials.refresh_token)
        if state == "expired":
            token.expires_at = NOW + timedelta(seconds=1)
            store.clock[0] = NOW + timedelta(seconds=1)
        elif state == "future":
            token.created_at = NOW + timedelta(seconds=1)
        else:
            token.expires_at = NOW + timedelta(days=8)
    with pytest.raises(SessionAuthenticationError):
        store.service.rotate_refresh_token(credentials.refresh_token)


@pytest.mark.parametrize("token", [None, "malformed", "", "A" * 43])
def test_unknown_or_malformed_refresh_rejected(store, token):
    with pytest.raises(SessionAuthenticationError) as caught:
        store.service.rotate_refresh_token(token)
    if token:
        assert token not in str(caught.value)


@pytest.mark.parametrize("state", ["active", "inactive", "expired"])
def test_reuse_commits_revocation_even_when_rejected(store, state):
    first = store.service.create_session(store.user_id)
    replacement = store.service.rotate_refresh_token(first.refresh_token)
    if state == "inactive":
        with store.factory.begin() as db:
            db.get(User, store.user_id).is_active = False
    elif state == "expired":
        store.clock[0] = first.expires_at
    with pytest.raises(SessionAuthenticationError):
        store.service.rotate_refresh_token(first.refresh_token)
    with store.factory() as db:
        assert db.get(AuthSession, first.session_id).revoked_at is not None
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 2
    with pytest.raises(SessionAuthenticationError):
        store.service.rotate_refresh_token(replacement.refresh_token)


def test_single_revocation_idempotency_and_ownership(store):
    first = store.service.create_session(store.user_id)
    second = store.service.create_session(store.other_id)
    with pytest.raises(SessionAuthenticationError):
        store.service.revoke_session(store.other_id, first.session_id)
    assert store.service.revoke_session(store.user_id, first.session_id)
    assert not store.service.revoke_session(store.user_id, first.session_id)
    assert store.service.validate_access_session(access_claims(second)).user_id == store.other_id


def test_logout_all_only_active_sessions_for_identity(store):
    first = store.service.create_session(store.user_id)
    store.service.create_session(store.user_id)
    other = store.service.create_session(store.other_id)
    assert store.service.revoke_all_sessions(store.user_id) == 2
    assert store.service.revoke_all_sessions(store.user_id) == 0
    with pytest.raises(SessionAuthenticationError):
        store.service.validate_access_session(access_claims(first))
    assert store.service.validate_access_session(access_claims(other))
    # A later authenticated login creates a new session, not a persistent ban.
    assert store.service.validate_access_session(access_claims(store.service.create_session(store.user_id)))


def test_rotation_failure_rolls_back_consumption_and_insert(store, monkeypatch):
    first = store.service.create_session(store.user_id)
    monkeypatch.setattr("app.modules.auth.session_service.generate_refresh_token", lambda: first.refresh_token)
    with pytest.raises(SessionPersistenceError) as caught:
        store.service.rotate_refresh_token(first.refresh_token)
    assert first.refresh_token not in str(caught.value)
    with store.factory() as db:
        assert token_row(db, first.refresh_token).consumed_at is None
        assert db.get(AuthSession, first.session_id).revoked_at is None
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 1


def test_no_credentials_returned_when_commit_fails(store, monkeypatch):
    class FailedCommit(Session):
        pass

    @sa.event.listens_for(FailedCommit, "before_commit")
    def fail(db):
        db.flush()
        raise sa.exc.OperationalError("commit", None, Exception("disposable failure"))

    monkeypatch.setattr("app.modules.auth.session_service.Session", FailedCommit)
    service = SessionService(store.engine, settings=store.settings, clock=lambda: NOW)
    with pytest.raises(SessionPersistenceError):
        service.create_session(store.user_id)
    with store.factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(AuthSession)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 0


def test_replay_commit_failure_is_persistence_error_not_success(store, monkeypatch):
    first = store.service.create_session(store.user_id)
    store.service.rotate_refresh_token(first.refresh_token)

    class FailedCommit(Session):
        pass

    @sa.event.listens_for(FailedCommit, "before_commit")
    def fail(db):
        db.flush()
        raise sa.exc.OperationalError("commit", None, Exception("disposable failure"))

    monkeypatch.setattr("app.modules.auth.session_service.Session", FailedCommit)
    service = SessionService(store.engine, clock=lambda: NOW)
    with pytest.raises(SessionPersistenceError):
        service.rotate_refresh_token(first.refresh_token)
    monkeypatch.undo()
    # A subsequent retry can persist revocation; no new token was issued.
    with pytest.raises(SessionAuthenticationError):
        store.service.rotate_refresh_token(first.refresh_token)
    with store.factory() as db:
        assert db.get(AuthSession, first.session_id).revoked_at is not None


@pytest.mark.parametrize("sqlstate", ["40001", "40P01"])
def test_transient_conflicts_retry_whole_rotation(store, monkeypatch, sqlstate):
    first = store.service.create_session(store.user_id)
    attempts = []

    class RetriedSession(Session):
        pass

    class Conflict(Exception):
        pass

    @sa.event.listens_for(RetriedSession, "before_commit")
    def conflict(db):
        attempts.append(1)
        if len(attempts) == 1:
            db.flush()
            error = Conflict()
            error.sqlstate = sqlstate
            raise sa.exc.DBAPIError("commit", None, error)

    monkeypatch.setattr("app.modules.auth.session_service.Session", RetriedSession)
    service = SessionService(store.engine, clock=lambda: NOW)
    replacement = service.rotate_refresh_token(first.refresh_token)
    assert len(attempts) == 2
    with store.factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 2
        assert token_row(db, replacement.refresh_token)


def test_reject_shared_session_without_rolling_back_caller_work(store):
    with store.factory() as db:
        user = db.get(User, store.user_id)
        user.full_name = "Uncommitted caller work"
        with pytest.raises(TypeError, match="synchronous Engine"):
            SessionService(lambda: db, settings=store.settings)
        assert db.in_transaction() and db.is_modified(user)
        assert user.full_name == "Uncommitted caller work"


def test_user_lock_preserves_identity_fields(store):
    with store.factory() as db:
        before = db.execute(sa.select(User.__table__).order_by(User.id)).all()
    first = store.service.create_session(store.user_id)
    store.service.rotate_refresh_token(first.refresh_token)
    store.service.revoke_all_sessions(store.user_id)
    with store.factory() as db:
        assert db.execute(sa.select(User.__table__).order_by(User.id)).all() == before


def test_logout_all_does_not_revoke_expired_sessions(store):
    first = store.service.create_session(store.user_id)
    store.clock[0] = first.expires_at
    assert store.service.revoke_all_sessions(store.user_id) == 0
    with store.factory() as db:
        assert db.get(AuthSession, first.session_id).revoked_at is None


def test_naive_clock_fails_without_persistence(store):
    service = SessionService(store.engine, settings=store.settings, clock=lambda: NOW.replace(tzinfo=None))
    with pytest.raises(SecurityConfigurationError):
        service.create_session(store.user_id)
    with store.factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(AuthSession)) == 0


def test_exhausted_serialization_retries_roll_back(store, monkeypatch):
    first = store.service.create_session(store.user_id)
    attempts = []

    class FailedSession(Session):
        pass

    class Conflict(Exception):
        sqlstate = "40001"

    @sa.event.listens_for(FailedSession, "before_commit")
    def fail(db):
        db.flush()
        attempts.append(1)
        raise sa.exc.DBAPIError("commit", None, Conflict())

    monkeypatch.setattr("app.modules.auth.session_service.Session", FailedSession)
    service = SessionService(store.engine, clock=lambda: NOW)
    with pytest.raises(SessionPersistenceError):
        service.rotate_refresh_token(first.refresh_token)
    assert len(attempts) == 3
    with store.factory() as db:
        assert token_row(db, first.refresh_token).consumed_at is None
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 1


@pytest.mark.parametrize("mode", [None, "create_savepoint", "control_fully"])
def test_reject_external_transaction_without_touching_caller_work(store, mode):
    with store.engine.connect() as connection:
        outer = connection.begin()
        connection.execute(sa.update(User).where(User.id == store.user_id).values(full_name="Caller pending"))
        options = {} if mode is None else {"join_transaction_mode": mode}
        with Session(bind=connection, **options) as caller:
            assert not caller.in_transaction()  # Fresh Session, active underlying transaction.
            called = []

            def factory():
                called.append(True)
                return caller

            events = []
            def committed(conn):
                events.append("commit")
            def rolled_back(conn):
                events.append("rollback")
            sa.event.listen(connection, "commit", committed)
            sa.event.listen(connection, "rollback", rolled_back)
            try:
                for invalid in (connection, caller, factory, sessionmaker(bind=connection, **options)):
                    with pytest.raises(TypeError, match="synchronous Engine"):
                        SessionService(invalid)
                assert not called and not events
                assert outer.is_active and not caller.in_transaction()
                assert connection.scalar(sa.select(User.full_name).where(User.id == store.user_id)) == "Caller pending"
            finally:
                sa.event.remove(connection, "commit", committed)
                sa.event.remove(connection, "rollback", rolled_back)
        outer.rollback()
    with store.factory() as db:
        assert db.get(User, store.user_id).full_name == "First"


def test_credentials_follow_actual_commit_and_retries_use_new_sessions(store, monkeypatch):
    seen = []
    committed = []
    class ObservedSession(Session):
        pass
    class Conflict(Exception):
        sqlstate = "40001"

    @sa.event.listens_for(ObservedSession, "before_commit")
    def before(db):
        seen.append(db)
        db.flush()
        if len(seen) == 1:
            raise sa.exc.DBAPIError("commit", None, Conflict())

    @sa.event.listens_for(ObservedSession, "after_commit")
    def after(db):
        committed.append(db)

    monkeypatch.setattr("app.modules.auth.session_service.Session", ObservedSession)
    credentials = store.service.create_session(store.user_id)
    assert len(seen) == 2 and seen[0] is not seen[1]
    assert committed == [seen[1]]
    with store.factory() as db:
        assert token_row(db, credentials.refresh_token) is not None
    # An unrelated caller rollback cannot undo service writes or replay revocation.
    with store.factory() as caller:
        caller.begin()
        replacement = store.service.rotate_refresh_token(credentials.refresh_token)
        with pytest.raises(SessionAuthenticationError):
            store.service.rotate_refresh_token(credentials.refresh_token)
        caller.rollback()
    with store.factory() as db:
        assert token_row(db, replacement.refresh_token) is not None
        assert db.get(AuthSession, credentials.session_id).revoked_at is not None


@pytest.mark.parametrize("configured_at", ["engine", "options"])
def test_autocommit_rejected_before_writes(store, configured_at):
    if configured_at == "engine":
        if store.engine.dialect.name != "sqlite":
            pytest.skip("SQLite constructor default; PostgreSQL options tested separately")
        engine = sa.create_engine("sqlite://", isolation_level="AUTOCOMMIT")
    else:
        engine = store.engine.execution_options(isolation_level="AUTOCOMMIT")
    try:
        service = SessionService(engine, settings=store.settings)
        with pytest.raises(SecurityConfigurationError, match="transactional isolation"):
            service.create_session(store.user_id)
    finally:
        if configured_at == "engine":
            engine.dispose()
