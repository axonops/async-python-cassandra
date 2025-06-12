"""
Async result handling for Cassandra queries.
"""

import asyncio
import threading
from typing import Any, AsyncIterator, List, Optional

from cassandra.cluster import ResponseFuture


class AsyncResultHandler:
    """
    Handles asynchronous results from Cassandra queries.

    This class wraps ResponseFuture callbacks in asyncio Futures,
    providing proper async/await support for query results.
    """

    def __init__(self, response_future: ResponseFuture):
        self.response_future = response_future
        self.rows: List[Any] = []
        self._future: Optional[asyncio.Future[AsyncResultSet]] = None
        # Thread lock to protect shared state from concurrent driver callbacks
        self._lock = threading.Lock()
        # Track if we've been initialized with a future
        self._future_initialized = False
        # Track if result is ready (for early callback case)
        self._result_ready = False
        self._result_error: Optional[Exception] = None

        # Set up callbacks
        self.response_future.add_callbacks(callback=self._handle_page, errback=self._handle_error)

    def _cleanup_callbacks(self) -> None:
        """Clean up response future callbacks to prevent memory leaks."""
        try:
            # Clear callbacks if the method exists
            if hasattr(self.response_future, "clear_callbacks"):
                self.response_future.clear_callbacks()
        except Exception:
            # Ignore errors during cleanup
            pass

    def _handle_page(self, rows: List[Any]) -> None:
        """Handle successful page retrieval.

        This method is called from driver threads, so we need thread safety.
        """
        with self._lock:
            if rows is not None:
                # Create a defensive copy to avoid cross-thread data issues
                self.rows.extend(list(rows))

            if self.response_future.has_more_pages:
                self.response_future.start_fetching_next_page()
            else:
                # All pages fetched, set result
                # Create a copy of rows to avoid reference issues
                final_rows = list(self.rows)
                if self._future and not self._future.done():
                    if hasattr(self, "_loop"):
                        self._loop.call_soon_threadsafe(
                            self._future.set_result, AsyncResultSet(final_rows)
                        )
                else:
                    # Future not ready yet, mark result as ready for later
                    self._result_ready = True

                # Clean up callbacks after completion
                self._cleanup_callbacks()

    def _handle_error(self, exc: Exception) -> None:
        """Handle query execution error."""
        with self._lock:
            if self._future and not self._future.done():
                if hasattr(self, "_loop"):
                    self._loop.call_soon_threadsafe(self._future.set_exception, exc)
            else:
                # Future not ready yet, store error for later
                self._result_error = exc
                self._result_ready = True

        # Clean up callbacks to prevent memory leaks
        self._cleanup_callbacks()

    async def get_result(self, timeout: Optional[float] = None) -> "AsyncResultSet":
        """
        Wait for the query to complete and return the result.

        Args:
            timeout: Optional timeout in seconds. If None, uses the query timeout
                    from the ResponseFuture if available.

        Returns:
            AsyncResultSet containing all rows from the query.

        Raises:
            asyncio.TimeoutError: If the query doesn't complete within the timeout.
        """
        # Create future on first use to ensure it's created in the right event loop
        loop = asyncio.get_running_loop()
        if not self._future_initialized:
            self._future = loop.create_future()
            self._future_initialized = True
            self._loop = loop  # Store loop for callbacks

            # Check if result is already ready (callback fired early)
            with self._lock:
                if self._result_ready:
                    if self._result_error:
                        self._future.set_exception(self._result_error)
                    else:
                        # Result is ready, set it now
                        self._future.set_result(AsyncResultSet(list(self.rows)))

        if self._future is None:
            raise RuntimeError("Future not initialized")

        # Use query timeout if no explicit timeout provided
        if (
            timeout is None
            and hasattr(self.response_future, "timeout")
            and self.response_future.timeout is not None
        ):
            timeout = self.response_future.timeout

        try:
            if timeout is not None:
                return await asyncio.wait_for(self._future, timeout=timeout)
            else:
                return await self._future
        except asyncio.TimeoutError:
            # Clean up on timeout
            self._cleanup_callbacks()
            raise
        except Exception:
            # Clean up on any error
            self._cleanup_callbacks()
            raise


class AsyncResultSet:
    """
    Async wrapper for Cassandra query results.

    Provides async iteration over result rows and metadata access.
    """

    def __init__(self, rows: List[Any]):
        self._rows = rows
        self._index = 0

    def __aiter__(self) -> AsyncIterator[Any]:
        """Return async iterator for the result set."""
        self._index = 0  # Reset index for each iteration
        return self

    async def __anext__(self) -> Any:
        """Get next row from the result set."""
        if self._index >= len(self._rows):
            raise StopAsyncIteration

        row = self._rows[self._index]
        self._index += 1
        return row

    def __len__(self) -> int:
        """Return number of rows in the result set."""
        return len(self._rows)

    @property
    def rows(self) -> List[Any]:
        """Get all rows as a list."""
        return self._rows

    def one(self) -> Optional[Any]:
        """
        Get the first row or None if empty.

        Returns:
            First row from the result set or None.
        """
        return self._rows[0] if self._rows else None

    def all(self) -> List[Any]:
        """
        Get all rows.

        Returns:
            List of all rows in the result set.
        """
        return self._rows
