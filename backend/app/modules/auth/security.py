"""Offline security primitives only: no database, HTTP, or session management.

JWT validation establishes cryptographic validity, not authorization. Stage 2B
must still load the User/session and enforce activation, revocation, ownership,
and profile/verification permissions.
"""
import base64
import binascii
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import Settings, get_settings


MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128
JWT_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ("sub", "sid", "jti", "iss", "aud", "iat", "nbf", "exp", "type")
_URLSAFE_32_BYTES = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_password_hasher = PasswordHash((Argon2Hasher(parallelism=1),))


class PasswordPolicyError(ValueError):
    """A new password does not meet the documented policy."""


class SecurityConfigurationError(RuntimeError):
    """JWT configuration is missing or unsafe; contains no secret values."""


class InvalidAccessTokenError(ValueError):
    """An access token cannot be trusted; contains no token/claim values."""


class InvalidRefreshTokenError(ValueError):
    """An opaque refresh token is not in the expected canonical format."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    token_id: uuid.UUID
    issued_at: datetime
    not_before: datetime
    expires_at: datetime


@dataclass(frozen=True)
class _TokenConfig:
    key: bytes = field(repr=False)
    issuer: str
    audience: str
    lifetime_seconds: int


def _password_input_valid(password: object) -> bool:
    if not isinstance(password, str) or not 1 <= len(password) <= MAX_PASSWORD_LENGTH:
        return False
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return "\x00" not in password


def validate_password_policy(password: str) -> None:
    """Accept 15–128 characters, Unicode/spaces, no truncation or composition rules."""
    if (
        not _password_input_valid(password)
        or len(password) < MIN_PASSWORD_LENGTH
        or password.isspace()
    ):
        raise PasswordPolicyError(
            "Use 15–128 characters, not only whitespace, without null characters."
        )


def hash_password(password: str) -> str:
    validate_password_policy(password)
    return _password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    # Minimum signup length is not reapplied to existing passwords at login.
    if not _password_input_valid(password):
        return False
    if not isinstance(stored_hash, str) or len(stored_hash) > 1024:
        return False
    try:
        return _password_hasher.verify(password, stored_hash)
    except (UnknownHashError, ValueError, TypeError):
        return False


def _decode_canonical_random_value(value: object) -> bytes:
    """Decode exactly 32 bytes represented as unpadded canonical base64url."""
    if not isinstance(value, str) or not _URLSAFE_32_BYTES.fullmatch(value):
        raise ValueError("Invalid security value format")
    try:
        decoded = base64.b64decode(value + "=", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid security value format") from None
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        raise ValueError("Invalid security value format")
    return decoded


def _token_config(settings: Settings | None) -> _TokenConfig:
    settings = settings if settings is not None else get_settings()
    secret = settings.jwt_signing_secret
    if secret is None:
        raise SecurityConfigurationError("JWT signing secret is not configured")
    try:
        key = _decode_canonical_random_value(secret.get_secret_value())
    except ValueError:
        raise SecurityConfigurationError(
            "JWT signing secret must encode 32 cryptographically random bytes"
        ) from None
    # Reject obvious repetitive keys. Random generation, not this heuristic,
    # establishes entropy; no validator can prove how an operator made a key.
    if len(set(key)) < 16:
        raise SecurityConfigurationError("JWT signing secret is too repetitive")
    if (
        not settings.jwt_issuer or settings.jwt_issuer != settings.jwt_issuer.strip()
        or not settings.jwt_audience or settings.jwt_audience != settings.jwt_audience.strip()
    ):
        raise SecurityConfigurationError("JWT issuer and audience must be nonblank and trimmed")
    lifetime = settings.access_token_expire_minutes
    if type(lifetime) is not int or not 1 <= lifetime <= 15:
        raise SecurityConfigurationError("Access-token lifetime must be 1–15 minutes")
    return _TokenConfig(key, settings.jwt_issuer, settings.jwt_audience, lifetime * 60)


def create_access_token(
    user_id: uuid.UUID, session_id: uuid.UUID, *, settings: Settings | None = None,
) -> str:
    config = _token_config(settings)
    if not isinstance(user_id, uuid.UUID) or not isinstance(session_id, uuid.UUID):
        raise ValueError("User and session identifiers must be UUIDs")
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "sub": str(user_id), "sid": str(session_id), "jti": str(uuid.uuid4()),
        "iss": config.issuer, "aud": config.audience,
        "iat": now, "nbf": now, "exp": now + config.lifetime_seconds,
        "type": "access",
    }
    return jwt.encode(claims, config.key, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str, *, settings: Settings | None = None) -> AccessTokenClaims:
    config = _token_config(settings)
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 4096:
            raise ValueError
        claims = jwt.decode(
            token, config.key, algorithms=[JWT_ALGORITHM],
            issuer=config.issuer, audience=config.audience, leeway=0,
            options={"require": list(_REQUIRED_CLAIMS), "strict_aud": True},
        )
        if claims["type"] != "access":
            raise ValueError
        identifiers = []
        for name in ("sub", "sid", "jti"):
            value = claims[name]
            if not isinstance(value, str):
                raise ValueError
            identifier = uuid.UUID(value)
            if str(identifier) != value:
                raise ValueError
            identifiers.append(identifier)
        if any(type(claims[name]) is not int for name in ("iat", "nbf", "exp")):
            raise ValueError
        if not (
            claims["iat"] <= claims["nbf"] < claims["exp"]
            and 0 < claims["exp"] - claims["iat"] <= config.lifetime_seconds
        ):
            raise ValueError
        dates = [datetime.fromtimestamp(claims[name], timezone.utc) for name in ("iat", "nbf", "exp")]
        return AccessTokenClaims(*identifiers, *dates)
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError, OSError):
        raise InvalidAccessTokenError("Invalid or expired access token") from None


def generate_refresh_token() -> str:
    """Return a 256-bit opaque token for delivery to the client, never logging it."""
    return secrets.token_urlsafe(32)


def digest_refresh_token(token: str) -> bytes:
    """Validate format, then return the 32-byte SHA-256 digest used by Stage 1."""
    try:
        _decode_canonical_random_value(token)
    except ValueError:
        raise InvalidRefreshTokenError("Invalid refresh-token format") from None
    return hashlib.sha256(token.encode("ascii")).digest()
