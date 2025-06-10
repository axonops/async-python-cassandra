"""
Pytest configuration and shared fixtures.
"""

import asyncio

import pytest
from testcontainers.compose import DockerCompose


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def cassandra_container():
    """Start Cassandra container for integration tests."""
    compose = DockerCompose(
        filepath="tests/integration", compose_file_name="docker-compose.yml", pull=True
    )

    with compose:
        # Wait for Cassandra to be ready
        compose.wait_for("tcp://localhost:9042")
        yield compose


@pytest.fixture
async def cassandra_cluster():
    """Create a Cassandra cluster for tests."""
    from async_cassandra import AsyncCluster

    cluster = AsyncCluster(contact_points=["localhost"], port=9042)

    yield cluster

    await cluster.shutdown()


@pytest.fixture
async def cassandra_session(cassandra_cluster):
    """Create a Cassandra session for tests."""
    # Create test keyspace
    session = await cassandra_cluster.connect()

    await session.execute(
        """
        CREATE KEYSPACE IF NOT EXISTS test_keyspace
        WITH REPLICATION = {
            'class': 'SimpleStrategy',
            'replication_factor': 1
        }
    """
    )

    await session.set_keyspace("test_keyspace")

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
    await session.execute("DROP TABLE IF EXISTS users")
    await session.close()
