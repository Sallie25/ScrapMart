from functools import lru_cache
from ipaddress import ip_network
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ScrapMart API"
    app_version: str = "0.1.0"
    app_environment: str = "development"

    database_url: str | None = None
    redis_url: SecretStr = SecretStr("redis://redis:6379/0")
    signup_rate_limit_secret: SecretStr | None = None
    login_rate_limit_secret: SecretStr | None = None
    phone_otp_secret: SecretStr | None = None
    private_document_storage_backend: str = "disabled"
    private_document_storage_root: str | None = None
    private_document_storage_durable: bool = False
    auth_allowed_origins: list[str] = []
    auth_trusted_proxy_cidrs: list[str] = []

    @field_validator("auth_allowed_origins")
    @classmethod
    def exact_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"https", "http"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or "*" in value or value != value.strip()
                or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
            ):
                raise ValueError("Configure exact HTTPS origins or loopback HTTP origins")
        return values

    @field_validator("auth_trusted_proxy_cidrs")
    @classmethod
    def trusted_networks(cls, values: list[str]) -> list[str]:
        for value in values:
            if ip_network(value).prefixlen == 0:
                raise ValueError("Do not trust all proxy addresses")
        return values

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
