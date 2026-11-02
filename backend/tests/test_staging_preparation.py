"""Offline staging safety boundaries; no provider or PostgreSQL connections."""
import hashlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from sqlalchemy import create_engine
from app.core.config import Settings
from app.infrastructure.sms import get_sms_delivery
from app.infrastructure.storage.listing_photos import get_listing_photo_storage, ListingPhotoUnavailable
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable
from app.operations import staging
from app.operations.staging_bootstrap import (
    activate_empty, check_target, empty_manifest, BootstrapRejected,
    POLICY_STATE_ID, HEAD, FINGERPRINT,
)


@pytest.fixture
def settings():
    return Settings(_env_file=None, _secrets_dir=None)


def test_disabled_adapters_fail_closed(settings, monkeypatch):
    settings.listing_photo_storage_factory=None;settings.sms_delivery_factory=None
    monkeypatch.setattr('app.core.config.get_settings',lambda:settings)
    with pytest.raises(ListingPhotoUnavailable): get_listing_photo_storage(settings)
    with pytest.raises(VerificationInfrastructureUnavailable): get_sms_delivery()


def test_packaged_factory_interfaces(settings,monkeypatch):
    photo=SimpleNamespace(**{name:Mock() for name in ('put','exists','public_url','delete')})
    sms=SimpleNamespace(send_code=Mock())
    factory=Mock(side_effect=[photo,sms])
    monkeypatch.setitem(sys.modules,'staging_test_adapter',SimpleNamespace(factory=factory))
    settings.listing_photo_storage_factory='staging_test_adapter:factory'
    settings.sms_delivery_factory='staging_test_adapter:factory'
    monkeypatch.setattr('app.core.config.get_settings',lambda:settings)
    assert get_listing_photo_storage(settings) is photo
    assert get_sms_delivery() is sms
    assert factory.call_args_list[0].args==(settings,)
    photo.put.assert_not_called();sms.send_code.assert_not_called()


@pytest.mark.parametrize('reference',['https://example.test/factory','missing_module:factory','os:missing','x:y:z'])
def test_invalid_factory_configuration_is_safe(settings,monkeypatch,reference):
    settings.listing_photo_storage_factory=reference;settings.sms_delivery_factory=reference
    monkeypatch.setattr('app.core.config.get_settings',lambda:settings)
    with pytest.raises(ListingPhotoUnavailable) as photo: get_listing_photo_storage(settings)
    with pytest.raises(VerificationInfrastructureUnavailable) as sms: get_sms_delivery()
    assert reference not in str(photo.value)+str(sms.value)


def test_broken_factories_and_missing_methods(settings,monkeypatch):
    settings.listing_photo_storage_factory='staging_test_adapter:factory'
    for factory in (lambda _:object(),Mock(side_effect=RuntimeError('private credentials'))):
        monkeypatch.setitem(sys.modules,'staging_test_adapter',SimpleNamespace(factory=factory))
        with pytest.raises(ListingPhotoUnavailable) as error: get_listing_photo_storage(settings)
        assert 'private credentials' not in str(error.value)


class Result:
    def __init__(self, value=None): self.value=value;self.rowcount=1
    def scalars(self): return self
    def mappings(self): return self
    def all(self): return self.value
    def one(self): return self.value
    def scalar_one(self): return self.value


class Database:
    dialect=SimpleNamespace(name='postgresql',detect_autocommit_setting=lambda _:False)
    connection=SimpleNamespace(driver_connection=object())
    def __init__(self):
        self.calls=[];self.version=[HEAD];self.populated=False;self.reservations=False
        self.guards=[('users','ct_users_email_reservation'),('users','tr_users_email_immutable'),('email_identity_reservations','tr_email_reservation_immutable')]
        self.constraints=['uq_eir_lookup_key','fk_eir_user','ck_eir_policy_version','ck_eir_ownership','ck_eir_ascii_key','ck_eips_singleton','ck_eips_policy_version','ck_eips_status','ck_eips_counts','ck_eips_manifest','ck_eips_ready']
        self.states=[dict(id=POLICY_STATE_ID,policy_version=1,status='building',last_user_id=None,users_processed=0,source_count=0,manifest_sha256=None)]
        self.identity=('staging_test','maintenance',False);self.update_count=1
    def execute(self, statement, params=None):
        sql=str(statement);self.calls.append((sql,params))
        if 'current_database()' in sql: return Result(self.identity)
        if 'SELECT version_num' in sql: return Result(self.version)
        if 'FROM pg_catalog.pg_trigger' in sql: return Result(self.guards)
        if 'FROM pg_catalog.pg_constraint' in sql: return Result(self.constraints)
        if 'SELECT EXISTS' in sql: return Result(self.reservations if 'reservations' in sql else self.populated)
        if 'SELECT * FROM public.email_identity_policy_state' in sql: return Result(self.states)
        result=Result();result.rowcount=self.update_count;return result


def test_empty_bootstrap_fences_and_updates_only_policy():
    db=Database();check_target(db,'staging_test','maintenance');activate_empty(db)
    locks=[sql for sql,_ in db.calls if sql.startswith('LOCK')]
    assert len(locks)==4 and 'users IN SHARE' in locks[1] and 'EXCLUSIVE' in locks[-1]
    mutations=[(sql,params) for sql,params in db.calls if sql.startswith('UPDATE')]
    assert len(mutations)==1 and mutations[0][1]['manifest']==empty_manifest()
    source=hashlib.sha256(b'scrapmart-email-source-v1\0'+FINGERPRINT.encode()).digest()
    assert empty_manifest()==hashlib.sha256(b'scrapmart-email-checkpoint-v1\0'+FINGERPRINT.encode()+source+bytes(24)).digest()
    assert not any(sql.startswith(('INSERT','DELETE','ALTER','DROP')) for sql,_ in db.calls)


@pytest.mark.parametrize('change',[
    {'version':['wrong']},{'version':[HEAD,HEAD]}, {'populated':True}, {'reservations':True},
    {'guards':[]},{'constraints':[]},{'states':[]},
])
def test_bootstrap_rejects_incomplete_or_populated_state(change):
    db=Database()
    for key,value in change.items(): setattr(db,key,value)
    with pytest.raises(BootstrapRejected): activate_empty(db)
    assert not any(sql.startswith('UPDATE') for sql,_ in db.calls)


@pytest.mark.parametrize('field,value',[
    ('status','ready'),('policy_version',2),('users_processed',1),('source_count',1),
    ('manifest_sha256',bytes(32)),('last_user_id',POLICY_STATE_ID),('id',None),
])
def test_bootstrap_refuses_nonpristine_policy(field,value):
    db=Database();db.states[0][field]=value
    with pytest.raises(BootstrapRejected): activate_empty(db)
    assert not any(sql.startswith('UPDATE') for sql,_ in db.calls)


def test_policy_fingerprint_and_compare_update_fail_closed(monkeypatch):
    db=Database();monkeypatch.setattr('app.operations.staging_bootstrap.policy_fingerprint',lambda:'wrong')
    with pytest.raises(BootstrapRejected): activate_empty(db)
    assert not db.calls
    monkeypatch.setattr('app.operations.staging_bootstrap.policy_fingerprint',lambda:FINGERPRINT)
    db.update_count=0
    with pytest.raises(BootstrapRejected): activate_empty(db)


@pytest.mark.parametrize('identity',[('other','maintenance',False),('staging_test','runtime',False),('staging_test','maintenance',True)])
def test_operator_target_checks(identity):
    db=Database();db.identity=identity
    with pytest.raises(BootstrapRejected): check_target(db,'staging_test','maintenance')


def test_no_bootstrap_on_non_postgresql():
    engine=create_engine('sqlite://')
    with engine.connect() as db, pytest.raises(BootstrapRejected): check_target(db,'test','role')
    engine.dispose()


def args(operation='bootstrap-empty'):
    return [operation,'--confirm-staging','--expected-database','staging_test','--expected-role','maintenance']


def test_cli_requires_explicit_confirmation_and_staging_config(monkeypatch,capsys):
    create=Mock();monkeypatch.setattr(staging,'create_engine',create)
    monkeypatch.setenv('APP_ENVIRONMENT','production')
    monkeypatch.setenv('STAGING_MAINTENANCE_DATABASE_URL','never-display-this')
    with pytest.raises(SystemExit): staging.main(args())
    with pytest.raises(SystemExit): staging.main([x for x in args() if x!='--confirm-staging'])
    create.assert_not_called();assert 'never-display-this' not in capsys.readouterr().err


def test_cli_atomic_commit_rollback_and_safe_uncertainty(monkeypatch,capsys):
    monkeypatch.setenv('APP_ENVIRONMENT','staging');monkeypatch.setenv('STAGING_MAINTENANCE_DATABASE_URL','private-url')
    from unittest.mock import MagicMock
    engine=MagicMock();engine.dialect.name='postgresql'
    monkeypatch.setattr(staging,'create_engine',lambda *a,**kw:engine)
    monkeypatch.setattr(staging,'check_target',Mock())
    activate=Mock();monkeypatch.setattr(staging,'activate_empty',activate)
    staging.main(args());activate.assert_called_once()
    tx=engine.connect.return_value.__enter__.return_value.begin.return_value
    assert tx.__exit__.call_args.args==(None,None,None)
    tx.__exit__.side_effect=RuntimeError('private-url')
    with pytest.raises(SystemExit): staging.main(args())
    assert 'private-url' not in capsys.readouterr().err
    assert activate.call_count==2  # Exactly one invocation per operator attempt.
    assert engine.dispose.call_count==2


def test_cli_migrations_use_explicit_connection(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setenv('APP_ENVIRONMENT','staging');monkeypatch.setenv('STAGING_MAINTENANCE_DATABASE_URL','private-url')
    engine=MagicMock();engine.dialect.name='postgresql'
    monkeypatch.setattr(staging,'create_engine',lambda *a,**kw:engine)
    monkeypatch.setattr(staging,'check_target',Mock())
    upgrade=Mock();monkeypatch.setattr(staging.command,'upgrade',upgrade)
    staging.main(args('migrate'))
    config,head=upgrade.call_args.args
    assert config.attributes['connection'] is engine.connect.return_value.__enter__.return_value
    assert head==HEAD


def test_alembic_environment_uses_supplied_connection_without_settings(monkeypatch):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.environment import EnvironmentContext
    engine=create_engine('sqlite://')
    monkeypatch.setenv('DATABASE_URL','not-a-real-database-url')
    monkeypatch.setattr('sqlalchemy.engine_from_config',Mock(side_effect=AssertionError('No new engine allowed')))
    config=Config('alembic.ini');script=ScriptDirectory.from_config(config)
    with engine.begin() as db:
        config.attributes['connection']=db
        with EnvironmentContext(config,script,fn=lambda revision,context:iter(())):
            script.run_env()
        assert not db.closed
    engine.dispose()


def test_bootstrap_failure_exits_transaction_without_retry(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setenv('APP_ENVIRONMENT','staging');monkeypatch.setenv('STAGING_MAINTENANCE_DATABASE_URL','private-url')
    engine=MagicMock();engine.dialect.name='postgresql'
    monkeypatch.setattr(staging,'create_engine',lambda *a,**kw:engine)
    monkeypatch.setattr(staging,'check_target',Mock())
    activate=Mock(side_effect=BootstrapRejected());monkeypatch.setattr(staging,'activate_empty',activate)
    with pytest.raises(SystemExit): staging.main(args())
    activate.assert_called_once()
    tx=engine.connect.return_value.__enter__.return_value.begin.return_value
    assert tx.__exit__.call_args.args[0] is BootstrapRejected
