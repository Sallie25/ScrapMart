"""Explicit staging-only migration/bootstrap entrypoint; no automatic retries."""
import argparse
import os
import sys
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.operations.staging_bootstrap import BootstrapRejected, activate_empty, check_target
from app.operations.provision_diagnostics import failure, render

HEAD = 'c28fa4567def'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('migrate', 'bootstrap-empty', 'provision-runtime'))
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--expected-role', required=True)
    parser.add_argument('--confirm-staging', action='store_true', required=True)
    parser.add_argument('--safe-provision-diagnostics', action='store_true')
    args = parser.parse_args(argv)
    if args.safe_provision_diagnostics and args.operation != 'provision-runtime':
        parser.error('Safe provisioning diagnostics require provision-runtime.')
    url = os.environ.get('STAGING_MAINTENANCE_DATABASE_URL')
    if os.environ.get('APP_ENVIRONMENT') != 'staging' or not url:
        parser.exit(1, 'Staging maintenance configuration is required.\n')
    engine = None
    operation = 'connection'
    commit_uncertain = False
    def report(value):
        nonlocal operation
        operation = value
    try:
        engine = create_engine(url, poolclass=NullPool, hide_parameters=True, echo=False,
                               isolation_level='READ COMMITTED',
                               connect_args={'connect_timeout': 10})
        if engine.dialect.name != 'postgresql': raise BootstrapRejected()
        with engine.connect() as db:
            with db.begin():
                report('transaction-setup')
                db.execute(text("SET LOCAL lock_timeout='5s'"))
                db.execute(text("SET LOCAL statement_timeout='60s'"))
                report('target')
                check_target(db, args.expected_database, args.expected_role)
                if args.operation == 'migrate':
                    config = Config('alembic.ini')
                    config.attributes['connection'] = db
                    command.upgrade(config, HEAD)
                elif args.operation == "bootstrap-empty":
                    activate_empty(db)
                else:
                    from app.operations.runtime_role import provision
                    provision(db, report=report)
                report('commit')
                commit_uncertain = True
            commit_uncertain = False
            report('connection-close')
        print('Staging maintenance completed.')
    except (Exception, KeyboardInterrupt) as error:
        if args.safe_provision_diagnostics:
            print(render(failure(error, operation, commit_uncertain)), file=sys.stderr)
            parser.exit(1)
        # A lost commit acknowledgement is ambiguous: never claim rollback/retry.
        parser.exit(1, 'Maintenance not confirmed. Inspect durable state using a separately authorized session before retrying; no automatic retry was attempted.\n')
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                # Cleanup must not override the sanitized result with a traceback.
                pass


if __name__ == '__main__':
    main()
