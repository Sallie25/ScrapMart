"""Offline D3 migration/ACL specification checks; no database connections."""
import importlib.util
import io
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.operations.runtime_role import MANIFEST, COLUMNS, ROLE


def test_d3_postgresql_sql_keeps_data_and_hardens_functions():
    path=Path('alembic/versions/c28fa4567def_restricted_runtime_compatibility.py')
    spec=importlib.util.spec_from_file_location('d3_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output,'version_table_schema':'d3_fixture'})):
        module.upgrade();module.downgrade()
    sql=output.getvalue()
    assert module.down_revision=='b17e9a3456cd'
    assert 'SECURITY DEFINER' not in sql and 'SECURITY INVOKER SET search_path=pg_catalog' in sql
    assert 'UPDATE d3_fixture.listings SET id=id' in sql
    assert 'FROM d3_fixture.listing_images' in sql
    assert 'DROP TABLE' not in sql and 'ALTER TABLE' not in sql
    assert sql.count('CREATE TRIGGER guard_runtime_identifier')==3
    assert 'REVOKE ALL ON FUNCTION d3_fixture.scrapmart_check_listing_images() FROM PUBLIC' in sql


def test_acl_manifest_excludes_maintenance_and_privileged_columns():
    assert len(COLUMNS)==17 and 'alembic_version' not in COLUMNS
    assert ROLE=='scrapmart_staging_api'
    assert MANIFEST['UPDATE']['email_identity_policy_state']=={'id'}
    assert 'verification_reviewers' not in MANIFEST['INSERT']
    assert 'verification_reviewers' not in MANIFEST['UPDATE']
    assert MANIFEST['UPDATE']['users']=={'updated_at'}
    assert {'id'}==MANIFEST['UPDATE']['buyer_profiles']==MANIFEST['UPDATE']['categories']
    assert 'id' in MANIFEST['UPDATE']['listings']
    for tables in MANIFEST.values():
        for table,columns in tables.items(): assert columns <= COLUMNS[table]


class DatabaseAcl:
    def __init__(self,acl,*,create=False,temp=False,grantable_temp=False):
        self.acl=acl;self.create=create;self.temp=temp;self.grantable_temp=grantable_temp
    def execute(self,statement,parameters=None):
        from types import SimpleNamespace
        sql=str(statement)
        if 'aclexplode' in sql: return SimpleNamespace(all=lambda:self.acl)
        value=self.grantable_temp if 'WITH GRANT OPTION' in sql else self.create if "'CREATE'" in sql else self.temp
        return SimpleNamespace(scalar_one=lambda:value)


def test_public_temp_only_is_accepted_with_or_without_runtime_connect():
    from app.operations.runtime_role import audit_database_privileges
    for acl in ([(0,'TEMPORARY',False)],[(0,'TEMPORARY',False),(42,'CONNECT',False)]):
        audit_database_privileges(DatabaseAcl(acl,temp=True),42)
    audit_database_privileges(DatabaseAcl([],temp=False),42)


def test_direct_temp_and_other_database_privilege_drift_rejected():
    import pytest
    from app.operations.runtime_role import audit_database_privileges,RuntimeRoleRejected
    for acl in ([(0,'TEMPORARY',False),(42,'TEMPORARY',False)],
                [(42,'TEMPORARY',False)],[(42,'TEMPORARY',True)],
                [(42,'CONNECT',True)],[(42,'CREATE',False)]):
        with pytest.raises(RuntimeRoleRejected):
            audit_database_privileges(DatabaseAcl(acl,temp=True),42)
    for db in (DatabaseAcl([],temp=True),DatabaseAcl([(0,'TEMPORARY',False)],temp=True,create=True),
               DatabaseAcl([(0,'TEMPORARY',False)],temp=True,grantable_temp=True)):
        with pytest.raises(RuntimeRoleRejected): audit_database_privileges(db,42)


def test_removed_public_hardening_flag_fails_before_connect(monkeypatch,capsys):
    import pytest
    from unittest.mock import Mock
    from app.operations import staging
    create=Mock();monkeypatch.setattr(staging,'create_engine',create)
    with pytest.raises(SystemExit):
        staging.main(['provision-runtime','--confirm-staging','--expected-database','scrapmart_staging',
                      '--expected-role','operator','--harden-public'])
    create.assert_not_called()
    assert 'unrecognized arguments: --harden-public' in capsys.readouterr().err
