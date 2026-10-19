from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ScrapMart API"
    app_version: str = "0.1.0"
    app_environment: str = "development"

    database_url: str | None = None
    redis_url: str = "redis://redis:6379/0"

    # Validated by token helpers on use, not during application/health startup.
    jwt_signing_secret: SecretStr | None = None
    jwt_issuer: str = "scrapmart-backend"
    jwt_audience: str = "scrapmart-web"
    access_token_expire_minutes: int = 15
    auth_session_expire_days: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
