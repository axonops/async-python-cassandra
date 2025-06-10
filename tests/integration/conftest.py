"""
Pytest configuration for integration tests.
"""

import pytest
import pytest_asyncio
from async_cassandra import AsyncCluster


@pytest_asyncio.fixture
async def cassandra_cluster():
    """Create an async Cassandra cluster for testing."""
    cluster = AsyncCluster(contact_points=["localhost"])
    yield cluster
    await cluster.shutdown()


@pytest_asyncio.fixture
async def cassandra_session(cassandra_cluster):
    """Create an async Cassandra session for testing."""
    session = await cassandra_cluster.connect()
    
    # Create test keyspace
    await session.execute(
        """
        CREATE KEYSPACE IF NOT EXISTS test_async_cassandra
        WITH REPLICATION = {
            'class': 'SimpleStrategy',
            'replication_factor': 1
        }
        """
    )
    
    await session.set_keyspace("test_async_cassandra")
    
    # Create test table
    await session.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            name TEXT,
            email TEXT,
            age INT
        )
        """
    )
    
    yield session
    
    # Cleanup
    await session.close()