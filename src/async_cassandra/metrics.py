"""
Metrics and observability system for async-cassandra.

This module provides comprehensive monitoring capabilities including:
- Query performance metrics
- Connection health tracking
- Error rate monitoring
- Custom metrics collection
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Metrics for individual query execution."""

    query_hash: str
    duration: float
    success: bool
    error_type: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    parameters_count: int = 0
    result_size: int = 0


@dataclass
class ConnectionMetrics:
    """Metrics for connection health."""

    host: str
    is_healthy: bool
    last_check: datetime
    response_time: float
    error_count: int = 0
    total_queries: int = 0


class MetricsCollector(ABC):
    """Abstract base class for metrics collection backends."""

    @abstractmethod
    async def record_query(self, metrics: QueryMetrics) -> None:
        """Record query execution metrics."""
        pass

    @abstractmethod
    async def record_connection_health(self, metrics: ConnectionMetrics) -> None:
        """Record connection health metrics."""
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics."""
        pass


class InMemoryMetricsCollector(MetricsCollector):
    """In-memory metrics collector for development and testing."""

    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        self.query_metrics: deque = deque(maxlen=max_entries)
        self.connection_metrics: Dict[str, ConnectionMetrics] = {}
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.query_counts: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def record_query(self, metrics: QueryMetrics) -> None:
        """Record query execution metrics."""
        async with self._lock:
            self.query_metrics.append(metrics)
            self.query_counts[metrics.query_hash] += 1

            if not metrics.success and metrics.error_type:
                self.error_counts[metrics.error_type] += 1

    async def record_connection_health(self, metrics: ConnectionMetrics) -> None:
        """Record connection health metrics."""
        async with self._lock:
            self.connection_metrics[metrics.host] = metrics

    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics."""
        async with self._lock:
            if not self.query_metrics:
                return {"message": "No metrics available"}

            # Calculate performance stats
            recent_queries = [
                q
                for q in self.query_metrics
                if q.timestamp > datetime.utcnow() - timedelta(minutes=5)
            ]

            if recent_queries:
                durations = [q.duration for q in recent_queries]
                success_rate = sum(1 for q in recent_queries if q.success) / len(recent_queries)

                stats = {
                    "query_performance": {
                        "total_queries": len(self.query_metrics),
                        "recent_queries_5min": len(recent_queries),
                        "avg_duration_ms": sum(durations) / len(durations) * 1000,
                        "min_duration_ms": min(durations) * 1000,
                        "max_duration_ms": max(durations) * 1000,
                        "success_rate": success_rate,
                        "queries_per_second": len(recent_queries) / 300,  # 5 minutes
                    },
                    "error_summary": dict(self.error_counts),
                    "top_queries": dict(
                        sorted(self.query_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                    ),
                    "connection_health": {
                        host: {
                            "healthy": metrics.is_healthy,
                            "response_time_ms": metrics.response_time * 1000,
                            "error_count": metrics.error_count,
                            "total_queries": metrics.total_queries,
                        }
                        for host, metrics in self.connection_metrics.items()
                    },
                }
            else:
                stats = {
                    "query_performance": {"message": "No recent queries"},
                    "error_summary": dict(self.error_counts),
                    "top_queries": {},
                    "connection_health": {},
                }

            return stats


class PrometheusMetricsCollector(MetricsCollector):
    """Prometheus metrics collector for production monitoring."""

    query_duration: Optional["Histogram"]
    query_total: Optional["Counter"]
    connection_health: Optional["Gauge"]
    error_total: Optional["Counter"]
    _available: bool

    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Gauge, Histogram

            self.query_duration = Histogram(
                "cassandra_query_duration_seconds",
                "Time spent executing Cassandra queries",
                ["query_type", "success"],
            )
            self.query_total = Counter(
                "cassandra_queries_total",
                "Total number of Cassandra queries",
                ["query_type", "success"],
            )
            self.connection_health = Gauge(
                "cassandra_connection_healthy", "Whether Cassandra connection is healthy", ["host"]
            )
            self.error_total = Counter(
                "cassandra_errors_total", "Total number of Cassandra errors", ["error_type"]
            )
            self._available = True
        except ImportError:
            logger.warning("prometheus_client not available, metrics disabled")
            self._available = False

    async def record_query(self, metrics: QueryMetrics) -> None:
        """Record query execution metrics to Prometheus."""
        if not self._available:
            return

        query_type = "prepared" if "prepared" in metrics.query_hash else "simple"
        success_label = "success" if metrics.success else "failure"

        if self.query_duration is not None:
            self.query_duration.labels(query_type=query_type, success=success_label).observe(
                metrics.duration
            )

        if self.query_total is not None:
            self.query_total.labels(query_type=query_type, success=success_label).inc()

        if not metrics.success and metrics.error_type and self.error_total is not None:
            self.error_total.labels(error_type=metrics.error_type).inc()

    async def record_connection_health(self, metrics: ConnectionMetrics) -> None:
        """Record connection health to Prometheus."""
        if not self._available:
            return

        if self.connection_health is not None:
            self.connection_health.labels(host=metrics.host).set(1 if metrics.is_healthy else 0)

    async def get_stats(self) -> Dict[str, Any]:
        """Get current Prometheus metrics."""
        if not self._available:
            return {"error": "Prometheus client not available"}

        return {"message": "Metrics available via Prometheus endpoint"}


class MetricsMiddleware:
    """Middleware to automatically collect metrics for async-cassandra operations."""

    def __init__(self, collectors: List[MetricsCollector]):
        self.collectors = collectors
        self._enabled = True

    def enable(self) -> None:
        """Enable metrics collection."""
        self._enabled = True

    def disable(self) -> None:
        """Disable metrics collection."""
        self._enabled = False

    async def record_query_metrics(
        self,
        query: str,
        duration: float,
        success: bool,
        error_type: Optional[str] = None,
        parameters_count: int = 0,
        result_size: int = 0,
    ) -> None:
        """Record metrics for a query execution."""
        if not self._enabled:
            return

        # Create a hash of the query for grouping (remove parameter values)
        query_hash = self._normalize_query(query)

        metrics = QueryMetrics(
            query_hash=query_hash,
            duration=duration,
            success=success,
            error_type=error_type,
            parameters_count=parameters_count,
            result_size=result_size,
        )

        # Send to all collectors
        for collector in self.collectors:
            try:
                await collector.record_query(metrics)
            except Exception as e:
                logger.warning(f"Failed to record metrics: {e}")

    async def record_connection_metrics(
        self,
        host: str,
        is_healthy: bool,
        response_time: float,
        error_count: int = 0,
        total_queries: int = 0,
    ) -> None:
        """Record connection health metrics."""
        if not self._enabled:
            return

        metrics = ConnectionMetrics(
            host=host,
            is_healthy=is_healthy,
            last_check=datetime.utcnow(),
            response_time=response_time,
            error_count=error_count,
            total_queries=total_queries,
        )

        for collector in self.collectors:
            try:
                await collector.record_connection_health(metrics)
            except Exception as e:
                logger.warning(f"Failed to record connection metrics: {e}")

    def _normalize_query(self, query: str) -> str:
        """Normalize query for grouping by removing parameter values."""
        import hashlib
        import re

        # Remove extra whitespace and normalize
        normalized = re.sub(r"\s+", " ", query.strip().upper())

        # Replace parameter placeholders with generic markers
        normalized = re.sub(r"\?", "?", normalized)
        normalized = re.sub(r"'[^']*'", "'?'", normalized)  # String literals
        normalized = re.sub(r"\b\d+\b", "?", normalized)  # Numbers

        # Create a hash for storage efficiency
        return hashlib.md5(normalized.encode()).hexdigest()[:12]


# Decorators for easy metrics integration
def with_metrics(middleware: MetricsMiddleware) -> Callable:
    """Decorator to add metrics to async functions."""

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = False
            error_type = None

            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error_type = type(e).__name__
                raise
            finally:
                duration = time.perf_counter() - start_time
                query = kwargs.get("query", str(args[1]) if len(args) > 1 else "unknown")

                await middleware.record_query_metrics(
                    query=query, duration=duration, success=success, error_type=error_type
                )

        return wrapper

    return decorator


# Factory function for easy setup
def create_metrics_system(
    backend: str = "memory", prometheus_enabled: bool = False
) -> MetricsMiddleware:
    """Create a metrics system with specified backend."""
    collectors: List[MetricsCollector] = []

    if backend == "memory":
        collectors.append(InMemoryMetricsCollector())

    if prometheus_enabled:
        collectors.append(PrometheusMetricsCollector())

    return MetricsMiddleware(collectors)
