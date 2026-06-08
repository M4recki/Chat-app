from __future__ import annotations

import threading
import time
from collections import deque
from typing import TypedDict

from fastapi import HTTPException, Request


class RateLimitRule(TypedDict):
    """Configuration for a single rate limit rule.

    Attributes:
        path: URL path to match
        methods: HTTP methods to match
        scope: Unique scope name for the rule
        max_requests: Maximum number of requests allowed
        window_seconds: Time window in seconds
    """

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

    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RateLimiter:
    """In-memory sliding-window limiter keyed by scope and identifier."""

    def __init__(self) -> None:
        """Initialize the bucket store and lock."""
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def enforce(
        self,
        request: Request,
        scope: str,
        max_requests: int,
        window_seconds: int,
        identifier: str | None = None,
    ) -> dict[str, int] | None:
        """Enforce a rate limit and return metadata for response headers.

        Raises HTTPException(429) when the limit is exceeded.
        """
        if max_requests <= 0 or window_seconds <= 0:
            return None

        now = time.monotonic()
        now_epoch = time.time()
        cutoff = now - window_seconds
        identifier = identifier or get_client_identifier(request)
        bucket_key = f"{scope}:{identifier}"

        with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = deque()
                self._buckets[bucket_key] = bucket

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


rate_limiter = RateLimiter()


def enforce_rate_limit(
    request: Request,
    scope: str,
    max_requests: int,
    window_seconds: int,
    identifier: str | None = None,
) -> dict[str, int] | None:
    """Convenience wrapper for enforcing a rate limit using the singleton."""
    return rate_limiter.enforce(
        request,
        scope,
        max_requests,
        window_seconds,
        identifier=identifier,
    )
