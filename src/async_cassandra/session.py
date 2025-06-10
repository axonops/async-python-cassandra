"""
Async session management for Cassandra connections.
"""

import asyncio
import time
from typing import Dict, List, Optional, Union, Any

from cassandra import (
    InvalidRequest,
    OperationTimedOut,
    ReadTimeout,
    Unavailable,
    WriteTimeout,
)
from cassandra.cluster import _NOT_SET, EXEC_PROFILE_DEFAULT, Session, Cluster, Host, ExecutionProfile
from cassandra.query import BatchStatement, PreparedStatement, SimpleStatement

from .base import AsyncCloseable, AsyncContextManageable, check_not_closed, ExceptionHandler
from .exceptions import ConnectionError, QueryError
from .result import AsyncResultHandler, AsyncResultSet
from .streaming import StreamingResultHandler, AsyncStreamingResultSet, StreamConfig
from .metrics import MetricsMiddleware


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
    async def create(cls, cluster: Cluster, keyspace: Optional[str] = None) -> "AsyncCassandraSession":
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
        query: Union[str, SimpleStatement, PreparedStatement],
        parameters: Optional[Union[List, Dict]] = None,
        trace: bool = False,
        custom_payload: Optional[Dict[str, bytes]] = None,
        timeout: Union[float, object] = _NOT_SET,
        execution_profile: Union[str, ExecutionProfile] = EXEC_PROFILE_DEFAULT,
        paging_state: Optional[bytes] = None,
        host: Optional[Host] = None,
        execute_as: Optional[str] = None,
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
        self._check_not_closed()

        # Start metrics timing
        start_time = time.perf_counter()
        success = False
        error_type = None
        result_size = 0

        cassandra_exceptions = (InvalidRequest, Unavailable, ReadTimeout, WriteTimeout, OperationTimedOut)
        
        try:
            async with ExceptionHandler("Query execution failed", QueryError, cassandra_exceptions):
                response_future = self._session.execute_async(
                    query,
                    parameters,
                    trace,
                    custom_payload,
                    timeout,
                    execution_profile,
                    paging_state,
                    host,
                    execute_as,
                )

                handler = AsyncResultHandler(response_future)
                result = await handler.get_result()
                
                success = True
                result_size = len(result.rows) if hasattr(result, 'rows') else 0
                return result
                
        except Exception as e:
            error_type = type(e).__name__
            raise
        finally:
            # Record metrics if middleware is available
            if self._metrics:
                duration = time.perf_counter() - start_time
                query_str = str(query) if isinstance(query, (SimpleStatement, PreparedStatement)) else query
                params_count = len(parameters) if parameters else 0
                
                await self._metrics.record_query_metrics(
                    query=query_str,
                    duration=duration,
                    success=success,
                    error_type=error_type,
                    parameters_count=params_count,
                    result_size=result_size
                )

    @check_not_closed
    async def execute_stream(
        self,
        query: Union[str, SimpleStatement, PreparedStatement],
        parameters: Optional[Union[List, Dict]] = None,
        stream_config: Optional[StreamConfig] = None,
        trace: bool = False,
        custom_payload: Optional[Dict[str, bytes]] = None,
        timeout: Union[float, object] = _NOT_SET,
        execution_profile: Union[str, ExecutionProfile] = EXEC_PROFILE_DEFAULT,
        paging_state: Optional[bytes] = None,
        host: Optional[Host] = None,
        execute_as: Optional[str] = None,
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
        self._check_not_closed()

        cassandra_exceptions = (InvalidRequest, Unavailable, ReadTimeout, WriteTimeout, OperationTimedOut)
        
        async with ExceptionHandler("Streaming query execution failed", QueryError, cassandra_exceptions):
            response_future = self._session.execute_async(
                query,
                parameters,
                trace,
                custom_payload,
                timeout,
                execution_profile,
                paging_state,
                host,
                execute_as,
            )

            handler = StreamingResultHandler(response_future, stream_config)
            return await handler.get_streaming_result()

    async def execute_batch(
        self,
        batch_statement: BatchStatement,
        trace: bool = False,
        custom_payload: Optional[Dict[str, bytes]] = None,
        timeout: Union[float, object] = _NOT_SET,
        execution_profile: Union[str, ExecutionProfile] = EXEC_PROFILE_DEFAULT,
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
            timeout=timeout,
            execution_profile=execution_profile,
        )

    @check_not_closed
    async def prepare(
        self, query: str, custom_payload: Optional[Dict[str, bytes]] = None
    ) -> PreparedStatement:
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
        cassandra_exceptions = (InvalidRequest, OperationTimedOut)
        
        async with ExceptionHandler("Statement preparation failed", QueryError, cassandra_exceptions):
            loop = asyncio.get_event_loop()

            # Prepare in executor to avoid blocking
            prepared = await loop.run_in_executor(
                None, lambda: self._session.prepare(query, custom_payload)
            )

            return prepared

    async def _do_close(self) -> None:
        """Perform the actual session shutdown."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._session.shutdown)

    @property
    def keyspace(self) -> Optional[str]:
        """Get current keyspace."""
        return self._session.keyspace

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
        if not keyspace or not all(c.isalnum() or c == '_' for c in keyspace):
            raise ValueError(
                f"Invalid keyspace name: '{keyspace}'. "
                "Keyspace names must contain only alphanumeric characters and underscores."
            )
        
        await self.execute(f"USE {keyspace}")
