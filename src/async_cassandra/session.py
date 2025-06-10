"""
Async session management for Cassandra connections.
"""

import asyncio
from typing import Any, Dict, List, Optional, Union

from cassandra import (
    InvalidRequest,
    OperationTimedOut,
    ReadTimeout,
    Unavailable,
    WriteTimeout,
)
from cassandra.cluster import _NOT_SET, EXEC_PROFILE_DEFAULT, Session
from cassandra.query import BatchStatement, PreparedStatement, SimpleStatement

from .exceptions import ConnectionError, QueryError
from .result import AsyncResultHandler, AsyncResultSet


class AsyncCassandraSession:
    """
    Async wrapper for Cassandra Session.

    Provides async/await interface for executing CQL queries against Cassandra.
    """

    def __init__(self, session: Session):
        """
        Initialize async session wrapper.

        Args:
            session: The underlying Cassandra session.
        """
        self._session = session
        self._closed = False
        self._close_lock = asyncio.Lock()

    @classmethod
    async def create(cls, cluster: Any, keyspace: Optional[str] = None) -> "AsyncCassandraSession":
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
        timeout: Any = _NOT_SET,
        execution_profile: Any = EXEC_PROFILE_DEFAULT,
        paging_state: Optional[bytes] = None,
        host: Optional[Any] = None,
        execute_as: Optional[str] = None,
    ) -> AsyncResultSet:
        """
        Execute a CQL query asynchronously.

        Args:
            query: The query to execute.
            parameters: Query parameters.
            trace: Whether to enable query tracing.
            custom_payload: Custom payload to send with the request.
            timeout: Query timeout in seconds.
            execution_profile: Execution profile to use.
            paging_state: Paging state for resuming paged queries.
            host: Specific host to execute query on.
            execute_as: User to execute the query as.

        Returns:
            AsyncResultSet containing query results.

        Raises:
            QueryError: If query execution fails.
        """
        if self._closed:
            raise ConnectionError("Session is closed")

        try:
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
            return await handler.get_result()

        except (InvalidRequest, Unavailable, ReadTimeout, WriteTimeout, OperationTimedOut) as e:
            # Re-raise Cassandra-specific exceptions as-is for proper handling
            raise
        except Exception as e:
            # Wrap other exceptions in QueryError
            raise QueryError(f"Query execution failed: {str(e)}", cause=e)

    async def execute_batch(
        self,
        batch_statement: BatchStatement,
        trace: bool = False,
        custom_payload: Optional[Dict[str, bytes]] = None,
        timeout: Any = _NOT_SET,
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
            timeout=timeout,
            execution_profile=execution_profile,
        )

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
        if self._closed:
            raise ConnectionError("Session is closed")

        try:
            loop = asyncio.get_event_loop()

            # Prepare in executor to avoid blocking
            prepared = await loop.run_in_executor(
                None, lambda: self._session.prepare(query, custom_payload)
            )

            return prepared

        except (InvalidRequest, OperationTimedOut) as e:
            # Re-raise Cassandra-specific exceptions as-is
            raise
        except Exception as e:
            # Wrap other exceptions in QueryError
            raise QueryError(f"Statement preparation failed: {str(e)}", cause=e)

    async def close(self) -> None:
        """
        Close the session and release resources.

        This method is idempotent and can be called multiple times safely.
        """
        async with self._close_lock:
            if not self._closed:
                self._closed = True

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._session.shutdown)

    async def __aenter__(self) -> "AsyncCassandraSession":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def is_closed(self) -> bool:
        """Check if session is closed."""
        return self._closed

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
