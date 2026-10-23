"""Shared fixed-window Redis counters, with signup defaults and fail-closed errors."""
import base64
import hashlib
import hmac
from functools import lru_cache

from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.core.config import get_settings

# One key per invocation: compatible with Redis Cluster as well as standalone.
# The first attempt anchors the window. Blocked attempts never extend it.
COUNTER_SCRIPT = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = redis.call('TTL', KEYS[1])
if count >= tonumber(ARGV[1]) then
    if ttl < 0 then return redis.error_reply('Invalid counter expiry') end
    return {0, ttl}
end
count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
local remaining = redis.call('TTL', KEYS[1])
if remaining < 0 then return redis.error_reply('Invalid counter expiry') end
return {1, remaining}
"""


class RateLimitUnavailableError(RuntimeError):
    pass


class SignupRateLimitedError(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__("Too many registration attempts")


class SignupRateLimiter:
    namespace = "signup"
    limits = {"email": 5, "ip": 20}
    window_seconds = 3600

    def __init__(self, client: Redis, secret: bytes) -> None:
        if len(secret) != 32 or len(set(secret)) < 16:
            raise RateLimitUnavailableError("Rate limiter is not configured")
        self._client = client
        self._secret = secret

    def check(self, kind: str, value: str) -> None:
        digest = hmac.new(self._secret, (kind + "\0" + value).encode("utf-8"), hashlib.sha256).hexdigest()
        key = f"scrapmart:{self.namespace}:{kind}:{digest}"
        try:
            allowed, ttl = self._client.eval(COUNTER_SCRIPT, 1, key, self.limits[kind], self.window_seconds)
            if allowed not in (0, 1) or not isinstance(ttl, int) or not 0 <= ttl <= self.window_seconds:
                raise RateLimitUnavailableError("Rate limiter is unavailable")
        except (RedisError, OSError, ValueError, TypeError):
            raise RateLimitUnavailableError("Rate limiter is unavailable") from None
        if not allowed:
            raise SignupRateLimitedError(ttl)


@lru_cache
def get_signup_rate_limiter() -> SignupRateLimiter:
    settings = get_settings()
    return configured_rate_limiter(SignupRateLimiter, settings.signup_rate_limit_secret, settings)


def configured_rate_limiter(limiter_type, configured_secret, settings) -> SignupRateLimiter:
    """Shared Redis construction and secret validation; never connects on import."""
    try:
        if configured_secret is None:
            raise ValueError
        encoded = configured_secret.get_secret_value()
        secret = base64.b64decode(encoded + "=", altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(secret).decode().rstrip("=") != encoded:
            raise ValueError
        if len(secret) != 32 or len(set(secret)) < 16:
            raise ValueError
        client = Redis.from_url(
            settings.redis_url.get_secret_value(), socket_timeout=1,
            socket_connect_timeout=1, retry=Retry(NoBackoff(), 0),
        )
        return limiter_type(client, secret)
    except (ValueError, TypeError, RedisError):
        raise RateLimitUnavailableError("Rate limiter is not configured") from None
