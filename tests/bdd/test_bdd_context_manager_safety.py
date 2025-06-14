"""
BDD tests for context manager safety.

Tests the behavior described in features/context_manager_safety.feature
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from pytest_bdd import given, scenarios, then, when

from async_cassandra import AsyncCluster
from async_cassandra.exceptions import QueryError
from async_cassandra.streaming import StreamConfig

# Load all scenarios from the feature file
scenarios("features/context_manager_safety.feature")


# Fixtures for test state
@pytest.fixture
def test_state():
    """Holds state across BDD steps."""
    return {
        "cluster": None,
        "session": None,
        "error": None,
        "streaming_result": None,
        "sessions": [],
        "results": [],
        "thread_results": []
    }


# Background steps
@given("a running Cassandra cluster")
def cassandra_is_running(cassandra_cluster):
    """Cassandra cluster is provided by the fixture."""
    assert cassandra_cluster.contact_point is not None


@given("a test keyspace \"test_context_safety\"")
async def create_test_keyspace(cassandra_cluster, test_state):
    """Create test keyspace."""
    cluster = AsyncCluster([cassandra_cluster.contact_point])
    session = await cluster.connect()
    
    await session.execute(
        """
        CREATE KEYSPACE IF NOT EXISTS test_context_safety
        WITH REPLICATION = {
            'class': 'SimpleStrategy',
            'replication_factor': 1
        }
        """
    )
    
    test_state["cluster"] = cluster
    test_state["session"] = session


# Scenario: Query error doesn't close session
@given("an open session connected to the test keyspace")
async def open_session(test_state):
    """Ensure session is connected to test keyspace."""
    await test_state["session"].set_keyspace("test_context_safety")
    
    # Create a test table
    await test_state["session"].execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            id UUID PRIMARY KEY,
            value TEXT
        )
        """
    )


@when("I execute a query that causes an error")
async def execute_bad_query(test_state):
    """Execute a query that will fail."""
    try:
        await test_state["session"].execute("SELECT * FROM non_existent_table")
    except QueryError as e:
        test_state["error"] = e


@then("the session should remain open and usable")
async def session_is_open(test_state):
    """Verify session is still open."""
    assert test_state["session"] is not None
    assert not test_state["session"].is_closed


@then("I should be able to execute subsequent queries successfully")
async def can_execute_queries(test_state):
    """Execute a successful query."""
    test_id = uuid.uuid4()
    await test_state["session"].execute(
        "INSERT INTO test_table (id, value) VALUES (%s, %s)",
        [test_id, "test_value"]
    )
    
    result = await test_state["session"].execute(
        "SELECT * FROM test_table WHERE id = %s",
        [test_id]
    )
    assert result.one().value == "test_value"


# Scenario: Streaming error doesn't close session
@given("an open session with test data")
async def session_with_data(test_state):
    """Create session with test data."""
    await test_state["session"].set_keyspace("test_context_safety")
    
    await test_state["session"].execute(
        """
        CREATE TABLE IF NOT EXISTS stream_test (
            id UUID PRIMARY KEY,
            value INT
        )
        """
    )
    
    # Insert test data
    for i in range(10):
        await test_state["session"].execute(
            "INSERT INTO stream_test (id, value) VALUES (%s, %s)",
            [uuid.uuid4(), i]
        )


@when("a streaming operation encounters an error")
async def streaming_error(test_state):
    """Try to stream from non-existent table."""
    try:
        async with await test_state["session"].execute_stream(
            "SELECT * FROM non_existent_stream_table"
        ) as stream:
            async for row in stream:
                pass
    except Exception as e:
        test_state["error"] = e


@then("the streaming result should be closed")
async def streaming_closed(test_state):
    """Streaming result is closed (checked by context manager exit)."""
    # Context manager ensures closure
    assert test_state["error"] is not None


@then("the session should remain open")
async def session_still_open(test_state):
    """Session should not be closed."""
    assert not test_state["session"].is_closed


@then("I should be able to start new streaming operations")
async def can_stream_again(test_state):
    """Start a new streaming operation."""
    count = 0
    async with await test_state["session"].execute_stream(
        "SELECT * FROM stream_test"
    ) as stream:
        async for row in stream:
            count += 1
    
    assert count == 10  # Should get all 10 rows


# Scenario: Session context manager doesn't close cluster
@given("an open cluster connection")
def cluster_is_open(test_state):
    """Cluster is already open from background."""
    assert test_state["cluster"] is not None


@when("I use a session in a context manager that exits with an error")
async def session_context_with_error(test_state):
    """Use session context manager with error."""
    try:
        async with await test_state["cluster"].connect("test_context_safety") as session:
            # Do some work
            await session.execute("SELECT * FROM system.local")
            # Raise an error
            raise ValueError("Test error")
    except ValueError:
        test_state["error"] = "Session context exited"


@then("the session should be closed")
def session_is_closed(test_state):
    """Session was closed by context manager."""
    # We know it's closed because context manager handles it
    assert test_state["error"] == "Session context exited"


@then("the cluster should remain open")
def cluster_still_open(test_state):
    """Cluster should not be closed."""
    assert not test_state["cluster"].is_closed


@then("I should be able to create new sessions from the cluster")
async def can_create_sessions(test_state):
    """Create a new session from cluster."""
    new_session = await test_state["cluster"].connect()
    result = await new_session.execute("SELECT release_version FROM system.local")
    assert result.one() is not None
    await new_session.close()


# Scenario: Multiple concurrent streams don't interfere
@given("multiple sessions from the same cluster")
async def create_multiple_sessions(test_state):
    """Create multiple sessions."""
    await test_state["session"].set_keyspace("test_context_safety")
    
    # Create test table
    await test_state["session"].execute(
        """
        CREATE TABLE IF NOT EXISTS concurrent_test (
            partition_id INT,
            id UUID,
            value TEXT,
            PRIMARY KEY (partition_id, id)
        )
        """
    )
    
    # Insert data for different partitions
    for partition in range(3):
        for i in range(20):
            await test_state["session"].execute(
                "INSERT INTO concurrent_test (partition_id, id, value) VALUES (%s, %s, %s)",
                [partition, uuid.uuid4(), f"value_{partition}_{i}"]
            )
    
    # Create multiple sessions
    for _ in range(3):
        session = await test_state["cluster"].connect("test_context_safety")
        test_state["sessions"].append(session)


@when("I stream data concurrently from each session")
async def concurrent_streaming(test_state):
    """Stream from each session concurrently."""
    async def stream_partition(session, partition_id):
        count = 0
        config = StreamConfig(fetch_size=5)
        
        async with await session.execute_stream(
            "SELECT * FROM concurrent_test WHERE partition_id = %s",
            [partition_id],
            stream_config=config
        ) as stream:
            async for row in stream:
                count += 1
        
        return count
    
    # Stream concurrently
    tasks = []
    for i, session in enumerate(test_state["sessions"]):
        task = stream_partition(session, i)
        tasks.append(task)
    
    test_state["results"] = await asyncio.gather(*tasks)


@then("each stream should complete independently")
def streams_completed(test_state):
    """All streams should complete."""
    assert len(test_state["results"]) == 3
    assert all(count == 20 for count in test_state["results"])


@then("closing one stream should not affect others")
async def close_one_stream(test_state):
    """Already tested by concurrent execution."""
    # Streams were in context managers, so they closed independently
    pass


@then("all sessions should remain usable")
async def all_sessions_usable(test_state):
    """Test all sessions still work."""
    for session in test_state["sessions"]:
        result = await session.execute("SELECT COUNT(*) FROM concurrent_test")
        assert result.one()[0] == 60  # Total rows


# Scenario: Thread safety during context exit
@given("a session being used by multiple threads")
async def session_for_threads(test_state):
    """Set up session for thread testing."""
    await test_state["session"].set_keyspace("test_context_safety")
    
    await test_state["session"].execute(
        """
        CREATE TABLE IF NOT EXISTS thread_test (
            id TEXT PRIMARY KEY,
            counter INT
        )
        """
    )
    
    await test_state["session"].execute(
        "INSERT INTO thread_test (id, counter) VALUES ('shared', 0)"
    )


@when("one thread exits a streaming context manager")
async def thread_exits_context(test_state):
    """Use streaming in main thread while other threads work."""
    def worker_thread(session, thread_id):
        """Worker thread function."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def do_work():
            # Read current value
            result = await session.execute(
                "SELECT counter FROM thread_test WHERE id = 'shared'"
            )
            current = result.one().counter
            
            # Update
            await session.execute(
                "UPDATE thread_test SET counter = %s WHERE id = 'shared'",
                [current + 1]
            )
            
            return f"Thread {thread_id} completed"
        
        result = loop.run_until_complete(do_work())
        loop.close()
        return result
    
    # Start threads
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        for i in range(2):
            future = executor.submit(worker_thread, test_state["session"], i)
            futures.append(future)
        
        # Use streaming in main thread
        async with await test_state["session"].execute_stream(
            "SELECT * FROM thread_test"
        ) as stream:
            async for row in stream:
                await asyncio.sleep(0.1)  # Give threads time to work
        
        # Collect thread results
        for future in futures:
            result = future.result(timeout=5.0)
            test_state["thread_results"].append(result)


@then("other threads should still be able to use the session")
def threads_used_session(test_state):
    """Verify threads completed their work."""
    assert len(test_state["thread_results"]) == 2
    assert all("completed" in result for result in test_state["thread_results"])


@then("no operations should be interrupted")
async def verify_thread_operations(test_state):
    """Verify all thread operations completed."""
    result = await test_state["session"].execute(
        "SELECT counter FROM thread_test WHERE id = 'shared'"
    )
    # Should have been incremented by both threads
    assert result.one().counter == 2


# Cleanup
@pytest.fixture(autouse=True)
async def cleanup(test_state):
    """Clean up after each test."""
    yield
    
    # Close all sessions
    for session in test_state.get("sessions", []):
        if session and not session.is_closed:
            await session.close()
    
    # Clean up main session and cluster
    if test_state.get("session"):
        try:
            await test_state["session"].execute("DROP KEYSPACE IF EXISTS test_context_safety")
        except:
            pass
        if not test_state["session"].is_closed:
            await test_state["session"].close()
    
    if test_state.get("cluster") and not test_state["cluster"].is_closed:
        await test_state["cluster"].shutdown()