"""
async-cassandra: Async Python wrapper for the DataStax Cassandra driver.

This package provides true async/await support for Cassandra operations,
addressing performance limitations when using the official driver with
async frameworks like FastAPI.
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .cluster import AsyncCluster
from .exceptions import AsyncCassandraError, ConnectionError, QueryError
from .result import AsyncResultSet
from .retry_policy import AsyncRetryPolicy
from .session import AsyncCassandraSession

__all__ = [
    "AsyncCassandraSession",
    "AsyncCluster",
    "AsyncCassandraError",
    "ConnectionError",
    "QueryError",
    "AsyncResultSet",
    "AsyncRetryPolicy",
]
