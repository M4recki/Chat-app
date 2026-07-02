import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import make_request
from fastapi import HTTPException

from project.python.rate_limit import (
    MemoryBackend,
    RateLimiter,
    RedisBackend,
    get_client_identifier,
)
from project.python.settings import settings as app_settings

#  RateLimiter.get_client_identifier


def test_rate_limiter_get_client_identifier_x_forwarded_for():
    request = make_request([(b"x-forwarded-for", b"203.0.113.42, 10.0.0.1")])
    assert get_client_identifier(request) == "203.0.113.42"


def test_rate_limiter_get_client_identifier_fallback_host():
    request = make_request(host="10.0.0.55")
    assert get_client_identifier(request) == "10.0.0.55"


def test_rate_limiter_get_client_identifier_no_client():
    request = make_request(host=None)
    assert get_client_identifier(request) == "unknown"


#  RateLimiter.enforce edge cases


@pytest.mark.asyncio
async def test_rate_limiter_enforce_zero_max_requests():
    limiter = RateLimiter()
    request = make_request()
    result = await limiter.enforce(request, "test", 0, 60)

    assert result is None


@pytest.mark.asyncio
async def test_rate_limiter_enforce_negative_window():
    limiter = RateLimiter()
    request = make_request()
    result = await limiter.enforce(request, "test", 5, -1)

    assert result is None


@pytest.mark.asyncio
async def test_rate_limiter_enforce_bucket_cleanup():
    limiter = RateLimiter()
    backend = limiter.backend

    assert isinstance(backend, MemoryBackend)
    backend.buckets["cleanup:127.0.0.1"] = deque(
        [
            time.monotonic() - 120,
            time.monotonic() - 100,
        ]
    )
    request = make_request()
    result = await limiter.enforce(request, "cleanup", 5, 30)
    assert result is not None
    assert result["remaining"] >= 3


# ---------------------------------------------------------------------------
# RedisBackend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_backend_enforce_under_limit(monkeypatch):
    mock_redis = MagicMock()
    mock_pipe = AsyncMock()
    mock_pipe.__aenter__.return_value = mock_pipe
    mock_pipe.execute.return_value = (0, 1, 1, True)
    mock_redis.pipeline.return_value = mock_pipe
    monkeypatch.setattr(
        "project.python.rate_limit.aioredis.from_url",
        lambda url, **kw: mock_redis,
    )

    backend = RedisBackend("redis://localhost:6379/0")
    result = await backend.enforce("test:bucket", 5, 60)

    assert result["remaining"] == 3
    assert result["limit"] == 5
    assert result["reset"] > 0


@pytest.mark.asyncio
async def test_redis_backend_enforce_over_limit(monkeypatch):
    mock_redis = MagicMock()
    mock_pipe = AsyncMock()
    mock_pipe.__aenter__.return_value = mock_pipe
    mock_pipe.execute.return_value = (0, 5, 1, True)
    mock_redis.pipeline.return_value = mock_pipe
    mock_redis.zrange = AsyncMock(return_value=[(b"1234567890", 1234567890.0)])
    monkeypatch.setattr(
        "project.python.rate_limit.aioredis.from_url",
        lambda url, **kw: mock_redis,
    )

    backend = RedisBackend("redis://localhost:6379/0")
    with pytest.raises(HTTPException) as exc:
        await backend.enforce("test:bucket", 5, 60)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limiter_redis_connection_error_falls_to_memory(monkeypatch):
    monkeypatch.setattr(app_settings, "redis_url", "redis://localhost:6379/0")
    monkeypatch.setattr(
        "project.python.rate_limit.aioredis.from_url",
        lambda url, **kw: (_ for _ in ()).throw(ConnectionError("timeout")),
    )

    limiter = RateLimiter()
    assert isinstance(limiter.backend, MemoryBackend)
