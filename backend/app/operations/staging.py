"""Explicit staging-only migration/bootstrap entrypoint; no automatic retries."""
import argparse
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.operations.staging_bootstrap import BootstrapRejected, activate_empty, check_target

HEAD = 'c28fa4567def'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('migrate', 'bootstrap-empty', 'provision-runtime'))
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--expected-role', required=True)
    parser.add_argument('--confirm-staging', action='store_true', required=True)
    parser.add_argument("--harden-public", action="store_true", help="Explicitly remove staging PUBLIC CREATE/TEMP privileges")
    args = parser.parse_args(argv)
    if args.harden_public and args.operation != "provision-runtime":
        parser.error("--harden-public is only valid for provision-runtime")
    url = os.environ.get('STAGING_MAINTENANCE_DATABASE_URL')
    if os.environ.get('APP_ENVIRONMENT') != 'staging' or not url:
        parser.exit(1, 'Staging maintenance configuration is required.\n')
    engine = None
    try:
        engine = create_engine(url, poolclass=NullPool, hide_parameters=True,
                               isolation_level='READ COMMITTED',
                               connect_args={'connect_timeout': 10})
        if engine.dialect.name != 'postgresql': raise BootstrapRejected()
        with engine.connect() as db:
            with db.begin():
                db.execute(text("SET LOCAL lock_timeout='5s'"))
                db.execute(text("SET LOCAL statement_timeout='60s'"))
                check_target(db, args.expected_database, args.expected_role)
                if args.operation == 'migrate':
                    config = Config('alembic.ini')
                    config.attributes['connection'] = db
                    command.upgrade(config, HEAD)
                elif args.operation == "bootstrap-empty":
                    activate_empty(db)
                else:
                    from app.operations.runtime_role import provision
                    provision(db, harden_public=args.harden_public)
        print('Staging maintenance completed.')
    except Exception:
        # A lost commit acknowledgement is ambiguous: never claim rollback/retry.
        parser.exit(1, 'Maintenance not confirmed. Inspect durable state using a separately authorized session before retrying; no automatic retry was attempted.\n')
    finally:
        if engine is not None: engine.dispose()


if __name__ == '__main__':
    main()
