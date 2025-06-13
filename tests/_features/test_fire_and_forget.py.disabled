"""Fire-and-forget query functionality tests.

This module tests fire-and-forget query execution patterns and metrics.
"""

from unittest.mock import Mock

import pytest
from cassandra.cluster import ResponseFuture

from async_cassandra import AsyncCassandraSession as AsyncSession
from async_cassandra.monitoring import MetricsCollector


class TestFireAndForget:
    """Test fire-and-forget query functionality."""

    @pytest.mark.features
    @pytest.mark.quick
    @pytest.mark.critical
    async def test_basic_fire_and_forget(self):
        """Test basic fire-and-forget query execution."""
        mock_session = Mock()
        mock_future = Mock(spec=ResponseFuture)
        mock_session.execute_async.return_value = mock_future

        async_session = AsyncSession(mock_session)

        # Execute fire-and-forget query
        future = async_session.execute_async(
            "INSERT INTO events (id, data) VALUES (?, ?)", [1, "event_data"], fire_and_forget=True
        )

        # Should return future immediately without waiting
        assert future == mock_future
        mock_session.execute_async.assert_called_once()

    @pytest.mark.features
    async def test_fire_and_forget_with_metrics(self):
        """Test fire-and-forget queries with metrics collection."""
        mock_session = Mock()
        mock_future = Mock(spec=ResponseFuture)
        mock_session.execute_async.return_value = mock_future

        # Setup metrics
        metrics_collector = MetricsCollector()
        async_session = AsyncSession(mock_session)
        async_session._metrics_collector = metrics_collector

        # Execute multiple fire-and-forget queries
        for i in range(5):
            async_session.execute_async(
                "INSERT INTO events (id, data) VALUES (?, ?)",
                [i, f"event_{i}"],
                fire_and_forget=True,
            )

        # Check metrics
        assert metrics_collector.query_metrics.fire_and_forget_queries == 5
        assert mock_session.execute_async.call_count == 5

    @pytest.mark.features
    async def test_fire_and_forget_error_handling(self):
        """Test error handling in fire-and-forget queries."""
        mock_session = Mock()
        mock_session.execute_async.side_effect = Exception("Connection error")

        async_session = AsyncSession(mock_session)

        # Fire-and-forget should not raise exceptions to caller
        with pytest.raises(Exception, match="Connection error"):
            async_session.execute_async(
                "INSERT INTO events (id, data) VALUES (?, ?)", [1, "data"], fire_and_forget=True
            )

    @pytest.mark.features
    @pytest.mark.critical
    async def test_mixed_query_patterns(self):
        """Test mixing fire-and-forget with regular queries."""
        mock_session = Mock()

        # Setup different responses
        mock_future = Mock(spec=ResponseFuture)
        mock_result = Mock(current_rows=[{"count": 100}])

        mock_session.execute_async.return_value = mock_future
        mock_session.execute.return_value = mock_result

        async_session = AsyncSession(mock_session)

        # Mix of query types
        # 1. Fire-and-forget insert
        f1 = async_session.execute_async(
            "INSERT INTO events (id) VALUES (?)", [1], fire_and_forget=True
        )

        # 2. Regular query
        result = await async_session.execute("SELECT COUNT(*) FROM events")

        # 3. Another fire-and-forget
        f2 = async_session.execute_async(
            "INSERT INTO events (id) VALUES (?)", [2], fire_and_forget=True
        )

        # Verify execution
        assert f1 == mock_future
        assert f2 == mock_future
        assert result.current_rows[0]["count"] == 100
        assert mock_session.execute_async.call_count == 2
        assert mock_session.execute.call_count == 1

    @pytest.mark.features
    async def test_fire_and_forget_with_callbacks(self):
        """Test fire-and-forget with custom callbacks."""
        mock_session = Mock()
        mock_future = Mock(spec=ResponseFuture)

        callback_results = []
        errback_results = []

        def custom_callback(result):
            callback_results.append(result)

        def custom_errback(error):
            errback_results.append(error)

        mock_future.add_callback.side_effect = lambda cb: cb("success")
        mock_future.add_errback.side_effect = lambda eb: None

        mock_session.execute_async.return_value = mock_future

        async_session = AsyncSession(mock_session)

        # Execute with callbacks
        async_session.execute_async(
            "INSERT INTO events (id) VALUES (?)",
            [1],
            fire_and_forget=True,
            callback=custom_callback,
            errback=custom_errback,
        )

        # Callbacks should be registered
        mock_future.add_callback.assert_called()
        mock_future.add_errback.assert_called()
        assert callback_results == ["success"]

    @pytest.mark.features
    async def test_fire_and_forget_concurrency(self):
        """Test concurrent fire-and-forget queries."""
        mock_session = Mock()

        # Track execution order
        execution_order = []

        def execute_async_side_effect(query, *args, **kwargs):
            execution_order.append(query)
            return Mock(spec=ResponseFuture)

        mock_session.execute_async.side_effect = execute_async_side_effect

        async_session = AsyncSession(mock_session)

        # Launch many concurrent fire-and-forget queries
        queries = []
        for i in range(100):
            query = f"INSERT INTO events (id) VALUES ({i})"
            async_session.execute_async(query, fire_and_forget=True)
            queries.append(query)

        # All should have been executed
        assert len(execution_order) == 100
        assert set(execution_order) == set(queries)

    @pytest.mark.features
    async def test_fire_and_forget_statement_types(self):
        """Test fire-and-forget with different statement types."""
        mock_session = Mock()
        mock_future = Mock(spec=ResponseFuture)
        mock_session.execute_async.return_value = mock_future

        async_session = AsyncSession(mock_session)

        # Test with SimpleStatement
        from cassandra.query import SimpleStatement

        stmt = SimpleStatement("INSERT INTO events (id) VALUES (?)")
        async_session.execute_async(stmt, [1], fire_and_forget=True)

        # Test with prepared statement
        mock_prepared = Mock()
        mock_session.prepare.return_value = mock_prepared

        prepared = await async_session.prepare("INSERT INTO events (id) VALUES (?)")
        async_session.execute_async(prepared, [2], fire_and_forget=True)

        # Test with batch statement
        from cassandra.query import BatchStatement

        batch = BatchStatement()
        batch.add("INSERT INTO events (id) VALUES (?)", [3])
        batch.add("INSERT INTO events (id) VALUES (?)", [4])
        async_session.execute_async(batch, fire_and_forget=True)

        # All should execute
        assert mock_session.execute_async.call_count == 3

    @pytest.mark.features
    @pytest.mark.critical
    async def test_fire_and_forget_resource_cleanup(self):
        """Test that fire-and-forget queries don't leak resources."""
        import gc
        import weakref

        mock_session = Mock()

        # Track futures
        futures_created = []

        def create_future(*args, **kwargs):
            future = Mock(spec=ResponseFuture)
            futures_created.append(weakref.ref(future))
            return future

        mock_session.execute_async.side_effect = create_future

        async_session = AsyncSession(mock_session)

        # Execute many fire-and-forget queries
        for i in range(100):
            async_session.execute_async(
                "INSERT INTO events (id) VALUES (?)", [i], fire_and_forget=True
            )

        # Force garbage collection
        gc.collect()

        # Check how many futures are still alive
        alive_count = sum(1 for ref in futures_created if ref() is not None)

        # Most should be collected (some may still be referenced)
        assert alive_count < 10, f"Too many futures still alive: {alive_count}/100"
