"""Offline source, startup and migration-chain checks; no environment secrets."""
import ast
from pathlib import Path
from unittest.mock import patch
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from app.core.config import Settings


def main():
    for path in Path('app').rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    settings = Settings(_env_file=None, _secrets_dir=None, app_environment='staging',
                        database_url=None, jwt_signing_secret=None,
                        signup_rate_limit_secret=None, login_rate_limit_secret=None,
                        phone_otp_secret=None, listing_photo_storage_factory=None,
                        sms_delivery_factory=None, auth_allowed_origins=[],
                        auth_trusted_proxy_cidrs=[], private_document_storage_backend='disabled')
    with patch('app.core.config.get_settings', return_value=settings):
        from app.main import create_app
        with TestClient(create_app()) as client:
            assert client.get('/api/v1/health').status_code == 200
    scripts = ScriptDirectory.from_config(Config('alembic.ini'))
    assert scripts.get_heads() == ['c28fa4567def']
    assert len(list(scripts.walk_revisions())) == 11
    print('Source, secret-free startup and single-head migration checks passed.')


if __name__ == '__main__':
    main()
