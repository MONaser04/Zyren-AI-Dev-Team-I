"""
Health Monitor — Phase 3 Resilience
====================================
Monitors health of LLM models and providers for alerting and automatic failover.
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


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ModelHealth:
    """Health status for a single model."""

    model: str
    provider: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: datetime = field(default_factory=lambda: datetime.now(UTC))
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_requests: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0.0
    last_error: str | None = None
    last_latency_ms: float = 0.0

    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests


@dataclass
class HealthCheckConfig:
    """Configuration for health monitoring."""

    check_interval: float = 60.0  # Seconds between health checks
    failure_threshold: int = 3  # Consecutive failures before UNHEALTHY
    success_threshold: int = 2  # Consecutive successes to recover
    latency_threshold_ms: float = 10000.0  # Latency threshold for DEGRADED
    min_requests_for_rate: int = 10  # Min requests before calculating failure rate


class HealthMonitor:
    """Monitors health of models and providers."""

    def __init__(self, config: HealthCheckConfig | None = None):
        self.config = config or HealthCheckConfig()
        self._models: dict[str, ModelHealth] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._callbacks: list[Callable[[ModelHealth], None]] = []
        self._running = False
        self._monitor_thread: threading.Thread | None = None

    def register_model(self, model: str, provider: str) -> ModelHealth:
        """Register a model for health monitoring."""
        with self._global_lock:
            if model not in self._models:
                self._models[model] = ModelHealth(model=model, provider=provider)
                self._locks[model] = threading.Lock()
            return self._models[model]

    def record_success(self, model: str, latency_ms: float) -> None:
        """Record a successful request."""
        health = self._get_or_create(model)
        with self._get_lock(model):
            health.total_requests += 1
            health.consecutive_successes += 1
            health.consecutive_failures = 0
            health.last_latency_ms = latency_ms
            health.last_error = None

            # Update average latency (exponential moving average)
            alpha = 0.1
            health.avg_latency_ms = (
                alpha * latency_ms + (1 - alpha) * health.avg_latency_ms
            )

            # Update status
            self._update_status(health)

    def record_failure(self, model: str, error: str | Exception, latency_ms: float = 0) -> None:
        """Record a failed request."""
        health = self._get_or_create(model)
        with self._get_lock(model):
            health.total_requests += 1
            health.total_failures += 1
            health.consecutive_failures += 1
            health.consecutive_successes = 0
            health.last_error = str(error)
            health.last_latency_ms = latency_ms

            self._update_status(health)

    def _get_or_create(self, model: str) -> ModelHealth:
        """Get or create health record."""
        with self._global_lock:
            if model not in self._models:
                # Extract provider from model ID (e.g., "openai/gpt-4o" -> "openai")
                provider = model.split("/")[0] if "/" in model else "unknown"
                self._models[model] = ModelHealth(model=model, provider=provider)
                self._locks[model] = threading.Lock()
            return self._models[model]

    def _get_lock(self, model: str) -> threading.Lock:
        """Get or create lock for model."""
        with self._global_lock:
            if model not in self._locks:
                self._locks[model] = threading.Lock()
            return self._locks[model]

    def _update_status(self, health: ModelHealth) -> None:
        """Update health status based on metrics."""
        old_status = health.status

        # Check for unhealthy
        if health.consecutive_failures >= self.config.failure_threshold:
            health.status = HealthStatus.UNHEALTHY
        # Check for degraded (high latency)
        elif health.avg_latency_ms >= self.config.latency_threshold_ms:
            health.status = HealthStatus.DEGRADED
        # Check for recovery
        elif health.consecutive_successes >= self.config.success_threshold:
            health.status = HealthStatus.HEALTHY
        elif health.total_requests >= self.config.min_requests_for_rate:
            if health.failure_rate() > 0.5:
                health.status = HealthStatus.UNHEALTHY
            elif health.failure_rate() > 0.1:
                health.status = HealthStatus.DEGRADED
            else:
                health.status = HealthStatus.HEALTHY

        health.last_check = datetime.now(UTC)

        # Trigger callbacks on status change
        if old_status != health.status:
            logger.warning(
                "Model %s health changed: %s -> %s",
                health.model,
                old_status.value,
                health.status.value,
            )
            for callback in self._callbacks:
                try:
                    callback(health)
                except Exception as e:
                    logger.error("Health callback failed: %s", e)

    def add_callback(self, callback: Callable[[ModelHealth], None]) -> None:
        """Add a callback for health status changes."""
        self._callbacks.append(callback)

    def get_health(self, model: str) -> ModelHealth | None:
        """Get health status for a model."""
        return self._models.get(model)

    def get_all_health(self) -> dict[str, ModelHealth]:
        """Get health status for all models."""
        return dict(self._models)

    def get_unhealthy_models(self) -> list[ModelHealth]:
        """Get all unhealthy models."""
        return [h for h in self._models.values() if h.status == HealthStatus.UNHEALTHY]

    def get_degraded_models(self) -> list[ModelHealth]:
        """Get all degraded models."""
        return [h for h in self._models.values() if h.status == HealthStatus.DEGRADED]

    def get_healthy_models(self) -> list[ModelHealth]:
        """Get all healthy models."""
        return [h for h in self._models.values() if h.status == HealthStatus.HEALTHY]

    def is_healthy(self, model: str) -> bool:
        """Check if a model is healthy."""
        health = self._models.get(model)
        if health is None:
            return True  # Unknown models assumed healthy
        return health.status == HealthStatus.HEALTHY

    def is_available(self, model: str) -> bool:
        """Check if a model is available (healthy or degraded)."""
        health = self._models.get(model)
        if health is None:
            return True
        return health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    def start_monitoring(self) -> None:
        """Start background health monitoring."""
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Health monitor started")

    def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("Health monitor stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                self._periodic_check()
            except Exception as e:
                logger.error("Error in health monitor loop: %s", e)
            time.sleep(self.config.check_interval)

    def _periodic_check(self) -> None:
        """Periodic health check - trigger callbacks for current status."""
        for health in self._models.values():
            # Trigger callbacks to keep external systems updated
            for callback in self._callbacks:
                try:
                    callback(health)
                except Exception as e:
                    logger.error("Health callback failed: %s", e)

    def get_status_summary(self) -> dict[str, Any]:
        """Get summary of all model health."""
        total = len(self._models)
        healthy = len(self.get_healthy_models())
        degraded = len(self.get_degraded_models())
        unhealthy = len(self.get_unhealthy_models())
        unknown = total - healthy - degraded - unhealthy

        return {
            "total_models": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "unknown": unknown,
            "models": {
                model: {
                    "status": health.status.value,
                    "provider": health.provider,
                    "failure_rate": round(health.failure_rate(), 4),
                    "avg_latency_ms": round(health.avg_latency_ms, 2),
                    "last_check": health.last_check.isoformat(),
                }
                for model, health in self._models.items()
            },
        }


# Global health monitor instance
_global_monitor: HealthMonitor | None = None


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = HealthMonitor()
    return _global_monitor


def set_health_monitor(monitor: HealthMonitor) -> None:
    """Set the global health monitor (for testing)."""
    global _global_monitor
    _global_monitor = monitor