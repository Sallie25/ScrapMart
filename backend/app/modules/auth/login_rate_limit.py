"""Login-specific budgets using the existing atomic Redis counter architecture."""
from functools import lru_cache

from app.core.config import get_settings
from app.modules.auth.signup_rate_limit import SignupRateLimiter, configured_rate_limiter


class BuyerLoginRateLimiter(SignupRateLimiter):
    namespace = "login"
    limits = {"email": 10, "ip": 30}
    window_seconds = 900


@lru_cache
def get_login_rate_limiter() -> BuyerLoginRateLimiter:
    settings = get_settings()
    return configured_rate_limiter(BuyerLoginRateLimiter, settings.login_rate_limit_secret, settings)
