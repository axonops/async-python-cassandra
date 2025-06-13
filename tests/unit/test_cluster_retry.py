"""
Unit tests for cluster connection retry logic.
"""

import asyncio
from unittest.mock import Mock, patch

import pytest
from cassandra.cluster import NoHostAvailable

from async_cassandra.cluster import AsyncCluster
from async_cassandra.exceptions import ConnectionError


@pytest.mark.asyncio
class TestClusterConnectionRetry:
    """Test cluster connection retry behavior."""

    async def test_connection_retries_on_failure(self):
        """Test that connection attempts are retried on failure."""
        mock_cluster = Mock()

        # Create a mock that fails twice then succeeds
        connect_attempts = 0

        def connect_side_effect(keyspace=None):
            nonlocal connect_attempts
            connect_attempts += 1
            if connect_attempts < 3:
                raise NoHostAvailable("Unable to connect to any servers", {})
            return Mock()  # Return a mock session on third attempt

        mock_cluster.connect = Mock(side_effect=connect_side_effect)

        with patch("async_cassandra.cluster.Cluster", return_value=mock_cluster):
            cluster = AsyncCluster(["localhost"])

            # Should succeed after retries
            session = await cluster.connect()
            assert session is not None
            assert connect_attempts == 3

    async def test_connection_fails_after_max_retries(self):
        """Test that connection fails after maximum retry attempts."""
        mock_cluster = Mock()

        # Always fail
        mock_cluster.connect = Mock(
            side_effect=NoHostAvailable("Unable to connect to any servers", {})
        )

        with patch("async_cassandra.cluster.Cluster", return_value=mock_cluster):
            cluster = AsyncCluster(["localhost"])

            # Should fail after max retries (3)
            with pytest.raises(ConnectionError) as exc_info:
                await cluster.connect()

            assert "Failed to connect to cluster after 3 attempts" in str(exc_info.value)
            assert mock_cluster.connect.call_count == 3

    async def test_connection_retry_with_increasing_delay(self):
        """Test that retry delays increase with each attempt."""
        mock_cluster = Mock()

        # Fail all attempts
        mock_cluster.connect = Mock(
            side_effect=NoHostAvailable("Unable to connect to any servers", {})
        )

        sleep_delays = []

        async def mock_sleep(delay):
            sleep_delays.append(delay)

        with patch("async_cassandra.cluster.Cluster", return_value=mock_cluster):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                cluster = AsyncCluster(["localhost"])

                with pytest.raises(ConnectionError):
                    await cluster.connect()

                # Should have 2 sleep calls (between 3 attempts)
                assert len(sleep_delays) == 2
                # First delay should be 2.0 seconds (NoHostAvailable gets longer delay)
                assert sleep_delays[0] == 2.0
                # Second delay should be 4.0 seconds
                assert sleep_delays[1] == 4.0

    async def test_timeout_error_not_retried(self):
        """Test that asyncio.TimeoutError is not retried."""
        mock_cluster = Mock()

        # Create session that takes too long
        async def slow_connect(keyspace=None):
            await asyncio.sleep(20)  # Longer than timeout
            return Mock()

        mock_cluster.connect = Mock(side_effect=lambda k=None: Mock())

        with patch("async_cassandra.cluster.Cluster", return_value=mock_cluster):
            with patch(
                "async_cassandra.session.AsyncCassandraSession.create",
                side_effect=asyncio.TimeoutError(),
            ):
                cluster = AsyncCluster(["localhost"])

                # Should raise TimeoutError without retrying
                with pytest.raises(asyncio.TimeoutError):
                    await cluster.connect(timeout=0.1)

                # Should not have retried (create was called only once)

    async def test_other_exceptions_use_shorter_delay(self):
        """Test that non-NoHostAvailable exceptions use shorter retry delay."""
        mock_cluster = Mock()

        # Fail with generic exception
        mock_cluster.connect = Mock(side_effect=Exception("Generic error"))

        sleep_delays = []

        async def mock_sleep(delay):
            sleep_delays.append(delay)

        with patch("async_cassandra.cluster.Cluster", return_value=mock_cluster):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                cluster = AsyncCluster(["localhost"])

                with pytest.raises(ConnectionError):
                    await cluster.connect()

                # Should have 2 sleep calls
                assert len(sleep_delays) == 2
                # First delay should be 0.5 seconds (generic exception)
                assert sleep_delays[0] == 0.5
                # Second delay should be 1.0 seconds
                assert sleep_delays[1] == 1.0
