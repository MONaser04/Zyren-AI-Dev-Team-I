"""
Circuit Breaker — Phase 3 Resilience
=====================================
Circuit breaker pattern implementation for LLM calls.

Prevents cascade failures by stopping calls to failing models/providers
and allowing time for recovery.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, calls go through
    OPEN = "open"  # Failing, calls blocked
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and call is blocked."""

    def __init__(self, circuit_name: str, retry_after: float):
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{circuit_name}' is OPEN. Retry after {retry_after:.1f}s"
        )


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes in half-open before closing
    timeout: float = 60.0  # Seconds before attempting half-open
    half_open_max_calls: int = 3  # Max calls in half-open state
    excluded_exceptions: tuple[type[Exception], ...] = ()  # Exceptions that don't count as failures


@dataclass
class CircuitBreakerStats:
    """Statistics for a circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure: datetime | None = None
    last_success: datetime | None = None
    last_state_change: datetime | None = None


class CircuitBreaker:
    """Circuit breaker for protecting against cascade failures."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float = 0
        self._lock = threading.RLock()
        self._stats = CircuitBreakerStats()
        self._callbacks: list[Callable[[str, CircuitState, CircuitState], None]] = []

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has elapsed
                if time.monotonic() - self._last_failure_time >= self.config.timeout:
                    self._transition_to_half_open()
            return self._state

    def is_available(self) -> bool:
        """Check if calls are allowed."""
        return self.state != CircuitState.OPEN

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function with circuit breaker protection."""
        if not self.is_available():
            retry_after = self.config.timeout - (time.monotonic() - self._last_failure_time)
            raise CircuitBreakerOpenError(self.name, max(0, retry_after))

        # Check half-open limit
        if self._state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    retry_after = self.config.timeout - (time.monotonic() - self._last_failure_time)
                    raise CircuitBreakerOpenError(self.name, max(0, retry_after))
                self._half_open_calls += 1

        self._stats.total_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.excluded_exceptions:
            # Don't count excluded exceptions as failures
            raise
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            self._stats.successful_calls += 1
            self._stats.last_success = datetime.now(UTC)

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to_closed()
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset failure count on success

    def _on_failure(self) -> None:
        """Handle failed call."""
        with self._lock:
            self._stats.failed_calls += 1
            self._stats.last_failure = datetime.now(UTC)
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._transition_to_open()
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to_open()

    def _transition_to_open(self) -> None:
        """Transition to OPEN state."""
        if self._state != CircuitState.OPEN:
            old_state = self._state
            self._state = CircuitState.OPEN
            self._stats.state_changes += 1
            self._stats.last_state_change = datetime.now(UTC)
            logger.warning("Circuit breaker '%s' opened after %d failures", self.name, self._failure_count)
            self._notify_callbacks(old_state, CircuitState.OPEN)

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state."""
        if self._state != CircuitState.HALF_OPEN:
            old_state = self._state
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            self._half_open_calls = 0
            self._stats.state_changes += 1
            self._stats.last_state_change = datetime.now(UTC)
            logger.info("Circuit breaker '%s' half-open (testing recovery)", self.name)
            self._notify_callbacks(old_state, CircuitState.HALF_OPEN)

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state."""
        if self._state != CircuitState.CLOSED:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._stats.state_changes += 1
            self._stats.last_state_change = datetime.now(UTC)
            logger.info("Circuit breaker '%s' closed (recovered)", self.name)
            self._notify_callbacks(old_state, CircuitState.CLOSED)

    def _notify_callbacks(self, old_state: CircuitState, new_state: CircuitState) -> None:
        """Notify registered callbacks of state change."""
        for callback in self._callbacks:
            try:
                callback(self.name, old_state, new_state)
            except Exception as e:
                logger.error("Circuit breaker callback failed: %s", e)

    def add_state_change_callback(self, callback: Callable[[str, CircuitState, CircuitState], None]) -> None:
        """Add a callback for state changes."""
        self._callbacks.append(callback)

    def get_stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        return self._stats

    def get_status(self) -> dict[str, Any]:
        """Get current status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
                "state_changes": self._stats.state_changes,
                "last_failure": self._stats.last_failure.isoformat() if self._stats.last_failure else None,
                "last_success": self._stats.last_success.isoformat() if self._stats.last_success else None,
            },
        }

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = 0
            logger.info("Circuit breaker '%s' reset", self.name)

    def force_open(self) -> None:
        """Force circuit breaker open."""
        with self._lock:
            self._transition_to_open()

    def force_close(self) -> None:
        """Force circuit breaker closed."""
        with self._lock:
            self._transition_to_closed()


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()

    def get_or_create(self, name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get circuit breaker by name."""
        return self._breakers.get(name)

    def remove(self, name: str) -> bool:
        """Remove a circuit breaker."""
        with self._lock:
            if name in self._breakers:
                del self._breakers[name]
                return True
            return False

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()

    def force_open_all(self) -> None:
        """Force all circuit breakers open."""
        for breaker in self._breakers.values():
            breaker.force_open()

    def force_close_all(self) -> None:
        """Force all circuit breakers closed."""
        for breaker in self._breakers.values():
            breaker.force_close()


# Global circuit breaker registry
_global_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CircuitBreakerRegistry()
    return _global_registry


def set_circuit_breaker_registry(registry: CircuitBreakerRegistry) -> None:
    """Set the global circuit breaker registry (for testing)."""
    global _global_registry
    _global_registry = registry