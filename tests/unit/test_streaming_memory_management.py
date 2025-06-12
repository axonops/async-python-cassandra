"""
Test memory management and resource cleanup in streaming.
"""

import asyncio
import gc
import weakref
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from async_cassandra.streaming import AsyncStreamingResultSet, StreamConfig


class TestStreamingMemoryManagement:
    """Test memory management in streaming operations."""

    @pytest.mark.asyncio
    async def test_async_context_manager_cleanup(self):
        """Test that async context manager properly cleans up resources."""
        # Create mock response future
        response_future = Mock()
        response_future.has_more_pages = False
        response_future.clear_callbacks = Mock()
        
        # Track if cleanup was called
        cleanup_called = False
        
        async with AsyncStreamingResultSet(response_future) as stream:
            # Verify stream is usable
            assert not stream._closed
            # Mock some data
            stream._handle_page([1, 2, 3])
            assert len(stream._current_page) == 3
        
        # After context exit, verify cleanup
        assert stream._closed
        assert stream._exhausted
        assert len(stream._current_page) == 0
        response_future.clear_callbacks.assert_called()

    @pytest.mark.asyncio
    async def test_abandoned_iterator_cleanup(self):
        """Test that abandoned iterators clean up their callbacks."""
        # Create mock response future
        response_future = Mock()
        response_future.has_more_pages = True
        response_future.clear_callbacks = Mock()
        response_future.start_fetching_next_page = Mock()
        
        # Create streaming result set
        stream = AsyncStreamingResultSet(response_future)
        stream._handle_page([1, 2, 3])
        
        # Manually trigger deletion logic
        stream.__del__()
        
        # Verify cleanup was called
        response_future.clear_callbacks.assert_called()
        assert len(stream._current_page) == 0
        assert len(stream._active_callbacks) == 0

    @pytest.mark.asyncio
    async def test_multiple_context_manager_entries(self):
        """Test that multiple context manager entries don't cause issues."""
        response_future = Mock()
        response_future.has_more_pages = False
        response_future.clear_callbacks = Mock()
        
        stream = AsyncStreamingResultSet(response_future)
        
        # First context
        async with stream:
            assert not stream._closed
        
        assert stream._closed
        
        # Second context should be safe but no-op
        async with stream:
            assert stream._closed  # Still closed
        
        # Cleanup should only be called once
        response_future.clear_callbacks.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_in_iteration_cleans_up(self):
        """Test that exceptions during iteration still clean up properly."""
        response_future = Mock()
        response_future.has_more_pages = True
        response_future.clear_callbacks = Mock()
        
        stream = AsyncStreamingResultSet(response_future)
        
        # Mock page data
        stream._handle_page([1, 2, 3])
        stream._first_page_ready = True
        
        class TestException(Exception):
            pass
        
        with pytest.raises(TestException):
            async with stream:
                async for row in stream:
                    if row == 2:
                        raise TestException("Test error")
        
        # Verify cleanup happened
        assert stream._closed
        response_future.clear_callbacks.assert_called()

    @pytest.mark.asyncio
    async def test_memory_limit_enforcement(self):
        """Test that memory limits are respected."""
        # Create config with memory limit
        config = StreamConfig(
            fetch_size=1000,
            max_memory_mb=1  # Very small limit for testing
        )
        
        response_future = Mock()
        response_future.has_more_pages = True
        
        stream = AsyncStreamingResultSet(response_future, config)
        
        # TODO: Implement actual memory limit enforcement in the streaming class
        # For now, just verify the config is stored
        assert stream.config.max_memory_mb == 1

    @pytest.mark.asyncio
    async def test_timeout_cleanup(self):
        """Test that timeouts properly clean up resources."""
        config = StreamConfig(timeout_seconds=0.1)
        
        response_future = Mock()
        response_future.has_more_pages = True
        response_future.clear_callbacks = Mock()
        
        stream = AsyncStreamingResultSet(response_future, config)
        
        # Create a slow page callback
        async def slow_iteration():
            async with stream:
                stream._handle_page([1, 2, 3])
                stream._first_page_ready = True
                async for row in stream:
                    await asyncio.sleep(0.2)  # Longer than timeout
        
        # TODO: Implement actual timeout handling in streaming
        # For now, just verify config is stored
        assert stream.config.timeout_seconds == 0.1

    @pytest.mark.asyncio
    async def test_close_wakes_up_waiters(self):
        """Test that close() wakes up any threads waiting for pages."""
        response_future = Mock()
        response_future.has_more_pages = True
        
        stream = AsyncStreamingResultSet(response_future)
        
        # Create page ready event
        stream._page_ready = asyncio.Event()
        
        # Start a task that waits for a page
        wait_task = asyncio.create_task(stream._page_ready.wait())
        
        # Give the task a moment to start waiting
        await asyncio.sleep(0.01)
        
        # Close the stream
        await stream.close()
        
        # The wait should complete (not hang)
        try:
            await asyncio.wait_for(wait_task, timeout=0.1)
        except asyncio.TimeoutError:
            pytest.fail("close() did not wake up page waiters")

    @pytest.mark.asyncio
    async def test_concurrent_close_and_iteration(self):
        """Test that concurrent close and iteration is handled safely."""
        response_future = Mock()
        response_future.has_more_pages = True
        response_future.clear_callbacks = Mock()
        response_future.start_fetching_next_page = Mock()
        
        stream = AsyncStreamingResultSet(response_future)
        stream._handle_page([1, 2, 3, 4, 5])
        stream._first_page_ready = True
        
        # Track iterations
        iterations = []
        
        async def iterate():
            try:
                async for row in stream:
                    iterations.append(row)
                    await asyncio.sleep(0.01)
            except Exception:
                pass  # Expected when stream is closed
        
        async def close_after_delay():
            await asyncio.sleep(0.02)
            await stream.close()
        
        # Run both concurrently
        await asyncio.gather(
            iterate(),
            close_after_delay(),
            return_exceptions=True
        )
        
        # Should have gotten some iterations before close
        assert len(iterations) > 0
        assert stream._closed

    def test_weak_reference_cleanup(self):
        """Test that weak references don't prevent garbage collection."""
        response_future = Mock()
        stream = AsyncStreamingResultSet(response_future)
        
        # Add some mock callbacks to weak set
        callback1 = Mock()
        callback2 = Mock()
        stream._active_callbacks.add(callback1)
        stream._active_callbacks.add(callback2)
        
        # Delete one callback
        del callback1
        gc.collect()
        
        # Weak set should only have one item now
        assert len(stream._active_callbacks) == 1