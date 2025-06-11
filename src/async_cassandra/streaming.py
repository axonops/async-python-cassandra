"""
Streaming support for large result sets in async-cassandra.

This module provides streaming capabilities to handle large result sets
without loading all data into memory at once.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, List, Optional

from cassandra.cluster import ResponseFuture
from cassandra.query import ConsistencyLevel, SimpleStatement

logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Configuration for streaming results."""

    fetch_size: int = 1000  # Number of rows per page
    max_pages: Optional[int] = None  # Limit number of pages (None = no limit)
    page_callback: Optional[Callable[[int, int], None]] = None  # Progress callback


class AsyncStreamingResultSet:
    """
    Streaming result set that fetches pages on demand.

    This class provides memory-efficient iteration over large result sets
    by fetching pages as needed rather than loading all results at once.
    """

    def __init__(self, response_future: ResponseFuture, config: Optional[StreamConfig] = None):
        """
        Initialize streaming result set.

        Args:
            response_future: The Cassandra response future
            config: Streaming configuration
        """
        self.response_future = response_future
        self.config = config or StreamConfig()

        self._loop = asyncio.get_running_loop()
        self._current_page: List[Any] = []
        self._current_index = 0
        self._page_number = 0
        self._total_rows = 0
        self._exhausted = False
        self._error: Optional[Exception] = None

        # Event to signal when a page is ready
        self._page_ready = asyncio.Event()

        # Start fetching the first page
        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        """Set up callbacks for the current page."""
        self.response_future.add_callbacks(callback=self._handle_page, errback=self._handle_error)

    def _handle_page(self, rows: Optional[List[Any]]) -> None:
        """Handle successful page retrieval."""
        if rows is not None:
            self._current_page = rows
            self._current_index = 0
            self._page_number += 1
            self._total_rows += len(rows)

            # Call progress callback if provided
            if self.config.page_callback:
                try:
                    self.config.page_callback(self._page_number, len(rows))
                except Exception as e:
                    logger.warning(f"Page callback error: {e}")

            # Check if we've reached the page limit
            if self.config.max_pages and self._page_number >= self.config.max_pages:
                self._exhausted = True
        else:
            self._current_page = []
            self._exhausted = True

        # Signal that the page is ready
        self._loop.call_soon_threadsafe(self._page_ready.set)

    def _handle_error(self, exc: Exception) -> None:
        """Handle query execution error."""
        self._error = exc
        self._exhausted = True
        self._loop.call_soon_threadsafe(self._page_ready.set)

    async def _fetch_next_page(self) -> bool:
        """
        Fetch the next page of results.

        Returns:
            True if a page was fetched, False if no more pages.
        """
        if self._exhausted:
            return False

        if not self.response_future.has_more_pages:
            self._exhausted = True
            return False

        # Clear the event before fetching
        self._page_ready.clear()

        # Start fetching the next page
        self.response_future.start_fetching_next_page()

        # Wait for the page to be ready
        await self._page_ready.wait()

        # Check for errors
        if self._error:
            raise self._error

        return len(self._current_page) > 0

    def __aiter__(self) -> AsyncIterator[Any]:
        """Return async iterator for streaming results."""
        return self

    async def __anext__(self) -> Any:
        """Get next row from the streaming result set."""
        # Check for errors first
        if self._error:
            raise self._error

        # If we have rows in the current page, return one
        if self._current_index < len(self._current_page):
            row = self._current_page[self._current_index]
            self._current_index += 1
            return row

        # If current page is exhausted, try to fetch next page
        if await self._fetch_next_page():
            # Recursively call to get the first row from new page
            return await self.__anext__()

        # No more rows
        raise StopAsyncIteration

    async def pages(self) -> AsyncIterator[List[Any]]:
        """
        Iterate over pages instead of individual rows.

        Yields:
            Lists of row objects (pages).
        """
        # Yield the current page if it has data
        if self._current_page:
            yield self._current_page

        # Fetch and yield subsequent pages
        while await self._fetch_next_page():
            if self._current_page:
                yield self._current_page

    @property
    def page_number(self) -> int:
        """Get the current page number."""
        return self._page_number

    @property
    def total_rows_fetched(self) -> int:
        """Get the total number of rows fetched so far."""
        return self._total_rows

    async def cancel(self) -> None:
        """Cancel the streaming operation."""
        self._exhausted = True
        # Note: ResponseFuture doesn't provide a direct cancel method,
        # but setting exhausted will stop iteration


class StreamingResultHandler:
    """
    Handler for creating streaming result sets.

    This is an alternative to AsyncResultHandler that doesn't
    load all results into memory.
    """

    def __init__(self, response_future: ResponseFuture, config: Optional[StreamConfig] = None):
        """
        Initialize streaming result handler.

        Args:
            response_future: The Cassandra response future
            config: Streaming configuration
        """
        self.response_future = response_future
        self.config = config or StreamConfig()
        self._initial_future = asyncio.get_running_loop().create_future()
        self._streaming_result: Optional[AsyncStreamingResultSet] = None

        # Set up initial callback to create streaming result
        self.response_future.add_callbacks(
            callback=self._handle_initial_response, errback=self._handle_initial_error
        )

    def _handle_initial_response(self, rows: List[Any]) -> None:
        """Handle the initial response to create streaming result."""
        # Create the streaming result set with the initial rows
        self._streaming_result = AsyncStreamingResultSet(self.response_future, self.config)

        # Manually set the first page data
        if rows is not None:
            self._streaming_result._current_page = rows
            self._streaming_result._page_number = 1
            self._streaming_result._total_rows = len(rows)

            if self.config.page_callback:
                try:
                    self.config.page_callback(1, len(rows))
                except Exception as e:
                    logger.warning(f"Page callback error: {e}")

        # Resolve the future
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self._initial_future.set_result, self._streaming_result)

    def _handle_initial_error(self, exc: Exception) -> None:
        """Handle initial query error."""
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self._initial_future.set_exception, exc)

    async def get_streaming_result(self) -> AsyncStreamingResultSet:
        """
        Get the streaming result set.

        Returns:
            AsyncStreamingResultSet for efficient iteration.
        """
        result = await self._initial_future
        assert isinstance(result, AsyncStreamingResultSet)
        return result


def create_streaming_statement(
    query: str, fetch_size: int = 1000, consistency_level: Optional[ConsistencyLevel] = None
) -> SimpleStatement:
    """
    Create a statement configured for streaming.

    Args:
        query: The CQL query
        fetch_size: Number of rows per page
        consistency_level: Optional consistency level

    Returns:
        SimpleStatement configured for streaming
    """
    statement = SimpleStatement(query, fetch_size=fetch_size)

    if consistency_level is not None:
        statement.consistency_level = consistency_level

    return statement
