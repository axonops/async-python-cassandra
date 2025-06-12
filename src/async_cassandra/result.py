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
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            # If no event loop is running, we'll create the future when needed
            self._loop = None
        self._future = self._loop.create_future() if self._loop else None
        # Thread lock to protect shared state from concurrent driver callbacks
        self._lock = threading.Lock()

        # Set up callbacks
        self.response_future.add_callbacks(callback=self._handle_page, errback=self._handle_error)

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
                if self._loop and self._future:
                    self._loop.call_soon_threadsafe(
                        self._future.set_result, AsyncResultSet(final_rows)
                    )

    def _handle_error(self, exc: Exception) -> None:
        """Handle query execution error."""
        if self._loop and self._future:
            self._loop.call_soon_threadsafe(self._future.set_exception, exc)

    async def get_result(self) -> "AsyncResultSet":
        """
        Wait for the query to complete and return the result.

        Returns:
            AsyncResultSet containing all rows from the query.
        """
        if not self._loop:
            self._loop = asyncio.get_running_loop()
            self._future = self._loop.create_future()

        return await self._future


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
