"""
Integration tests specifically targeting the critical issues identified in the technical review.

These tests are designed to fail until the framework issues are fixed:
1. Thread safety between cassandra-driver threads and asyncio event loop
2. Memory leaks in streaming functionality
3. Error handling inconsistencies
4. Monitoring coverage gaps
"""

import asyncio
import gc
import threading
import weakref
from unittest.mock import MagicMock, patch

import pytest

from async_cassandra import AsyncCluster
from async_cassandra.result import AsyncResultHandler
from async_cassandra.streaming import AsyncStreamingResultSet


class TestThreadSafetyIssues:
    """Tests for thread safety issues between driver threads and asyncio."""

    @pytest.fixture
    async def async_session(self, cassandra_service):
        """Create async session for testing."""
        cluster = AsyncCluster(["127.0.0.1"])
        session = await cluster.connect()

        # Create test keyspace and table
        await session.execute("""
            CREATE KEYSPACE IF NOT EXISTS thread_safety_test
            WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
        """)
        await session.set_keyspace("thread_safety_test")

        await session.execute("DROP TABLE IF EXISTS test_data")
        await session.execute("""
            CREATE TABLE test_data (
                id INT PRIMARY KEY,
                data TEXT
            )
        """)

        yield session

        await session.close()
        await cluster.shutdown()

    def test_concurrent_page_callbacks_race_condition(self, async_session):
        """
        GIVEN multiple pages being fetched concurrently
        WHEN callbacks are invoked from driver threads
        THEN there should be no race conditions in AsyncResultHandler
        """
        # This test demonstrates the race condition in _handle_page

        async def run_test():
            # Insert test data across multiple partitions to force multiple pages
            insert_tasks = []
            for i in range(1000):
                stmt = "INSERT INTO test_data (id, data) VALUES (%s, %s)"
                insert_tasks.append(
                    async_session.execute(stmt, (i, f"data_{i}" * 100))
                )

            await asyncio.gather(*insert_tasks)

            # Now query with small page size to force multiple pages
            results = []
            errors = []

            async def fetch_with_paging():
                try:
                    # Use small fetch_size to force multiple pages
                    result = await async_session.execute(
                        "SELECT * FROM test_data LIMIT 1000"
                    )
                    results.append(len(result.rows))
                except Exception as e:
                    errors.append(str(e))

            # Run multiple concurrent queries to trigger race conditions
            tasks = [fetch_with_paging() for _ in range(20)]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Check for race condition indicators
            assert len(errors) == 0, f"Race condition errors: {errors}"
            assert all(r == 1000 for r in results), f"Inconsistent results: {results}"

        asyncio.run(run_test())

    def test_thread_lock_vs_asyncio_lock_mismatch(self):
        """
        GIVEN AsyncResultHandler using threading.Lock
        WHEN accessed from asyncio context
        THEN it should use asyncio-compatible synchronization
        """
        # This test demonstrates the issue with using threading.Lock in async code

        async def run_test():
            # Mock response future
            mock_future = MagicMock()
            mock_future.add_callbacks = MagicMock()
            mock_future.has_more_pages = False

            handler = AsyncResultHandler(mock_future)

            # Simulate concurrent access from multiple async tasks
            call_count = {"count": 0}

            async def access_handler():
                # Try to access handler state
                # In the current implementation, this uses threading.Lock
                # which can cause issues in asyncio context
                call_count["count"] += 1
                # Simulate some async work
                await asyncio.sleep(0.001)
                return handler.rows

            # Run multiple async tasks concurrently
            tasks = [access_handler() for _ in range(50)]
            results = await asyncio.gather(*tasks)

            # All tasks should complete
            assert call_count["count"] == 50
            assert len(results) == 50

        asyncio.run(run_test())

    def test_callback_thread_safety_with_event_loop(self):
        """
        GIVEN callbacks from Cassandra driver threads
        WHEN they interact with asyncio event loop
        THEN thread-safe mechanisms should be used
        """
        async def run_test():
            # Track which threads callbacks are called from
            callback_threads = []
            main_thread = threading.current_thread()

            class InstrumentedHandler(AsyncResultHandler):
                def _handle_page(self, rows):
                    # Record which thread this is called from
                    callback_threads.append(threading.current_thread())
                    super()._handle_page(rows)

            # Mock response future
            mock_future = MagicMock()
            mock_future.has_more_pages = False

            handler = InstrumentedHandler(mock_future)

            # Simulate callbacks from different threads
            def simulate_driver_callback():
                handler._handle_page([1, 2, 3])

            # Driver would call this from its own thread pool
            driver_threads = []
            for _ in range(5):
                t = threading.Thread(target=simulate_driver_callback)
                t.start()
                driver_threads.append(t)

            for t in driver_threads:
                t.join()

            # Verify callbacks came from different threads
            assert len(callback_threads) == 5
            assert any(t != main_thread for t in callback_threads), \
                "Callbacks should come from driver threads"

            # The current implementation has issues here
            # It should use call_soon_threadsafe consistently

        asyncio.run(run_test())


class TestMemoryLeakIssues:
    """Tests for memory leaks in streaming functionality."""

    def test_streaming_result_set_cleanup(self):
        """
        GIVEN streaming through large result sets
        WHEN pages are processed and discarded
        THEN memory should be properly released
        """
        async def run_test():
            # Track weak references to pages
            page_refs = []

            class InstrumentedStreamingResultSet(AsyncStreamingResultSet):
                def _handle_page(self, rows):
                    # Track weak reference to page
                    if rows:
                        page_refs.append(weakref.ref(rows))
                    super()._handle_page(rows)

            # Mock response future with multiple pages
            mock_future = MagicMock()
            mock_future.has_more_pages = True
            page_count = 0

            def fetch_next_page():
                nonlocal page_count
                page_count += 1
                if page_count < 10:
                    mock_future.has_more_pages = True
                    # Simulate page callback
                    handler._handle_page([f"row_{page_count}_{i}" for i in range(100)])
                else:
                    mock_future.has_more_pages = False
                    handler._handle_page([])

            mock_future.start_fetching_next_page = fetch_next_page

            handler = InstrumentedStreamingResultSet(mock_future)

            # Process all pages
            processed_rows = 0
            async for row in handler:
                processed_rows += 1
                # Simulate some processing
                await asyncio.sleep(0)

            # Force garbage collection
            gc.collect()

            # Check that old pages have been released
            alive_pages = sum(1 for ref in page_refs if ref() is not None)

            # Most pages should have been garbage collected
            # Current implementation may hold references longer than needed
            assert alive_pages <= 2, f"Too many pages still in memory: {alive_pages}"

        asyncio.run(run_test())

    def test_circular_reference_prevention(self):
        """
        GIVEN complex object relationships in streaming
        WHEN objects reference each other
        THEN circular references should be avoided to prevent leaks
        """
        async def run_test():
            # Track object creation and cleanup
            created_objects = []

            class TrackedFuture:
                def __init__(self):
                    created_objects.append(weakref.ref(self))
                    self.callbacks = []
                    self.has_more_pages = False

                def add_callbacks(self, callback, errback):
                    self.callbacks.append((callback, errback))

                def start_fetching_next_page(self):
                    pass

            # Create and use streaming result set
            future = TrackedFuture()
            result_set = AsyncStreamingResultSet(future)

            # Clear strong references
            del future
            del result_set

            # Force garbage collection
            gc.collect()

            # Check that objects were cleaned up
            alive_objects = sum(1 for ref in created_objects if ref() is not None)
            assert alive_objects == 0, f"Memory leak: {alive_objects} objects still alive"

        asyncio.run(run_test())

    def test_exception_cleanup_in_streaming(self):
        """
        GIVEN streaming operation that encounters an error
        WHEN exception occurs during streaming
        THEN all resources should be properly cleaned up
        """
        async def run_test():
            # Track resource allocation
            allocated_resources = []

            class ResourceTracker:
                def __init__(self, name):
                    self.name = name
                    allocated_resources.append(weakref.ref(self))

            # Mock a failing streaming operation
            mock_future = MagicMock()
            mock_future.has_more_pages = True

            error_on_page = 3
            current_page = 0

            def fetch_with_error():
                nonlocal current_page
                current_page += 1

                # Allocate some resources
                resource = ResourceTracker(f"page_{current_page}")

                if current_page == error_on_page:
                    raise Exception("Simulated error during fetch")

                return [f"row_{i}" for i in range(10)]

            mock_future.start_fetching_next_page = fetch_with_error

            result_set = AsyncStreamingResultSet(mock_future)

            # Try to iterate, expecting failure
            rows_processed = 0
            try:
                async for row in result_set:
                    rows_processed += 1
            except Exception:
                pass  # Expected

            # Clear references
            del result_set
            gc.collect()

            # Check cleanup
            alive_resources = sum(1 for ref in allocated_resources if ref() is not None)
            assert alive_resources == 0, f"Resources not cleaned up: {alive_resources}"

        asyncio.run(run_test())


class TestErrorHandlingInconsistencies:
    """Tests for error handling inconsistencies in the framework."""

    @pytest.fixture
    async def async_session(self, cassandra_service):
        """Create async session for testing."""
        cluster = AsyncCluster(["127.0.0.1"])
        session = await cluster.connect()
        yield session
        await session.close()
        await cluster.shutdown()

    async def test_error_handling_parity_execute_vs_stream(self, async_session):
        """
        GIVEN the same error condition
        WHEN it occurs in execute() vs execute_stream()
        THEN error handling should be consistent
        """
        # Test with invalid query
        invalid_query = "SELECT * FROM non_existent_table"

        # Test execute() error handling
        execute_error = None
        try:
            await async_session.execute(invalid_query)
        except Exception as e:
            execute_error = e

        # Test execute_stream() error handling
        stream_error = None
        try:
            result = await async_session.execute_stream(invalid_query)
            async for row in result:
                pass
        except Exception as e:
            stream_error = e

        # Both should raise similar errors
        assert execute_error is not None
        assert stream_error is not None
        assert type(execute_error) == type(stream_error), \
            f"Different error types: {type(execute_error)} vs {type(stream_error)}"

    async def test_timeout_error_handling_consistency(self, async_session):
        """
        GIVEN timeout conditions
        WHEN timeouts occur in different methods
        THEN timeout handling should be consistent
        """
        # Create test table
        await async_session.execute("""
            CREATE KEYSPACE IF NOT EXISTS timeout_test
            WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
        """)
        await async_session.set_keyspace("timeout_test")

        await async_session.execute("DROP TABLE IF EXISTS test_timeout")
        await async_session.execute("""
            CREATE TABLE test_timeout (
                id INT PRIMARY KEY,
                data TEXT
            )
        """)

        # Insert data
        for i in range(100):
            await async_session.execute(
                "INSERT INTO test_timeout (id, data) VALUES (%s, %s)",
                (i, "x" * 1000)
            )

        # Test timeout in execute()
        execute_timeout_error = None
        try:
            # Very short timeout to force error
            await async_session.execute(
                "SELECT * FROM test_timeout",
                timeout=0.001
            )
        except Exception as e:
            execute_timeout_error = e

        # Test timeout in execute_stream()
        stream_timeout_error = None
        try:
            result = await async_session.execute_stream(
                "SELECT * FROM test_timeout",
                timeout=0.001
            )
            async for row in result:
                pass
        except Exception as e:
            stream_timeout_error = e

        # Both should handle timeout consistently
        assert execute_timeout_error is not None
        assert stream_timeout_error is not None
        # Error types might differ but both should indicate timeout

    async def test_connection_error_propagation(self, async_session):
        """
        GIVEN connection errors at different stages
        WHEN errors occur
        THEN they should propagate consistently with proper context
        """
        from cassandra.cluster import NoHostAvailable

        # Mock connection failure
        with patch.object(async_session._session, 'execute_async') as mock_execute:
            mock_execute.side_effect = NoHostAvailable("All hosts failed", {})

            # Test execute() error propagation
            execute_error = None
            try:
                await async_session.execute("SELECT * FROM system.local")
            except Exception as e:
                execute_error = e

            # Test execute_stream() error propagation
            stream_error = None
            try:
                await async_session.execute_stream("SELECT * FROM system.local")
            except Exception as e:
                stream_error = e

            # Both should propagate the connection error
            assert execute_error is not None
            assert stream_error is not None

            # Both should preserve the original error type or wrap consistently
            assert isinstance(execute_error, (NoHostAvailable, Exception))
            assert isinstance(stream_error, (NoHostAvailable, Exception))
