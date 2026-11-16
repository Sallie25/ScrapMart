"""Opt-in Lua checks against the existing private local Redis container only."""
import json
import os
import secrets
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.modules.auth.signup_rate_limit import COUNTER_SCRIPT, SignupRateLimitedError, SignupRateLimiter

pytestmark = pytest.mark.skipif(
    os.environ.get("SCRAPMART_RUN_LOCAL_REDIS_TESTS") != "1",
    reason="Requires explicit existing local Redis opt-in",
)


@pytest.fixture
def local_redis():
    inspected = subprocess.run([
        "docker", "inspect", "scrapmart-redis", "--format",
        '{{json .Name}}\n{{json .Config.Image}}\n{{json .State.Status}}\n{{json .NetworkSettings.Ports}}\n{{json .NetworkSettings.Networks}}',
    ], capture_output=True, text=True, check=True, timeout=10)
    name, image, status, ports, networks = map(json.loads, inspected.stdout.splitlines())
    assert name == "/scrapmart-redis" and image == "redis:7.4-alpine" and status == "running"
    assert ports == {"6379/tcp": None}, "Stop: Redis must not have a published port"
    assert len(networks) == 1
    address = next(iter(networks.values()))["IPAddress"]
    assert address, "Container has no IP"
    client = Redis(host=address, port=6379, db=0, socket_connect_timeout=2,
                   socket_timeout=2, retry=Retry(NoBackoff(), 0))
    assert client.ping()
    assert client.info("server")["redis_version"].startswith("7.4.")
    prefix = "stage2c_validation:" + secrets.token_hex(16) + ":"
    keys = set()

    class NamespacedRedis:
        def eval(self, script, number, key, limit, window):
            key = prefix + key
            keys.add(key)
            return client.eval(script, number, key, limit, window)

    try:
        yield client, NamespacedRedis(), keys, prefix
    finally:
        if keys:
            client.delete(*keys)
            assert not any(client.exists(key) for key in keys)
        client.close()


@pytest.mark.parametrize("kind,limit", [("email", 5), ("ip", 20)])
def test_atomic_limits_across_independent_workers(local_redis, kind, limit):
    client, wrapped, keys, _ = local_redis
    secret = secrets.token_bytes(32)
    workers = [SignupRateLimiter(wrapped, secret), SignupRateLimiter(wrapped, secret)]
    def attempt(index):
        try:
            workers[index % 2].check(kind, "example@example.test" if kind == "email" else "192.0.2.1")
            return True
        except SignupRateLimitedError:
            return False
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(attempt, range(limit * 2)))
    assert sum(outcomes) == limit
    assert len(keys) == 1
    key = next(iter(keys))
    assert client.get(key) == str(limit).encode()
    assert 0 < client.ttl(key) <= 3600
    assert "example@example.test" not in key and "192.0.2.1" not in key


def test_lua_expiry_and_window_reset(local_redis):
    client, wrapped, keys, _ = local_redis
    assert wrapped.eval(COUNTER_SCRIPT, 1, "expiry", 1, 1)[0] == 1
    key = next(iter(keys))
    before = client.pttl(key)
    assert wrapped.eval(COUNTER_SCRIPT, 1, "expiry", 1, 1)[0] == 0
    assert 0 < client.pttl(key) <= before
    time.sleep(1.1)
    assert wrapped.eval(COUNTER_SCRIPT, 1, "expiry", 1, 1)[0] == 1
