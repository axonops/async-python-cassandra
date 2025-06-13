"""Timeout handling tests.

This module tests timeout behavior in async operations, including
query timeouts, connection timeouts, and proper cleanup.
"""

import asyncio
from unittest.mock import Mock, patch

import pytest
from cassandra import OperationTimedOut, ReadTimeout, WriteTimeout
from cassandra.cluster import ResponseFuture

from async_cassandra import AsyncCassandraSession as AsyncSession
from async_cassandra import AsyncCluster
from async_cassandra.result import AsyncResultHandler


def create_mock_response_future(rows=None, has_more_pages=False):
    """Helper to create a properly configured mock ResponseFuture."""
    mock_future = Mock()
    mock_future.has_more_pages = has_more_pages
    mock_future.timeout = None  # Avoid comparison issues
    mock_future.add_callbacks = Mock()

    def handle_callbacks(callback=None, errback=None):
        if callback:
            callback(rows if rows is not None else [])

    mock_future.add_callbacks.side_effect = handle_callbacks
    return mock_future


class TestTimeoutHandling:
    """Test timeout handling in async operations."""

    @pytest.mark.resilience
    @pytest.mark.quick
    @pytest.mark.critical
    async def test_query_timeout_propagation(self):
        """Test that query timeouts are properly propagated."""
        mock_session = Mock()
        mock_session.execute_async.side_effect = OperationTimedOut("Query timed out")

        async_session = AsyncSession(mock_session)

        with pytest.raises(OperationTimedOut, match="Query timed out"):
            await async_session.execute("SELECT * FROM large_table", timeout=1.0)

    @pytest.mark.resilience
    async def test_read_timeout_exception(self):
        """Test handling of read timeout exceptions."""
        mock_session = Mock()
        exception = ReadTimeout("Read timeout", data_retrieved=False)
        # Set attributes manually since they're not in constructor
        exception.consistency = 1
        exception.received_responses = 0
        exception.required_responses = 1
        mock_session.execute_async.side_effect = exception

        async_session = AsyncSession(mock_session)

        with pytest.raises(ReadTimeout) as exc_info:
            await async_session.execute("SELECT * FROM users")

        assert exc_info.value.consistency == 1
        assert exc_info.value.received_responses == 0
        assert exc_info.value.required_responses == 1
        assert exc_info.value.data_retrieved is False

    @pytest.mark.resilience
    async def test_write_timeout_exception(self):
        """Test handling of write timeout exceptions."""
        from cassandra import WriteType

        mock_session = Mock()
        exception = WriteTimeout("Write timeout", write_type=WriteType.SIMPLE)
        # Set attributes manually since they're not in constructor
        exception.consistency = 1
        exception.received_responses = 0
        exception.required_responses = 1
        mock_session.execute_async.side_effect = exception

        async_session = AsyncSession(mock_session)

        with pytest.raises(WriteTimeout) as exc_info:
            await async_session.execute("INSERT INTO users VALUES (?)", [1])

        assert exc_info.value.consistency == 1
        assert exc_info.value.received_responses == 0
        assert exc_info.value.required_responses == 1
        assert exc_info.value.write_type == WriteType.SIMPLE

    @pytest.mark.resilience
    @pytest.mark.critical
    async def test_timeout_with_callback_cleanup(self):
        """Test that callbacks are cleaned up on timeout."""
        # Create a mock response future that simulates timeout
        mock_future = Mock(spec=ResponseFuture)
        mock_future.timeout = None  # Avoid comparison issues
        callback_store = []

        def add_callback(callback, *args, **kwargs):
            callback_store.append(callback)
            # Simulate timeout after callback registration
            asyncio.get_event_loop().call_later(
                0.1, lambda: callback(OperationTimedOut("Timed out"))
            )

        mock_future.add_callback = add_callback
        mock_future.add_errback = add_callback

        mock_session = Mock()
        mock_session.execute_async.return_value = mock_future

        async_session = AsyncSession(mock_session)

        with pytest.raises(OperationTimedOut):
            await async_session.execute("SELECT * FROM large_table")

        # Verify callbacks were registered
        assert len(callback_store) > 0

    @pytest.mark.resilience
    async def test_concurrent_timeout_handling(self):
        """Test handling timeouts in concurrent queries."""
        mock_session = Mock()

        # Mix of successful and timed-out queries
        results = [
            create_mock_response_future([{"id": 1}]),  # Success
            OperationTimedOut("Query 2 timed out"),  # Timeout
            create_mock_response_future([{"id": 3}]),  # Success
            OperationTimedOut("Query 4 timed out"),  # Timeout
        ]

        mock_session.execute_async.side_effect = results

        async_session = AsyncSession(mock_session)

        # Execute queries concurrently
        tasks = []
        for i in range(4):
            task = async_session.execute(f"SELECT * FROM table{i}")
            tasks.append(task)

        # Gather results, allowing exceptions
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify results
        assert len(results) == 4
        assert not isinstance(results[0], Exception)
        assert isinstance(results[1], OperationTimedOut)
        assert not isinstance(results[2], Exception)
        assert isinstance(results[3], OperationTimedOut)

    @pytest.mark.resilience
    async def test_timeout_with_retry_policy(self):
        """Test timeout interaction with retry policy."""
        mock_session = Mock()

        # First attempt times out, retry succeeds
        exception = ReadTimeout("First attempt", data_retrieved=False)
        exception.consistency = 1
        exception.received_responses = 0
        exception.required_responses = 1

        mock_session.execute_async.side_effect = [
            exception,
            create_mock_response_future([{"id": 1, "name": "test"}]),
        ]

        async_session = AsyncSession(mock_session)

        # This should succeed after retry
        result = await async_session.execute("SELECT * FROM users WHERE id = 1")
        assert result._rows == [{"id": 1, "name": "test"}]
        assert mock_session.execute_async.call_count == 2

    @pytest.mark.resilience
    async def test_timeout_cleanup_on_session_close(self):
        """Test that pending timeouts are cleaned up when session closes."""
        mock_session = Mock()
        pending_futures = []

        # Create futures that will timeout
        def create_hanging_future(*args, **kwargs):
            future = asyncio.Future()
            pending_futures.append(future)
            # Don't complete the future to simulate hanging query
            return future

        mock_session.execute_async = Mock(side_effect=create_hanging_future)

        async_session = AsyncSession(mock_session)

        # Start queries that will hang
        tasks = []
        for i in range(3):
            task = asyncio.create_task(async_session.execute(f"SELECT * FROM table{i}"))
            tasks.append(task)

        # Close session should cancel pending operations
        await async_session.close()

        # All tasks should be cancelled
        for task in tasks:
            assert task.cancelled() or task.done()

    @pytest.mark.resilience
    def test_timeout_configuration(self):
        """Test timeout configuration at cluster and query level."""
        # Cluster-level timeout
        cluster = AsyncCluster(default_timeout=30.0)
        assert cluster.default_timeout == 30.0

        # Query-level timeout should override cluster default
        mock_session = Mock()

        # Create a mock ResponseFuture for the response
        mock_session.execute_async.return_value = create_mock_response_future([])

        async_session = AsyncSession(mock_session)

        # Execute with custom timeout
        asyncio.run(async_session.execute("SELECT * FROM users", timeout=5.0))

        # Verify timeout was passed to underlying session
        mock_session.execute_async.assert_called_once()
        args, kwargs = mock_session.execute_async.call_args
        # The timeout parameter is at position 4 in the call
        assert args[4] == 5.0

    @pytest.mark.resilience
    @pytest.mark.critical
    async def test_timeout_does_not_leak_resources(self):
        """Test that timeouts don't leak threads or memory."""
        import gc
        import weakref

        mock_session = Mock()
        mock_session.execute_async.side_effect = OperationTimedOut("Timed out")

        async_session = AsyncSession(mock_session)

        # Create weak references to track cleanup
        handler_refs = []

        original_handler_init = AsyncResultHandler.__init__

        def tracked_init(self, response_future):
            original_handler_init(self, response_future)
            handler_refs.append(weakref.ref(self))

        with patch.object(AsyncResultHandler, "__init__", tracked_init):
            # Execute queries that will timeout
            for i in range(10):
                try:
                    await async_session.execute(f"SELECT * FROM table{i}")
                except OperationTimedOut:
                    pass

        # Force garbage collection
        gc.collect()

        # Check that handlers were cleaned up
        alive_handlers = sum(1 for ref in handler_refs if ref() is not None)
        assert alive_handlers == 0, f"{alive_handlers} handlers still alive"
