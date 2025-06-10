"""
async-cassandra: Async Python wrapper for the Cassandra Python driver.

This package provides true async/await support for Cassandra operations,
addressing performance limitations when using the official driver with
async frameworks like FastAPI.
"""

__version__ = "0.1.0"
__author__ = "AxonOps"
__email__ = "community@axonops.com"

from .cluster import AsyncCluster
from .exceptions import AsyncCassandraError, ConnectionError, QueryError
from .metrics import (
    ConnectionMetrics,
    InMemoryMetricsCollector,
    MetricsCollector,
    MetricsMiddleware,
    PrometheusMetricsCollector,
    QueryMetrics,
    create_metrics_system,
)
from .monitoring import (
    ClusterMetrics,
    ConnectionMonitor,
    HostMetrics,
    HostStatus,
    RateLimitedSession,
    create_monitored_session,
)
from .result import AsyncResultSet
from .retry_policy import AsyncRetryPolicy
from .session import AsyncCassandraSession
from .streaming import AsyncStreamingResultSet, StreamConfig, create_streaming_statement

__all__ = [
    "AsyncCassandraSession",
    "AsyncCluster",
    "AsyncCassandraError",
    "ConnectionError",
    "QueryError",
    "AsyncResultSet",
    "AsyncRetryPolicy",
    "ConnectionMonitor",
    "RateLimitedSession",
    "create_monitored_session",
    "HostStatus",
    "HostMetrics",
    "ClusterMetrics",
    "AsyncStreamingResultSet",
    "StreamConfig",
    "create_streaming_statement",
    "MetricsMiddleware",
    "MetricsCollector",
    "InMemoryMetricsCollector",
    "PrometheusMetricsCollector",
    "QueryMetrics",
    "ConnectionMetrics",
    "create_metrics_system",
]
