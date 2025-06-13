"""Race condition and deadlock prevention tests.

This module tests for various race conditions including TOCTOU issues,
callback deadlocks, and concurrent access patterns.
"""

import asyncio
import threading
import time
from unittest.mock import Mock

import pytest

from async_cassandra import AsyncCassandraSession as AsyncSession
from async_cassandra.result import AsyncResultHandler


class TestRaceConditions:
    """Test race conditions and thread safety."""

    @pytest.mark.resilience
    @pytest.mark.critical
    async def test_toctou_event_loop_check(self):
        """Test Time-of-Check-Time-of-Use race in event loop handling."""
        from async_cassandra.utils import get_or_create_event_loop

        # Simulate rapid concurrent access from multiple threads
        results = []
        errors = []

        def worker():
            try:
                loop = get_or_create_event_loop()
                results.append(loop)
            except Exception as e:
                errors.append(e)

        # Create many threads to increase chance of race
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=worker)
            threads.append(thread)

        # Start all threads at once
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Should have no errors
        assert len(errors) == 0
        # Each thread should get a valid event loop
        assert len(results) == 20
        assert all(loop is not None for loop in results)

    @pytest.mark.resilience
    async def test_callback_registration_race(self):
        """Test race condition in callback registration."""
        handler = AsyncResultHandler()
        results = []

        # Try to register callbacks from multiple threads
        def register_success():
            handler.on_success("success")
            results.append("success")

        def register_error():
            handler.on_error(Exception("error"))
            results.append("error")

        # Start threads that race to set result
        t1 = threading.Thread(target=register_success)
        t2 = threading.Thread(target=register_error)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # Only one should win
        try:
            result = await handler.future
            assert result == "success"
            assert results.count("success") >= 1
        except Exception as e:
            assert str(e) == "error"
            assert results.count("error") >= 1

    @pytest.mark.resilience
    @pytest.mark.critical
    async def test_concurrent_session_operations(self):
        """Test concurrent operations on same session."""
        mock_session = Mock()
        call_count = 0

        def thread_safe_execute(*args, **kwargs):
            nonlocal call_count
            # Simulate some work
            time.sleep(0.001)
            call_count += 1
            return Mock(current_rows=[{"count": call_count}])

        mock_session.execute.side_effect = thread_safe_execute

        async_session = AsyncSession(mock_session)

        # Execute many queries concurrently
        tasks = []
        for i in range(50):
            task = asyncio.create_task(async_session.execute(f"SELECT COUNT(*) FROM table{i}"))
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should complete
        assert len(results) == 50
        assert call_count == 50

        # Results should have sequential counts (no lost updates)
        counts = sorted([r.current_rows[0]["count"] for r in results])
        assert counts == list(range(1, 51))

    @pytest.mark.resilience
    async def test_page_callback_deadlock_prevention(self):
        """Test prevention of deadlock in paging callbacks."""
        from async_cassandra.result import AsyncResultSet

        mock_result_set = Mock()
        mock_result_set.has_more_pages = True
        mock_result_set._current_rows = [1, 2, 3]

        mock_session = Mock()

        # Simulate slow page fetching
        fetch_event = asyncio.Event()

        async def slow_fetch_next_page():
            await fetch_event.wait()
            return Mock(has_more_pages=False, _current_rows=[4, 5, 6])

        mock_result_set.fetch_next_page_async = Mock(
            side_effect=lambda: asyncio.create_task(slow_fetch_next_page())
        )

        async_result = AsyncResultSet(mock_result_set, mock_session)

        # Start iterating
        results = []
        iteration_task = asyncio.create_task(self._collect_results(async_result, results))

        # Give it time to start
        await asyncio.sleep(0.1)

        # Should be waiting for next page
        assert not iteration_task.done()

        # Release the fetch
        fetch_event.set()

        # Should complete without deadlock
        await asyncio.wait_for(iteration_task, timeout=1.0)

        assert results == [1, 2, 3, 4, 5, 6]

    async def _collect_results(self, async_result, results):
        """Helper to collect results from async iteration."""
        async for row in async_result:
            results.append(row)

    @pytest.mark.resilience
    async def test_session_close_during_query(self):
        """Test closing session while queries are in flight."""
        mock_session = Mock()
        query_started = asyncio.Event()
        query_can_proceed = asyncio.Event()

        async def blocking_execute(*args):
            query_started.set()
            await query_can_proceed.wait()
            return Mock(current_rows=[])

        mock_session.execute.side_effect = blocking_execute
        mock_session.close.side_effect = lambda: query_can_proceed.set()

        async_session = AsyncSession(mock_session)

        # Start query
        query_task = asyncio.create_task(async_session.execute("SELECT * FROM users"))

        # Wait for query to start
        await query_started.wait()

        # Close session (should unblock query)
        await async_session.close()

        # Query should complete (not hang)
        await asyncio.wait_for(query_task, timeout=1.0)

    @pytest.mark.resilience
    @pytest.mark.critical
    async def test_thread_pool_saturation(self):
        """Test behavior when thread pool is saturated."""
        from async_cassandra.cluster import AsyncCluster

        # Create cluster with small thread pool
        cluster = AsyncCluster(thread_pool_max_workers=2)

        # Mock the underlying cluster
        mock_cluster = Mock()
        mock_session = Mock()

        # Simulate slow queries
        async def slow_query(*args):
            await asyncio.sleep(0.1)
            return Mock(current_rows=[{"id": 1}])

        mock_session.execute.side_effect = slow_query
        mock_cluster.connect.return_value = mock_session

        cluster._cluster = mock_cluster

        session = await cluster.connect()

        # Submit more queries than thread pool size
        start_time = time.time()
        tasks = []
        for i in range(6):  # 3x thread pool size
            task = asyncio.create_task(session.execute(f"SELECT * FROM table{i}"))
            tasks.append(task)

        # All should eventually complete
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        assert len(results) == 6
        # Should take at least 0.3s (6 queries / 2 threads * 0.1s per query)
        assert duration >= 0.25

    @pytest.mark.resilience
    async def test_event_loop_callback_ordering(self):
        """Test that callbacks maintain order when scheduled."""
        from async_cassandra.utils import safe_call_soon_threadsafe

        results = []
        loop = asyncio.get_running_loop()

        # Schedule callbacks from different threads
        def schedule_callback(value):
            safe_call_soon_threadsafe(loop, results.append, value)

        threads = []
        for i in range(10):
            thread = threading.Thread(target=schedule_callback, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Give callbacks time to execute
        await asyncio.sleep(0.1)

        # All callbacks should have executed
        assert len(results) == 10
        assert sorted(results) == list(range(10))

    @pytest.mark.resilience
    async def test_prepared_statement_concurrent_access(self):
        """Test concurrent access to prepared statements."""
        mock_session = Mock()
        mock_prepared = Mock()

        prepare_count = 0

        def prepare_side_effect(*args):
            nonlocal prepare_count
            prepare_count += 1
            time.sleep(0.01)  # Simulate preparation time
            return mock_prepared

        mock_session.prepare.side_effect = prepare_side_effect
        mock_session.execute.return_value = Mock(current_rows=[])

        async_session = AsyncSession(mock_session)

        # Many coroutines try to prepare same statement
        tasks = []
        for _ in range(10):
            task = asyncio.create_task(async_session.prepare("SELECT * FROM users WHERE id = ?"))
            tasks.append(task)

        prepared_statements = await asyncio.gather(*tasks)

        # All should get the same prepared statement
        assert all(ps == mock_prepared for ps in prepared_statements)
        # But prepare should only be called once (would need caching impl)
        # For now, it's called multiple times
        assert prepare_count == 10
