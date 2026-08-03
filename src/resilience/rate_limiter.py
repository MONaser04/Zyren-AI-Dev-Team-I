"""
Rate Limiter — Phase 3 Resilience
==================================
Token bucket rate limiter for per-provider and per-model rate limiting.

Supports both requests-per-minute (RPM) and tokens-per-minute (TPM) limits.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, model: str, limit_type: str, retry_after: float):
        self.model = model
        self.limit_type = limit_type
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for {model}: {limit_type}. Retry after {retry_after:.1f}s"
        )


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(default=0.0, init=False)
    last_refill: float = field(default=0.0, init=False)

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time until enough tokens are available."""
        self._refill()
        if self.tokens >= tokens:
            return 0.0
        return (tokens - self.tokens) / self.refill_rate

    def get_available(self) -> int:
        """Get currently available tokens."""
        self._refill()
        return int(self.tokens)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a model."""

    rpm: int | None = None  # Requests per minute
    tpm: int | None = None  # Tokens per minute
    rpd: int | None = None  # Requests per day


class RateLimiter:
    """Manages rate limits for multiple models/providers."""

    def __init__(self):
        self._buckets: dict[str, dict[str, TokenBucket]] = {}  # model -> {limit_type: bucket}
        self._locks: dict[str, threading.Lock] = {}
        self._default_configs: dict[str, RateLimitConfig] = {}
        self._global_lock = threading.Lock()

    def set_limits(self, model: str, config: RateLimitConfig) -> None:
        """Set rate limits for a model."""
        with self._global_lock:
            self._default_configs[model] = config
            # Initialize buckets
            if model not in self._buckets:
                self._buckets[model] = {}
            if model not in self._locks:
                self._locks[model] = threading.Lock()

            if config.rpm is not None:
                self._buckets[model]["rpm"] = TokenBucket(
                    capacity=config.rpm,
                    refill_rate=config.rpm / 60.0,
                )
            if config.tpm is not None:
                self._buckets[model]["tpm"] = TokenBucket(
                    capacity=config.tpm,
                    refill_rate=config.tpm / 60.0,
                )
            if config.rpd is not None:
                self._buckets[model]["rpd"] = TokenBucket(
                    capacity=config.rpd,
                    refill_rate=config.rpd / 86400.0,
                )

    async def acquire(
        self,
        model: str,
        tokens: int = 1,
        timeout: float | None = None,
    ) -> None:
        """Acquire permission to make a request.

        Args:
            model: Model identifier
            tokens: Number of tokens this request will use
            timeout: Max time to wait (None = wait indefinitely)

        Raises:
            RateLimitExceeded: If timeout is 0 and limit would be exceeded
        """
        # Get or create lock for this model
        lock = self._locks.get(model)
        if lock is None:
            with self._global_lock:
                if model not in self._locks:
                    self._locks[model] = threading.Lock()
                lock = self._locks[model]

        start_time = time.monotonic()

        while True:
            with lock:
                buckets = self._buckets.get(model, {})
                if not buckets:
                    # No limits configured, allow
                    return

                # Check all limits
                can_acquire = True
                max_wait = 0.0

                for limit_type, bucket in buckets.items():
                    if not bucket.consume(1 if limit_type == "rpm" else tokens):
                        can_acquire = False
                        wait = bucket.get_wait_time(1 if limit_type == "rpm" else tokens)
                        max_wait = max(max_wait, wait)

                if can_acquire:
                    return

                if timeout == 0:
                    raise RateLimitExceeded(model, "rate limit", max_wait)

                if timeout is not None and (time.monotonic() - start_time) >= timeout:
                    raise RateLimitExceeded(model, "rate limit timeout", max_wait)

            # Wait outside the lock
            wait_time = min(max_wait, 1.0)  # Cap wait to 1s to recheck
            await asyncio.sleep(wait_time)

    def get_status(self, model: str) -> dict[str, Any]:
        """Get current rate limit status for a model."""
        buckets = self._buckets.get(model, {})
        status = {}
        for limit_type, bucket in buckets.items():
            bucket._refill()
            status[limit_type] = {
                "available": int(bucket.tokens),
                "capacity": bucket.capacity,
                "refill_rate": bucket.refill_rate,
            }
        return status

    def reset(self, model: str) -> None:
        """Reset all buckets for a model."""
        with self._global_lock:
            if model in self._buckets:
                for bucket in self._buckets[model].values():
                    bucket.tokens = float(bucket.capacity)
                    bucket.last_refill = time.monotonic()
                logger.info("Rate limits reset for model %s", model)

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all models."""
        return {model: self.get_status(model) for model in self._buckets}


# Global rate limiter instance
_global_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter()
    return _global_limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Set the global rate limiter (for testing)."""
    global _global_limiter
    _global_limiter = limiter