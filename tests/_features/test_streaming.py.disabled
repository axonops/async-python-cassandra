"""Consolidated streaming functionality tests.

This module combines all streaming tests including basic functionality,
memory management, and error handling.
"""

import asyncio
import gc
import weakref
from unittest.mock import Mock

import pytest
from cassandra import ConsistencyLevel, InvalidRequest

from async_cassandra.result import AsyncStreamingResultSet, StreamingResultHandler
from async_cassandra.session import create_streaming_statement


class TestStreamingCore:
    """Core streaming functionality tests."""

    @pytest.mark.features
    @pytest.mark.quick
    @pytest.mark.critical
    async def test_single_page_streaming(self):
        """Test streaming with single page of results."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = False
        mock_result_set._current_rows = [1, 2, 3]

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        results = []
        async for row in streaming_result:
            results.append(row)

        assert results == [1, 2, 3]

    @pytest.mark.features
    @pytest.mark.critical
    async def test_multi_page_streaming(self):
        """Test streaming with multiple pages."""
        # First page
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]

        # Second page
        mock_page2 = Mock()
        mock_page2.has_more_pages = False
        mock_page2._current_rows = [4, 5, 6]

        # Mock fetch_next_page_async
        future = asyncio.Future()
        future.set_result(mock_page2)
        mock_result_set.fetch_next_page_async.return_value = future

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        results = []
        async for row in streaming_result:
            results.append(row)

        assert results == [1, 2, 3, 4, 5, 6]
        mock_result_set.fetch_next_page_async.assert_called_once()

    @pytest.mark.features
    async def test_page_based_iteration(self):
        """Test iterating by pages instead of rows."""
        # First page
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]
        mock_result_set.current_rows = [1, 2, 3]

        # Second page
        mock_page2 = Mock()
        mock_page2.has_more_pages = False
        mock_page2._current_rows = [4, 5, 6]
        mock_page2.current_rows = [4, 5, 6]

        future = asyncio.Future()
        future.set_result(mock_page2)
        mock_result_set.fetch_next_page_async.return_value = future

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        pages = []
        async for page in streaming_result.pages():
            pages.append(list(page))

        assert pages == [[1, 2, 3], [4, 5, 6]]

    @pytest.mark.features
    async def test_error_during_streaming(self):
        """Test error handling during streaming."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]

        # Error on fetch next page
        future = asyncio.Future()
        future.set_exception(InvalidRequest("Query error"))
        mock_result_set.fetch_next_page_async.return_value = future

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        results = []
        with pytest.raises(InvalidRequest, match="Query error"):
            async for row in streaming_result:
                results.append(row)

        # Should have gotten first page results before error
        assert results == [1, 2, 3]

    @pytest.mark.features
    async def test_streaming_cancellation(self):
        """Test cancelling streaming iteration."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = list(range(100))

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        results = []
        async for row in streaming_result:
            results.append(row)
            if len(results) >= 10:
                break  # Cancel iteration

        assert len(results) == 10
        assert results == list(range(10))

    @pytest.mark.features
    def test_create_streaming_statement(self):
        """Test creating streaming statements."""
        # Basic statement
        stmt = create_streaming_statement("SELECT * FROM users")
        assert stmt.query == "SELECT * FROM users"
        assert stmt.fetch_size == 5000

        # Custom fetch size
        stmt = create_streaming_statement("SELECT * FROM users", fetch_size=1000)
        assert stmt.fetch_size == 1000

        # With consistency level
        stmt = create_streaming_statement(
            "SELECT * FROM users", consistency_level=ConsistencyLevel.QUORUM
        )
        assert stmt.consistency_level == ConsistencyLevel.QUORUM


class TestStreamingMemoryManagement:
    """Test memory management in streaming operations."""

    @pytest.mark.features
    @pytest.mark.critical
    async def test_memory_cleanup_on_error(self):
        """Test that memory is properly cleaned up on errors."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        # Access _current_page to ensure it's created
        assert streaming_result._current_page is not None

        # Simulate error
        error = InvalidRequest("Test error")
        streaming_result._handle_error(error)

        # _current_page should be cleared
        assert streaming_result._current_page is None

    @pytest.mark.features
    async def test_no_memory_leak_on_multiple_errors(self):
        """Test that multiple errors don't cause memory accumulation."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = list(range(1000))  # Large dataset

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        # Simulate multiple errors
        for i in range(10):
            streaming_result._current_page = mock_result_set  # Simulate page load
            streaming_result._handle_error(Exception(f"Error {i}"))

            # Should be cleared each time
            assert streaming_result._current_page is None

    @pytest.mark.features
    @pytest.mark.critical
    async def test_async_context_manager_cleanup(self):
        """Test cleanup when using async context manager."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]

        mock_session = Mock()

        async with AsyncStreamingResultSet(mock_result_set, mock_session) as stream:
            results = []
            async for row in stream:
                results.append(row)
                if len(results) >= 2:
                    break

        # Should have cleaned up
        assert stream._current_page is None
        assert stream._driver_result_set is None

    @pytest.mark.features
    async def test_close_clears_callbacks(self):
        """Test that close() clears all callbacks and resources."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]
        mock_result_set.clear_callbacks = Mock()

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        # Close should clear everything
        await streaming_result.close()

        assert streaming_result._current_page is None
        assert streaming_result._driver_result_set is None
        mock_result_set.clear_callbacks.assert_called_once()

    @pytest.mark.features
    async def test_exception_in_iteration_cleans_up(self):
        """Test cleanup when exception occurs during iteration."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = False
        mock_result_set._current_rows = [1, 2, 3]

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())

        # Force exception during iteration
        async def bad_iteration():
            async for row in streaming_result:
                if row == 2:
                    raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            async with streaming_result:
                await bad_iteration()

        # Should still be cleaned up
        assert streaming_result._current_page is None

    @pytest.mark.features
    async def test_page_limit_enforcement(self):
        """Test that page limits are enforced."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]

        # Create pages
        pages = []
        for i in range(5):
            page = Mock()
            page.has_more_pages = i < 4
            page._current_rows = [i * 3 + 1, i * 3 + 2, i * 3 + 3]
            pages.append(page)

        # Mock fetch to return pages in order
        fetch_count = 0

        def fetch_next():
            nonlocal fetch_count
            future = asyncio.Future()
            if fetch_count < len(pages):
                future.set_result(pages[fetch_count])
                fetch_count += 1
            return future

        mock_result_set.fetch_next_page_async.side_effect = fetch_next

        # Limit to 3 pages
        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock(), max_pages=3)

        all_results = []
        async for row in streaming_result:
            all_results.append(row)

        # Should only get 3 pages worth of data
        assert len(all_results) == 9  # 3 pages * 3 rows each
        assert fetch_count == 2  # Initial page + 2 fetches

    @pytest.mark.features
    async def test_weakref_cleanup(self):
        """Test that streaming results can be garbage collected."""
        mock_result_set = Mock()
        mock_result_set.has_more_pages = False
        mock_result_set._current_rows = [1, 2, 3]

        streaming_result = AsyncStreamingResultSet(mock_result_set, Mock())
        weak_ref = weakref.ref(streaming_result)

        # Use it briefly
        async for _ in streaming_result:
            break

        # Delete reference
        del streaming_result

        # Force garbage collection
        gc.collect()

        # Should be collected
        assert weak_ref() is None


class TestStreamingResultHandler:
    """Test StreamingResultHandler functionality."""

    @pytest.mark.features
    @pytest.mark.quick
    async def test_get_streaming_result(self):
        """Test getting streaming result through handler."""
        handler = StreamingResultHandler(Mock())
        mock_result = Mock()

        handler.on_success(mock_result)

        result = await handler.future
        assert isinstance(result, AsyncStreamingResultSet)
        assert result._driver_result_set == mock_result

    @pytest.mark.features
    async def test_streaming_handler_error(self):
        """Test error handling in streaming handler."""
        handler = StreamingResultHandler(Mock())
        error = InvalidRequest("Streaming error")

        handler.on_error(error)

        with pytest.raises(InvalidRequest, match="Streaming error"):
            await handler.future
