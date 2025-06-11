"""
Pytest configuration for integration tests.
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

from async_cassandra import AsyncCluster

# Add integration test directory to path for container_manager import
sys.path.insert(0, str(Path(__file__).parent))
from container_manager import ContainerManager


def pytest_configure(config):
    """Configure pytest for integration tests."""
    # Skip if explicitly disabled
    if os.environ.get("SKIP_INTEGRATION_TESTS", "").lower() in ("1", "true", "yes"):
        return

    # Initialize container manager
    config.container_manager = ContainerManager()

    # Start containers if not already running
    if not config.container_manager.is_running():
        try:
            config.container_manager.start_containers()
            config.containers_started = True
        except Exception as e:
            pytest.exit(f"Failed to start test containers: {e}", 1)
    else:
        config.containers_started = False
        print("Using existing Cassandra container")


def pytest_unconfigure(config):
    """Clean up after tests."""
    # Only stop containers if we started them
    if (
        hasattr(config, "container_manager")
        and hasattr(config, "containers_started")
        and config.containers_started
        and os.environ.get("KEEP_CONTAINERS", "").lower() not in ("1", "true", "yes")
    ):
        try:
            config.container_manager.stop_containers()
        except Exception as e:
            print(f"Warning: Failed to stop containers: {e}")


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
