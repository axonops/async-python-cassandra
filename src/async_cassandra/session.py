"""
Async session management for Cassandra connections.
"""

import asyncio
import time
from typing import Any, Dict, Optional

from cassandra import InvalidRequest, OperationTimedOut, ReadTimeout, Unavailable, WriteTimeout
from cassandra.cluster import _NOT_SET, EXEC_PROFILE_DEFAULT, Cluster, Session
from cassandra.query import BatchStatement, PreparedStatement, SimpleStatement

from .base import AsyncCloseable, AsyncContextManageable
from .exceptions import ConnectionError, QueryError
from .metrics import MetricsMiddleware
from .result import AsyncResultHandler, AsyncResultSet
from .streaming import AsyncStreamingResultSet, StreamingResultHandler


class AsyncCassandraSession(AsyncCloseable, AsyncContextManageable):
    """
    Async wrapper for Cassandra Session.

    Provides async/await interface for executing CQL queries against Cassandra.
    """

    def __init__(self, session: Session, metrics: Optional[MetricsMiddleware] = None):
        """
        Initialize async session wrapper.

        Args:
            session: The underlying Cassandra session.
            metrics: Optional metrics middleware for observability.
        """
        super().__init__()
        self._session = session
        self._metrics = metrics

    @classmethod
    async def create(
        cls, cluster: Cluster, keyspace: Optional[str] = None
    ) -> "AsyncCassandraSession":
        """
        Create a new async session.

        Args:
            cluster: The Cassandra cluster to connect to.
            keyspace: Optional keyspace to use.

        Returns:
            New AsyncCassandraSession instance.
        """
        loop = asyncio.get_event_loop()

        # Connect in executor to avoid blocking
        session = await loop.run_in_executor(
            None, lambda: cluster.connect(keyspace) if keyspace else cluster.connect()
        )

        return cls(session)

    async def execute(
        self,
        query: Any,
        parameters: Any = None,
        trace: bool = False,
        custom_payload: Any = None,
        timeout: Any = None,
        execution_profile: Any = EXEC_PROFILE_DEFAULT,
        paging_state: Any = None,
        host: Any = None,
        execute_as: Any = None,
    ) -> AsyncResultSet:
        """
        Execute a CQL query asynchronously.

        Args:
            query: The query to execute.
            parameters: Query parameters.
            trace: Whether to enable query tracing.
            custom_payload: Custom payload to send with the request.
            timeout: Query timeout in seconds or _NOT_SET.
            execution_profile: Execution profile name or object to use.
            paging_state: Paging state for resuming paged queries.
            host: Specific host to execute query on.
            execute_as: User to execute the query as.

        Returns:
            AsyncResultSet containing query results.

        Raises:
            QueryError: If query execution fails.
        """
        if self.is_closed:
            raise ConnectionError("Session is closed")

        # Start metrics timing
        start_time = time.perf_counter()
        success = False
        error_type = None
        result_size = 0

        try:
            # Fix timeout handling - use _NOT_SET if timeout is None
            response_future = self._session.execute_async(
                query,
                parameters,
                trace,
                custom_payload,
                timeout if timeout is not None else _NOT_SET,
                execution_profile,
                paging_state,
                host,
                execute_as,
            )

            handler = AsyncResultHandler(response_future)
            result = await handler.get_result()

            success = True
            result_size = len(result.rows) if hasattr(result, "rows") else 0
            return result

        except (InvalidRequest, Unavailable, ReadTimeout, WriteTimeout, OperationTimedOut) as e:
            # Re-raise Cassandra exceptions without wrapping
            error_type = type(e).__name__
            raise
        except Exception as e:
            # Only wrap non-Cassandra exceptions
            error_type = type(e).__name__
            raise QueryError(f"Query execution failed: {str(e)}") from e
        finally:
            # Record metrics if middleware is available
            if self._metrics:
                duration = time.perf_counter() - start_time
                query_str = (
                    str(query) if isinstance(query, (SimpleStatement, PreparedStatement)) else query
                )
                params_count = len(parameters) if parameters else 0

                await self._metrics.record_query_metrics(
                    query=query_str,
                    duration=duration,
                    success=success,
                    error_type=error_type,
                    parameters_count=params_count,
                    result_size=result_size,
                )

    async def execute_stream(
        self,
        query: Any,
        parameters: Any = None,
        stream_config: Any = None,
        trace: bool = False,
        custom_payload: Any = None,
        timeout: Any = None,
        execution_profile: Any = EXEC_PROFILE_DEFAULT,
        paging_state: Any = None,
        host: Any = None,
        execute_as: Any = None,
    ) -> AsyncStreamingResultSet:
        """
        Execute a CQL query with streaming support for large result sets.

        This method is memory-efficient for queries that return many rows,
        as it fetches results page by page instead of loading everything
        into memory at once.

        Args:
            query: The query to execute.
            parameters: Query parameters.
            stream_config: Configuration for streaming (fetch size, callbacks, etc.)
            trace: Whether to enable query tracing.
            custom_payload: Custom payload to send with the request.
            timeout: Query timeout in seconds or _NOT_SET.
            execution_profile: Execution profile name or object to use.
            paging_state: Paging state for resuming paged queries.
            host: Specific host to execute query on.
            execute_as: User to execute the query as.

        Returns:
            AsyncStreamingResultSet for memory-efficient iteration.

        Raises:
            QueryError: If query execution fails.

        Example:
            # Stream through large result set
            async for row in await session.execute_stream(
                "SELECT * FROM large_table",
                stream_config=StreamConfig(fetch_size=5000)
            ):
                process_row(row)

            # Or process by pages
            result = await session.execute_stream("SELECT * FROM large_table")
            async for page in result.pages():
                process_batch(page)
        """
        if self.is_closed:
            raise ConnectionError("Session is closed")

        try:
            response_future = self._session.execute_async(
                query,
                parameters,
                trace,
                custom_payload,
                timeout if timeout is not None else _NOT_SET,
                execution_profile,
                paging_state,
                host,
                execute_as,
            )

            handler = StreamingResultHandler(response_future, stream_config)
            return await handler.get_streaming_result()
        except (InvalidRequest, Unavailable, ReadTimeout, WriteTimeout, OperationTimedOut) as e:
            raise QueryError(f"Streaming query execution failed: {str(e)}") from e

    async def execute_batch(
        self,
        batch_statement: BatchStatement,
        trace: bool = False,
        custom_payload: Optional[Dict[str, bytes]] = None,
        timeout: Any = None,
        execution_profile: Any = EXEC_PROFILE_DEFAULT,
    ) -> AsyncResultSet:
        """
        Execute a batch statement asynchronously.

        Args:
            batch_statement: The batch statement to execute.
            trace: Whether to enable query tracing.
            custom_payload: Custom payload to send with the request.
            timeout: Query timeout in seconds.
            execution_profile: Execution profile to use.

        Returns:
            AsyncResultSet (usually empty for batch operations).

        Raises:
            QueryError: If batch execution fails.
        """
        return await self.execute(
            batch_statement,
            trace=trace,
            custom_payload=custom_payload,
            timeout=timeout if timeout is not None else _NOT_SET,
            execution_profile=execution_profile,
        )

    async def prepare(self, query: str, custom_payload: Any = None) -> PreparedStatement:
        """
        Prepare a CQL statement asynchronously.

        Args:
            query: The query to prepare.
            custom_payload: Custom payload to send with the request.

        Returns:
            PreparedStatement that can be executed multiple times.

        Raises:
            QueryError: If statement preparation fails.
        """
        if self.is_closed:
            raise ConnectionError("Session is closed")

        try:
            loop = asyncio.get_event_loop()

            # Prepare in executor to avoid blocking
            prepared = await loop.run_in_executor(
                None, lambda: self._session.prepare(query, custom_payload)
            )

            return prepared
        except (InvalidRequest, OperationTimedOut) as e:
            raise QueryError(f"Statement preparation failed: {str(e)}") from e
        except Exception as e:
            raise QueryError(f"Statement preparation failed: {str(e)}") from e

    async def _do_close(self) -> None:
        """Perform the actual session shutdown."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._session.shutdown)

    @property
    def keyspace(self) -> Optional[str]:
        """Get current keyspace."""
        keyspace = self._session.keyspace
        return keyspace if isinstance(keyspace, str) else None

    async def set_keyspace(self, keyspace: str) -> None:
        """
        Set the current keyspace.

        Args:
            keyspace: The keyspace to use.

        Raises:
            QueryError: If setting keyspace fails.
            ValueError: If keyspace name is invalid.
        """
        # Validate keyspace name to prevent injection attacks
        if not keyspace or not all(c.isalnum() or c == "_" for c in keyspace):
            raise ValueError(
                f"Invalid keyspace name: '{keyspace}'. "
                "Keyspace names must contain only alphanumeric characters and underscores."
            )

        await self.execute(f"USE {keyspace}")
