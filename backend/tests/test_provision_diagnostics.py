"""Mock diagnostic output and transaction boundaries; no external connections."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy.exc import DBAPIError
from app.operations import staging, runtime_role
from app.operations.provision_diagnostics import failure, render, validated_child_report, PREFIX

SECRET='postgresql://owner:private-password@private-host/database'

@pytest.mark.parametrize('state,category', [('42501','permission-denied'),('28P01','authentication'),
    ('08006','connection'),('57014','timeout'),('55P03','timeout'),('40001','transaction-conflict'),
    ('42P01','postgresql-error'),(SECRET,'internal-error'),(None,'internal-error')])
def test_sanitized_sqlstate(state,category):
    error=Exception(SECRET);error.sqlstate=state
    wrapped=DBAPIError(SECRET,{'password':SECRET},error)
    record=failure(wrapped,'create-role',False)
    assert record==dict(operation='create-role',sqlstate=state if state and len(state)==5 else None,
                        category=category,commit_uncertain=False)
    assert SECRET not in render(record)
    assert validated_child_report(render(record))==render(record)

@pytest.mark.parametrize('output',[SECRET, PREFIX+'{}', PREFIX+'[]', PREFIX+'null',
    PREFIX+json.dumps(dict(operation=SECRET,sqlstate=None,category='internal-error',commit_uncertain=True)),
    render(failure(Exception(),'commit',True))+'\n'+SECRET])
def test_child_output_rejects_untrusted_content(output):
    assert validated_child_report(output) is None

@pytest.mark.parametrize('where',['connect','target','create-role','initial-audit','grant-columns','final-audit','commit','close'])
def test_staging_failure_record_and_one_attempt(monkeypatch,capsys,where):
    monkeypatch.setenv('APP_ENVIRONMENT','staging')
    monkeypatch.setenv('STAGING_MAINTENANCE_DATABASE_URL',SECRET)
    engine=MagicMock();engine.dialect.name='postgresql'
    db=engine.connect.return_value.__enter__.return_value
    tx=db.begin.return_value
    error=Exception(SECRET);error.sqlstate='42501'
    wrapped=DBAPIError(SECRET,{'password':SECRET},error)
    monkeypatch.setattr(staging,'create_engine',Mock(return_value=engine))
    target=Mock();monkeypatch.setattr(staging,'check_target',target)
    def provision(db,report):
        report(where)
        if where not in ('connect','target','commit','close'): raise wrapped
    attempt=Mock(side_effect=provision);monkeypatch.setattr(runtime_role,'provision',attempt)
    if where=='connect':engine.connect.side_effect=wrapped
    if where=='target':target.side_effect=wrapped
    if where=='commit':tx.__exit__.side_effect=wrapped
    if where=='close':engine.connect.return_value.__exit__.side_effect=wrapped
    with pytest.raises(SystemExit) as exit:
        staging.main(['provision-runtime','--confirm-staging','--expected-database','scrapmart_staging',
                      '--expected-role','operator','--safe-provision-diagnostics'])
    assert exit.value.code==1
    output=capsys.readouterr()
    assert SECRET not in output.out+output.err
    record=json.loads(output.err[len(PREFIX):])
    assert record['operation']=={'connect':'connection','close':'connection-close'}.get(where,where)
    assert record['commit_uncertain']==(where=='commit')
    assert record['sqlstate']=='42501'
    assert attempt.call_count==(0 if where in ('connect','target') else 1)
    engine.dispose.assert_called_once()
    if where not in ('connect','close','commit'):
        assert tx.__exit__.call_args.args[0] is DBAPIError


def test_precondition_category():
    assert failure(runtime_role.RuntimeRoleRejected(),'initial-audit',False)['category']=='precondition-rejected'


def test_real_provision_operation_marker_before_create_failure():
    db=MagicMock();db.dialect.name='postgresql'
    db.dialect.detect_autocommit_setting.return_value=False
    def execute(sql,*args):
        sql=str(sql);result=MagicMock()
        if sql.startswith('CREATE ROLE'):raise RuntimeError(SECRET)
        result.one.return_value=('scrapmart_staging',False,'operator')
        result.scalars.return_value.all.return_value=[runtime_role.HEAD]
        result.scalar_one.return_value=False if 'EXISTS' in sql else 1
        return result
    db.execute.side_effect=execute
    markers=[]
    with pytest.raises(RuntimeError):runtime_role.provision(db,report=markers.append)
    assert markers[-1]=='create-role'
