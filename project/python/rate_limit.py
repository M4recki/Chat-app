from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import TypedDict

from fastapi import HTTPException, Request

from .settings import settings

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

logger = logging.getLogger(__name__)


class RateLimitRule(TypedDict):
    path: str
    methods: set[str]
    scope: str
    max_requests: int
    window_seconds: int


def get_client_identifier(request: Request) -> str:
    """Resolve the best-effort client identifier from headers or socket."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    client = request.client
    if client is not None and client.host:
        return client.host
    return "unknown"


class RedisBackend:
    """Rate-limit storage backed by Redis (shared across workers)."""

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )

    async def enforce(
        self,
        bucket_key: str,
        max_requests: int,
        window_seconds: int,
    ) -> dict[str, int] | None:
        now = time.time()
        cutoff = now - window_seconds

        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.zremrangebyscore(bucket_key, "-inf", cutoff)
            await pipe.zcard(bucket_key)
            await pipe.zadd(bucket_key, {str(now): now})
            await pipe.expire(bucket_key, window_seconds * 2)
            _, count, _, _ = await pipe.execute()

        if count >= max_requests:
            oldest = await self._redis.zrange(bucket_key, 0, 0, withscores=True)
            retry_after = 0
            if oldest:
                retry_after = max(0, int(oldest[0][1] + window_seconds - now))
            reset_epoch = int(now + retry_after)
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_epoch),
                },
            )

        remaining = max_requests - (count + 1)
        reset_epoch = int(now + window_seconds)
        return {
            "limit": max_requests,
            "remaining": max(0, remaining),
            "reset": reset_epoch,
        }


class MemoryBackend:
    """In-memory rate-limit storage (per-process, not shared across workers)."""

    def __init__(self) -> None:
        self.buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    async def enforce(
        self,
        bucket_key: str,
        max_requests: int,
        window_seconds: int,
    ) -> dict[str, int] | None:
        now = time.monotonic()
        now_epoch = time.time()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self.buckets.get(bucket_key)
            if bucket is None:
                bucket = deque()
                self.buckets[bucket_key] = bucket

            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= max_requests:
                retry_after = 0
                if bucket:
                    retry_after = max(0, int(bucket[0] + window_seconds - now))
                reset_epoch = int(now_epoch + retry_after)
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_epoch),
                    },
                )

            remaining = max_requests - (len(bucket) + 1)
            bucket.append(now)

        reset_epoch = int(now_epoch + window_seconds)
        return {
            "limit": max_requests,
            "remaining": max(0, remaining),
            "reset": reset_epoch,
        }


class RateLimiter:
    """Rate limiter with optional Redis backend (falls back to in-memory)."""

    def __init__(self) -> None:
        self.backend: MemoryBackend | RedisBackend
        redis_url = settings.redis_url
        if redis_url and aioredis is not None:
            try:
                self.backend = RedisBackend(redis_url)
                logger.info("Rate limiter using Redis at %s", redis_url)
            except Exception as exc:
                logger.warning(
                    "Failed to connect to Redis (%s), falling back to in-memory",
                    exc,
                )
                self.backend = MemoryBackend()
        else:
            self.backend = MemoryBackend()
            logger.debug("Rate limiter using in-memory storage")

    async def enforce(
        self,
        request: Request,
        scope: str,
        max_requests: int,
        window_seconds: int,
        identifier: str | None = None,
    ) -> dict[str, int] | None:
        if max_requests <= 0 or window_seconds <= 0:
            return None

        identifier = identifier or get_client_identifier(request)
        bucket_key = f"{scope}:{identifier}"
        return await self.backend.enforce(bucket_key, max_requests, window_seconds)


rate_limiter = RateLimiter()


def clear_rate_limiter() -> None:
    """Reset all rate-limit buckets (used in tests)."""
    backend = rate_limiter.backend
    if isinstance(backend, MemoryBackend):
        backend.buckets.clear()


async def enforce_rate_limit(
    request: Request,
    scope: str,
    max_requests: int,
    window_seconds: int,
    identifier: str | None = None,
) -> dict[str, int] | None:
    return await rate_limiter.enforce(
        request,
        scope,
        max_requests,
        window_seconds,
        identifier=identifier,
    )
