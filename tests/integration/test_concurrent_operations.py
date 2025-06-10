"""
Comprehensive integration tests for concurrent operations against real Cassandra.
"""

import asyncio
import uuid
import time
from typing import List, Tuple
from datetime import datetime
import pytest
import pytest_asyncio

from async_cassandra import AsyncCluster, AsyncCassandraSession
from cassandra.cluster import NoHostAvailable
from cassandra import ConsistencyLevel, WriteTimeout, ReadTimeout


@pytest_asyncio.fixture
async def session(cassandra_container) -> AsyncCassandraSession:
    """Create test session with real Cassandra."""
    cluster = AsyncCluster(
        contact_points=[cassandra_container.get_contact_point()],
        port=cassandra_container.get_mapped_port(9042),
    )
    session = await cluster.connect()
    
    # Create test keyspace and table
    await session.execute("""
        CREATE KEYSPACE IF NOT EXISTS test_concurrent
        WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1}
    """)
    await session.set_keyspace("test_concurrent")
    
    await session.execute("DROP TABLE IF EXISTS stress_test")
    await session.execute("""
        CREATE TABLE stress_test (
            id UUID PRIMARY KEY,
            partition_key INT,
            data TEXT,
            counter INT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    
    await session.execute("DROP TABLE IF EXISTS counters")
    await session.execute("""
        CREATE TABLE counters (
            id UUID PRIMARY KEY,
            value COUNTER
        )
    """)
    
    yield session
    
    await session.close()
    await cluster.shutdown()


class TestConcurrentOperations:
    """Test concurrent operations with real Cassandra."""
    
    @pytest.mark.asyncio
    async def test_massive_concurrent_reads(self, session: AsyncCassandraSession):
        """Test handling 1000+ concurrent read operations."""
        # Insert test data
        insert_stmt = await session.prepare(
            "INSERT INTO stress_test (id, partition_key, data, counter, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        
        test_ids = []
        for i in range(100):
            test_id = uuid.uuid4()
            test_ids.append(test_id)
            await session.execute(insert_stmt, [
                test_id, i % 10, f"test_data_{i}", i, datetime.utcnow()
            ])
        
        # Perform 1000 concurrent reads
        select_stmt = await session.prepare(
            "SELECT * FROM stress_test WHERE id = ?"
        )
        
        async def read_record(record_id):
            start = time.time()
            result = await session.execute(select_stmt, [record_id])
            duration = time.time() - start
            return result.one(), duration
        
        # Create 1000 read tasks (reading the same 100 records multiple times)
        tasks = []
        for i in range(1000):
            record_id = test_ids[i % len(test_ids)]
            tasks.append(read_record(record_id))
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Verify results
        assert len(results) == 1000
        assert all(result[0] is not None for result in results)
        
        # Performance assertions
        avg_duration = sum(r[1] for r in results) / len(results)
        assert avg_duration < 0.1  # Average read should be under 100ms
        assert total_time < 10  # Total time should be under 10 seconds
        
        print(f"Completed 1000 concurrent reads in {total_time:.2f}s")
        print(f"Average read duration: {avg_duration*1000:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_concurrent_writes_different_partitions(self, session: AsyncCassandraSession):
        """Test concurrent writes to different partitions."""
        insert_stmt = await session.prepare(
            "INSERT INTO stress_test (id, partition_key, data, counter, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        
        async def write_batch(partition_key: int, count: int):
            tasks = []
            for i in range(count):
                test_id = uuid.uuid4()
                task = session.execute(insert_stmt, [
                    test_id, partition_key, f"data_{partition_key}_{i}", 
                    i, datetime.utcnow()
                ])
                tasks.append(task)
            await asyncio.gather(*tasks)
            return count
        
        # Write to 10 different partitions concurrently, 100 records each
        start_time = time.time()
        partition_tasks = [
            write_batch(partition, 100) for partition in range(10)
        ]
        results = await asyncio.gather(*partition_tasks)
        total_time = time.time() - start_time
        
        assert sum(results) == 1000
        assert total_time < 5  # Should complete within 5 seconds
        
        # Verify data
        count_result = await session.execute(
            "SELECT COUNT(*) FROM stress_test"
        )
        assert count_result.one()[0] >= 1000
    
    @pytest.mark.asyncio
    async def test_concurrent_read_write_mix(self, session: AsyncCassandraSession):
        """Test mixed concurrent read and write operations."""
        # Prepare statements
        insert_stmt = await session.prepare(
            "INSERT INTO stress_test (id, partition_key, data, counter, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        select_stmt = await session.prepare(
            "SELECT * FROM stress_test WHERE id = ?"
        )
        update_stmt = await session.prepare(
            "UPDATE stress_test SET counter = ?, updated_at = ? WHERE id = ?"
        )
        
        # Create initial data
        test_ids = []
        for i in range(50):
            test_id = uuid.uuid4()
            test_ids.append(test_id)
            await session.execute(insert_stmt, [
                test_id, i % 5, f"initial_data_{i}", 0, datetime.utcnow()
            ])
        
        # Define mixed operations
        async def write_operation():
            test_id = uuid.uuid4()
            await session.execute(insert_stmt, [
                test_id, 99, "new_data", 1, datetime.utcnow()
            ])
            return "write"
        
        async def read_operation():
            test_id = test_ids[asyncio.get_event_loop().time() % len(test_ids)]
            result = await session.execute(select_stmt, [test_id])
            return "read", result.one()
        
        async def update_operation():
            test_id = test_ids[int(asyncio.get_event_loop().time()) % len(test_ids)]
            await session.execute(update_stmt, [
                int(time.time()), datetime.utcnow(), test_id
            ])
            return "update"
        
        # Create mixed workload: 40% reads, 40% writes, 20% updates
        operations = []
        for _ in range(400):  # 400 reads
            operations.append(read_operation())
        for _ in range(400):  # 400 writes
            operations.append(write_operation())
        for _ in range(200):  # 200 updates
            operations.append(update_operation())
        
        # Shuffle operations
        import random
        random.shuffle(operations)
        
        # Execute all operations concurrently
        start_time = time.time()
        results = await asyncio.gather(*operations, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Count operation types
        read_count = sum(1 for r in results if isinstance(r, tuple) and r[0] == "read")
        write_count = sum(1 for r in results if r == "write")
        update_count = sum(1 for r in results if r == "update")
        error_count = sum(1 for r in results if isinstance(r, Exception))
        
        assert read_count >= 380  # Allow for some failures
        assert write_count >= 380
        assert update_count >= 180
        assert error_count < 20  # Less than 2% error rate
        assert total_time < 10  # Should complete within 10 seconds
    
    @pytest.mark.asyncio
    async def test_concurrent_batch_operations(self, session: AsyncCassandraSession):
        """Test concurrent batch operations."""
        from cassandra.query import BatchStatement, BatchType
        
        insert_stmt = await session.prepare(
            "INSERT INTO stress_test (id, partition_key, data, counter, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        
        async def execute_batch(batch_id: int, size: int):
            batch = BatchStatement(batch_type=BatchType.UNLOGGED)
            for i in range(size):
                test_id = uuid.uuid4()
                batch.add(insert_stmt, [
                    test_id, batch_id, f"batch_{batch_id}_item_{i}", 
                    i, datetime.utcnow()
                ])
            
            start = time.time()
            await session.execute(batch)
            return time.time() - start
        
        # Execute 20 batches concurrently, each with 50 items
        batch_tasks = [execute_batch(i, 50) for i in range(20)]
        start_time = time.time()
        durations = await asyncio.gather(*batch_tasks)
        total_time = time.time() - start_time
        
        assert len(durations) == 20
        assert all(d < 1.0 for d in durations)  # Each batch under 1 second
        assert total_time < 5  # Total time under 5 seconds
        
        # Verify data
        count_result = await session.execute(
            "SELECT COUNT(*) FROM stress_test"
        )
        assert count_result.one()[0] >= 1000  # 20 batches * 50 items
    
    @pytest.mark.asyncio
    async def test_concurrent_prepared_statements(self, session: AsyncCassandraSession):
        """Test concurrent execution of multiple prepared statements."""
        # Prepare multiple statement types
        statements = {
            'insert': await session.prepare(
                "INSERT INTO stress_test (id, partition_key, data, counter, created_at) "
                "VALUES (?, ?, ?, ?, ?)"
            ),
            'select_by_id': await session.prepare(
                "SELECT * FROM stress_test WHERE id = ?"
            ),
            'select_by_partition': await session.prepare(
                "SELECT * FROM stress_test WHERE partition_key = ? ALLOW FILTERING"
            ),
            'update': await session.prepare(
                "UPDATE stress_test SET counter = counter + 1 WHERE id = ?"
            ),
            'delete': await session.prepare(
                "DELETE FROM stress_test WHERE id = ?"
            )
        }
        
        # Create test data
        test_ids = []
        for i in range(100):
            test_id = uuid.uuid4()
            test_ids.append(test_id)
            await session.execute(statements['insert'], [
                test_id, i % 10, f"test_{i}", i, datetime.utcnow()
            ])
        
        # Define operations using different prepared statements
        async def random_operation():
            op_type = random.choice(['select_id', 'select_partition', 'update', 'insert'])
            
            if op_type == 'select_id':
                test_id = random.choice(test_ids)
                result = await session.execute(statements['select_by_id'], [test_id])
                return 'select_id', bool(result.one())
            
            elif op_type == 'select_partition':
                partition = random.randint(0, 9)
                result = await session.execute(statements['select_by_partition'], [partition])
                return 'select_partition', len(list(result))
            
            elif op_type == 'update':
                test_id = random.choice(test_ids)
                await session.execute(statements['update'], [test_id])
                return 'update', True
            
            else:  # insert
                test_id = uuid.uuid4()
                await session.execute(statements['insert'], [
                    test_id, random.randint(0, 9), "random_data", 
                    random.randint(0, 1000), datetime.utcnow()
                ])
                return 'insert', True
        
        # Execute 500 random operations concurrently
        operations = [random_operation() for _ in range(500)]
        start_time = time.time()
        results = await asyncio.gather(*operations, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Analyze results
        operation_counts = {}
        error_count = 0
        for result in results:
            if isinstance(result, Exception):
                error_count += 1
            else:
                op_type = result[0]
                operation_counts[op_type] = operation_counts.get(op_type, 0) + 1
        
        assert error_count < 25  # Less than 5% error rate
        assert total_time < 10  # Should complete within 10 seconds
        assert len(operation_counts) >= 3  # At least 3 operation types executed
    
    @pytest.mark.asyncio
    async def test_concurrent_counter_operations(self, session: AsyncCassandraSession):
        """Test concurrent counter operations which are particularly challenging."""
        # Create test counters
        counter_ids = [uuid.uuid4() for _ in range(10)]
        
        # Initialize counters
        for counter_id in counter_ids:
            await session.execute(
                "UPDATE counters SET value = value + 0 WHERE id = ?",
                [counter_id]
            )
        
        # Prepare statements
        increment_stmt = await session.prepare(
            "UPDATE counters SET value = value + ? WHERE id = ?"
        )
        decrement_stmt = await session.prepare(
            "UPDATE counters SET value = value - ? WHERE id = ?"
        )
        select_stmt = await session.prepare(
            "SELECT value FROM counters WHERE id = ?"
        )
        
        # Define concurrent operations
        async def increment_counter(counter_id, amount):
            await session.execute(increment_stmt, [amount, counter_id])
            return "increment", amount
        
        async def decrement_counter(counter_id, amount):
            await session.execute(decrement_stmt, [amount, counter_id])
            return "decrement", amount
        
        # Create mixed increment/decrement operations
        operations = []
        expected_totals = {counter_id: 0 for counter_id in counter_ids}
        
        for _ in range(1000):
            counter_id = random.choice(counter_ids)
            amount = random.randint(1, 10)
            
            if random.random() > 0.5:
                operations.append(increment_counter(counter_id, amount))
                expected_totals[counter_id] += amount
            else:
                operations.append(decrement_counter(counter_id, amount))
                expected_totals[counter_id] -= amount
        
        # Execute all operations concurrently
        start_time = time.time()
        results = await asyncio.gather(*operations, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Verify counter values
        await asyncio.sleep(0.5)  # Allow counters to settle
        
        actual_totals = {}
        for counter_id in counter_ids:
            result = await session.execute(select_stmt, [counter_id])
            actual_totals[counter_id] = result.one()[0] if result.one() else 0
        
        # Counter operations might have some eventual consistency issues
        # but totals should match
        for counter_id in counter_ids:
            assert actual_totals[counter_id] == expected_totals[counter_id], \
                f"Counter {counter_id} mismatch: expected {expected_totals[counter_id]}, got {actual_totals[counter_id]}"
        
        assert total_time < 15  # Counter operations are slower
    
    @pytest.mark.asyncio
    async def test_concurrent_streaming_operations(self, session: AsyncCassandraSession):
        """Test concurrent streaming operations."""
        # Insert large dataset
        insert_stmt = await session.prepare(
            "INSERT INTO stress_test (id, partition_key, data, counter, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        
        # Create 10,000 records across 10 partitions
        insert_tasks = []
        for i in range(10000):
            test_id = uuid.uuid4()
            task = session.execute(insert_stmt, [
                test_id, i % 10, f"streaming_test_{i}" * 10,  # Larger data
                i, datetime.utcnow()
            ])
            insert_tasks.append(task)
            
            # Execute in batches to avoid overwhelming
            if len(insert_tasks) >= 100:
                await asyncio.gather(*insert_tasks)
                insert_tasks = []
        
        if insert_tasks:
            await asyncio.gather(*insert_tasks)
        
        # Define streaming operations
        async def stream_partition(partition_key: int):
            from async_cassandra import StreamConfig
            
            config = StreamConfig(fetch_size=100)
            result = await session.execute_stream(
                "SELECT * FROM stress_test WHERE partition_key = ? ALLOW FILTERING",
                [partition_key],
                stream_config=config
            )
            
            count = 0
            data_size = 0
            async for row in result:
                count += 1
                data_size += len(row.data)
            
            return partition_key, count, data_size
        
        # Stream all partitions concurrently
        start_time = time.time()
        streaming_tasks = [stream_partition(i) for i in range(10)]
        results = await asyncio.gather(*streaming_tasks)
        total_time = time.time() - start_time
        
        # Verify results
        total_count = sum(r[1] for r in results)
        total_data = sum(r[2] for r in results)
        
        assert total_count == 10000
        assert total_data > 0
        assert total_time < 20  # Streaming 10k records should be reasonably fast
        
        print(f"Streamed {total_count} records ({total_data} bytes) in {total_time:.2f}s")
    
    @pytest.mark.asyncio
    async def test_connection_pool_stress(self, session: AsyncCassandraSession):
        """Stress test the connection pool with burst traffic."""
        select_stmt = await session.prepare("SELECT now() FROM system.local")
        
        async def burst_queries(burst_size: int):
            """Execute a burst of queries as fast as possible."""
            tasks = []
            for _ in range(burst_size):
                tasks.append(session.execute(select_stmt))
            
            start = time.time()
            await asyncio.gather(*tasks)
            return time.time() - start
        
        # Test increasing burst sizes
        burst_sizes = [10, 50, 100, 200, 500, 1000]
        results = []
        
        for size in burst_sizes:
            duration = await burst_queries(size)
            qps = size / duration
            results.append((size, duration, qps))
            print(f"Burst size {size}: {duration:.2f}s ({qps:.0f} queries/sec)")
            
            # Small delay between bursts
            await asyncio.sleep(0.1)
        
        # Verify connection pool handles bursts efficiently
        # QPS should remain relatively stable or increase with larger bursts
        for i in range(1, len(results)):
            # Later bursts should have similar or better QPS
            assert results[i][2] >= results[0][2] * 0.8  # Allow 20% degradation
    
    @pytest.mark.asyncio
    async def test_concurrent_consistency_levels(self, session: AsyncCassandraSession):
        """Test concurrent operations with different consistency levels."""
        insert_stmt = await session.prepare(
            "INSERT INTO stress_test (id, partition_key, data, counter, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        
        select_stmt = await session.prepare(
            "SELECT * FROM stress_test WHERE id = ?"
        )
        
        async def operation_with_consistency(consistency_level, test_id):
            """Execute operations with specific consistency level."""
            # Insert with specified consistency
            await session.execute(
                insert_stmt,
                [test_id, 1, f"consistency_test_{consistency_level}", 1, datetime.utcnow()],
                consistency_level=consistency_level
            )
            
            # Read back with same consistency
            result = await session.execute(
                select_stmt,
                [test_id],
                consistency_level=consistency_level
            )
            
            return consistency_level, result.one() is not None
        
        # Test different consistency levels concurrently
        consistency_levels = [
            ConsistencyLevel.ONE,
            ConsistencyLevel.QUORUM,
            ConsistencyLevel.ALL,
            ConsistencyLevel.LOCAL_ONE,
            ConsistencyLevel.LOCAL_QUORUM,
        ]
        
        operations = []
        for i in range(100):
            test_id = uuid.uuid4()
            cl = consistency_levels[i % len(consistency_levels)]
            operations.append(operation_with_consistency(cl, test_id))
        
        start_time = time.time()
        results = await asyncio.gather(*operations, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Count successes per consistency level
        success_by_cl = {}
        error_by_cl = {}
        
        for result in results:
            if isinstance(result, Exception):
                cl_name = str(result)  # Extract CL from error if possible
                error_by_cl[cl_name] = error_by_cl.get(cl_name, 0) + 1
            else:
                cl, success = result
                if cl not in success_by_cl:
                    success_by_cl[cl] = {'success': 0, 'total': 0}
                success_by_cl[cl]['total'] += 1
                if success:
                    success_by_cl[cl]['success'] += 1
        
        # All consistency levels should work with single-node cluster
        assert len(success_by_cl) >= 3  # At least 3 different CLs succeeded
        assert total_time < 10  # Should complete reasonably fast