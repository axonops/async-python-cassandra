"""
Integration tests for network failure scenarios against real Cassandra.
"""

import asyncio
import uuid
import time
import subprocess
from datetime import datetime
import pytest
import pytest_asyncio

from async_cassandra import AsyncCluster, AsyncCassandraSession
from cassandra.cluster import NoHostAvailable
from cassandra import OperationTimedOut


def is_docker_available():
    """Check if Docker is available for network manipulation."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


class NetworkManipulator:
    """Utility to simulate network failures using Docker or tc (traffic control)."""
    
    def __init__(self, container_name: str):
        self.container_name = container_name
        self.docker_available = is_docker_available()
    
    async def add_latency(self, latency_ms: int):
        """Add network latency to Cassandra container."""
        if self.docker_available:
            cmd = [
                "docker", "exec", self.container_name,
                "tc", "qdisc", "add", "dev", "eth0", "root",
                "netem", "delay", f"{latency_ms}ms"
            ]
            subprocess.run(cmd, capture_output=True)
    
    async def add_packet_loss(self, loss_percent: int):
        """Add packet loss to simulate unreliable network."""
        if self.docker_available:
            cmd = [
                "docker", "exec", self.container_name,
                "tc", "qdisc", "add", "dev", "eth0", "root",
                "netem", "loss", f"{loss_percent}%"
            ]
            subprocess.run(cmd, capture_output=True)
    
    async def pause_container(self):
        """Pause Cassandra container to simulate node failure."""
        if self.docker_available:
            subprocess.run(["docker", "pause", self.container_name], capture_output=True)
    
    async def unpause_container(self):
        """Unpause Cassandra container."""
        if self.docker_available:
            subprocess.run(["docker", "unpause", self.container_name], capture_output=True)
    
    async def reset_network(self):
        """Reset network conditions to normal."""
        if self.docker_available:
            cmd = [
                "docker", "exec", self.container_name,
                "tc", "qdisc", "del", "dev", "eth0", "root"
            ]
            subprocess.run(cmd, capture_output=True, stderr=subprocess.DEVNULL)


@pytest_asyncio.fixture
async def session_with_retry(cassandra_container) -> AsyncCassandraSession:
    """Create test session with retry policy for failure testing."""
    from async_cassandra import AsyncRetryPolicy
    
    retry_policy = AsyncRetryPolicy(
        read_retry_count=2,
        write_retry_count=2,
        unavailable_retry_count=2
    )
    
    cluster = AsyncCluster(
        contact_points=[cassandra_container.get_contact_point()],
        port=cassandra_container.get_mapped_port(9042),
        retry_policy=retry_policy,
        request_timeout=5.0,  # Lower timeout for faster failure detection
    )
    session = await cluster.connect()
    
    # Create test keyspace and table
    await session.execute("""
        CREATE KEYSPACE IF NOT EXISTS test_failures
        WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1}
    """)
    await session.set_keyspace("test_failures")
    
    await session.execute("DROP TABLE IF EXISTS failure_test")
    await session.execute("""
        CREATE TABLE failure_test (
            id UUID PRIMARY KEY,
            data TEXT,
            counter INT,
            created_at TIMESTAMP
        )
    """)
    
    yield session
    
    await session.close()
    await cluster.shutdown()


@pytest_asyncio.fixture
async def network_manipulator(cassandra_container):
    """Create network manipulator for the test container."""
    # Get container name/ID from testcontainers
    container_name = cassandra_container._container.id[:12]
    manipulator = NetworkManipulator(container_name)
    
    yield manipulator
    
    # Always reset network conditions after test
    await manipulator.reset_network()


class TestNetworkFailures:
    """Test network failure scenarios."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_docker_available(), reason="Docker required for network tests")
    async def test_high_latency_operations(self, session_with_retry: AsyncCassandraSession, network_manipulator):
        """Test operations under high network latency."""
        # Prepare statements
        insert_stmt = await session_with_retry.prepare(
            "INSERT INTO failure_test (id, data, counter, created_at) VALUES (?, ?, ?, ?)"
        )
        select_stmt = await session_with_retry.prepare(
            "SELECT * FROM failure_test WHERE id = ?"
        )
        
        # Add 200ms latency
        await network_manipulator.add_latency(200)
        await asyncio.sleep(1)  # Allow network changes to take effect
        
        # Test operations under latency
        test_id = uuid.uuid4()
        
        # Write should succeed but be slow
        start = time.time()
        await session_with_retry.execute(insert_stmt, [
            test_id, "high_latency_test", 1, datetime.utcnow()
        ])
        write_time = time.time() - start
        assert write_time > 0.2  # Should take at least 200ms
        
        # Read should also succeed but be slow
        start = time.time()
        result = await session_with_retry.execute(select_stmt, [test_id])
        read_time = time.time() - start
        assert read_time > 0.2
        assert result.one() is not None
        
        # Reset network
        await network_manipulator.reset_network()
        await asyncio.sleep(1)
        
        # Operations should be fast again
        start = time.time()
        await session_with_retry.execute(select_stmt, [test_id])
        normal_time = time.time() - start
        assert normal_time < 0.1  # Should be much faster
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_docker_available(), reason="Docker required for network tests")
    async def test_packet_loss_resilience(self, session_with_retry: AsyncCassandraSession, network_manipulator):
        """Test resilience to packet loss."""
        insert_stmt = await session_with_retry.prepare(
            "INSERT INTO failure_test (id, data, counter, created_at) VALUES (?, ?, ?, ?)"
        )
        
        # Add 10% packet loss
        await network_manipulator.add_packet_loss(10)
        await asyncio.sleep(1)
        
        # Execute many operations - some should fail and retry
        success_count = 0
        failure_count = 0
        retry_count = 0
        
        for i in range(50):
            test_id = uuid.uuid4()
            try:
                start = time.time()
                await session_with_retry.execute(insert_stmt, [
                    test_id, f"packet_loss_test_{i}", i, datetime.utcnow()
                ])
                duration = time.time() - start
                success_count += 1
                
                # Longer duration indicates retries occurred
                if duration > 0.5:
                    retry_count += 1
                    
            except Exception:
                failure_count += 1
        
        # With retry policy, most should succeed
        assert success_count >= 45  # At least 90% success rate
        assert retry_count > 0  # Some operations should have required retries
        
        # Reset network
        await network_manipulator.reset_network()
    
    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, cassandra_container):
        """Test handling of connection timeouts."""
        # Create cluster with very short timeout
        cluster = AsyncCluster(
            contact_points=[cassandra_container.get_contact_point()],
            port=cassandra_container.get_mapped_port(9042),
            connect_timeout=0.001,  # 1ms timeout - will always fail
        )
        
        # Connection should fail with timeout
        with pytest.raises(NoHostAvailable) as exc_info:
            await cluster.connect()
        
        # Should contain connection error
        assert any("ConnectionException" in str(error) for error in exc_info.value.errors.values())
        
        await cluster.shutdown()
    
    @pytest.mark.asyncio
    async def test_request_timeout_handling(self, session_with_retry: AsyncCassandraSession):
        """Test handling of request timeouts."""
        # Create a large dataset that will take time to query
        insert_stmt = await session_with_retry.prepare(
            "INSERT INTO failure_test (id, data, counter, created_at) VALUES (?, ?, ?, ?)"
        )
        
        # Insert many records
        for i in range(1000):
            await session_with_retry.execute(insert_stmt, [
                uuid.uuid4(), "x" * 1000, i, datetime.utcnow()
            ])
        
        # Try to query all with very short timeout
        with pytest.raises(OperationTimedOut):
            await session_with_retry.execute(
                "SELECT * FROM failure_test",
                timeout=0.001  # 1ms timeout
            )
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_docker_available(), reason="Docker required for network tests")
    async def test_node_failure_recovery(self, session_with_retry: AsyncCassandraSession, network_manipulator):
        """Test recovery from temporary node failure."""
        insert_stmt = await session_with_retry.prepare(
            "INSERT INTO failure_test (id, data, counter, created_at) VALUES (?, ?, ?, ?)"
        )
        select_stmt = await session_with_retry.prepare(
            "SELECT * FROM failure_test WHERE id = ?"
        )
        
        # Insert initial data
        test_id = uuid.uuid4()
        await session_with_retry.execute(insert_stmt, [
            test_id, "recovery_test", 1, datetime.utcnow()
        ])
        
        # Verify data is accessible
        result = await session_with_retry.execute(select_stmt, [test_id])
        assert result.one() is not None
        
        # Simulate node failure
        await network_manipulator.pause_container()
        
        # Operations should fail
        failed = False
        try:
            await session_with_retry.execute(select_stmt, [test_id])
        except (NoHostAvailable, OperationTimedOut):
            failed = True
        assert failed
        
        # Recover node
        await network_manipulator.unpause_container()
        await asyncio.sleep(2)  # Allow recovery time
        
        # Operations should work again
        result = await session_with_retry.execute(select_stmt, [test_id])
        assert result.one() is not None
    
    @pytest.mark.asyncio
    async def test_concurrent_failures(self, session_with_retry: AsyncCassandraSession):
        """Test handling of failures during concurrent operations."""
        insert_stmt = await session_with_retry.prepare(
            "INSERT INTO failure_test (id, data, counter, created_at) VALUES (?, ?, ?, ?)"
        )
        
        async def failing_operation(should_fail: bool):
            """Operation that might fail based on flag."""
            test_id = uuid.uuid4()
            
            if should_fail:
                # Use invalid keyspace to force failure
                try:
                    await session_with_retry.execute(
                        "INSERT INTO nonexistent_table (id) VALUES (?)",
                        [test_id]
                    )
                    return "unexpected_success"
                except Exception:
                    return "expected_failure"
            else:
                await session_with_retry.execute(insert_stmt, [
                    test_id, "concurrent_test", 1, datetime.utcnow()
                ])
                return "success"
        
        # Mix successful and failing operations
        operations = []
        for i in range(100):
            should_fail = i % 3 == 0  # Every 3rd operation fails
            operations.append(failing_operation(should_fail))
        
        # Execute concurrently
        results = await asyncio.gather(*operations, return_exceptions=True)
        
        # Count results
        success_count = sum(1 for r in results if r == "success")
        expected_failures = sum(1 for r in results if r == "expected_failure")
        unexpected_errors = sum(1 for r in results if isinstance(r, Exception))
        
        assert success_count >= 65  # ~2/3 should succeed
        assert expected_failures >= 30  # ~1/3 should fail as expected
        assert unexpected_errors < 5  # Very few unexpected errors
    
    @pytest.mark.asyncio
    async def test_retry_policy_effectiveness(self, cassandra_container):
        """Test that retry policy improves success rate."""
        # Create two sessions - one with retry, one without
        cluster_no_retry = AsyncCluster(
            contact_points=[cassandra_container.get_contact_point()],
            port=cassandra_container.get_mapped_port(9042),
            request_timeout=1.0,
        )
        
        from async_cassandra import AsyncRetryPolicy
        
        cluster_with_retry = AsyncCluster(
            contact_points=[cassandra_container.get_contact_point()],
            port=cassandra_container.get_mapped_port(9042),
            request_timeout=1.0,
            retry_policy=AsyncRetryPolicy(
                read_retry_count=3,
                write_retry_count=3,
                unavailable_retry_count=3
            )
        )
        
        session_no_retry = await cluster_no_retry.connect()
        session_with_retry = await cluster_with_retry.connect()
        
        # Use test_failures keyspace
        await session_no_retry.execute("""
            CREATE KEYSPACE IF NOT EXISTS test_failures
            WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1}
        """)
        await session_no_retry.set_keyspace("test_failures")
        await session_with_retry.set_keyspace("test_failures")
        
        # Prepare statement with very aggressive timeout to force retries
        stmt = "SELECT * FROM system.local WHERE key = 'local'"
        
        async def attempt_query(session, timeout):
            try:
                await session.execute(stmt, timeout=timeout)
                return True
            except Exception:
                return False
        
        # Test with very short timeout to induce failures
        short_timeout = 0.01  # 10ms - likely to fail sometimes
        
        # Run many attempts with each session
        tasks_no_retry = [attempt_query(session_no_retry, short_timeout) for _ in range(50)]
        tasks_with_retry = [attempt_query(session_with_retry, short_timeout) for _ in range(50)]
        
        results_no_retry = await asyncio.gather(*tasks_no_retry)
        results_with_retry = await asyncio.gather(*tasks_with_retry)
        
        success_no_retry = sum(results_no_retry)
        success_with_retry = sum(results_with_retry)
        
        # Retry policy should improve success rate
        assert success_with_retry >= success_no_retry
        
        # Cleanup
        await session_no_retry.close()
        await session_with_retry.close()
        await cluster_no_retry.shutdown()
        await cluster_with_retry.shutdown()
    
    @pytest.mark.asyncio
    async def test_streaming_with_failures(self, session_with_retry: AsyncCassandraSession):
        """Test streaming operations with network issues."""
        from async_cassandra import StreamConfig
        
        # Insert test data
        insert_stmt = await session_with_retry.prepare(
            "INSERT INTO failure_test (id, data, counter, created_at) VALUES (?, ?, ?, ?)"
        )
        
        for i in range(1000):
            await session_with_retry.execute(insert_stmt, [
                uuid.uuid4(), f"stream_test_{i}", i, datetime.utcnow()
            ])
        
        # Stream with potential failures
        config = StreamConfig(fetch_size=50, max_pages=5)
        
        # Track streaming progress
        rows_received = 0
        errors_encountered = 0
        
        try:
            result = await session_with_retry.execute_stream(
                "SELECT * FROM failure_test",
                stream_config=config
            )
            
            async for row in result:
                rows_received += 1
                
                # Simulate intermittent processing issues
                if rows_received % 100 == 0:
                    await asyncio.sleep(0.1)
                    
        except Exception:
            errors_encountered += 1
        
        # Should receive at least some rows even with issues
        assert rows_received > 0
        assert rows_received <= 1000  # May not get all due to max_pages
    
    @pytest.mark.asyncio
    async def test_batch_operations_with_failures(self, session_with_retry: AsyncCassandraSession):
        """Test batch operations under failure conditions."""
        from cassandra.query import BatchStatement, BatchType
        
        insert_stmt = await session_with_retry.prepare(
            "INSERT INTO failure_test (id, data, counter, created_at) VALUES (?, ?, ?, ?)"
        )
        
        # Create batches of different sizes
        batch_sizes = [10, 50, 100]
        results = {}
        
        for size in batch_sizes:
            batch = BatchStatement(batch_type=BatchType.UNLOGGED)
            
            for i in range(size):
                batch.add(insert_stmt, [
                    uuid.uuid4(), f"batch_{size}_{i}", i, datetime.utcnow()
                ])
            
            # Execute batch with short timeout to potentially trigger retries
            try:
                start = time.time()
                await session_with_retry.execute(batch, timeout=1.0)
                duration = time.time() - start
                results[size] = {"success": True, "duration": duration}
            except Exception as exc:
                results[size] = {"success": False, "error": str(exc)}
        
        # At least small batches should succeed
        assert results[10]["success"]
        
        # Larger batches might take longer due to retries
        if results[50]["success"] and results[10]["success"]:
            assert results[50]["duration"] >= results[10]["duration"]