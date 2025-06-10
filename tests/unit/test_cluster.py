"""
Unit tests for async cluster management.
"""

from ssl import SSLContext, PROTOCOL_TLS_CLIENT
from unittest.mock import Mock, patch

import pytest
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster
from cassandra.policies import (
    ExponentialReconnectionPolicy,
    TokenAwarePolicy,
)

from async_cassandra.cluster import AsyncCluster
from async_cassandra.exceptions import ConnectionError
from async_cassandra.retry_policy import AsyncRetryPolicy
from async_cassandra.session import AsyncCassandraSession


class TestAsyncCluster:
    """Test cases for AsyncCluster."""

    @pytest.fixture
    def mock_cluster(self):
        """Create a mock Cassandra cluster."""
        with patch("async_cassandra.cluster.Cluster") as mock_cluster_class:
            mock_instance = Mock(spec=Cluster)
            mock_instance.shutdown = Mock()
            mock_instance.metadata = {"test": "metadata"}
            mock_cluster_class.return_value = mock_instance
            yield mock_instance

    def test_init_with_defaults(self, mock_cluster):
        """Test initialization with default values."""
        async_cluster = AsyncCluster()

        # Verify defaults were set
        assert not async_cluster.is_closed

        # Verify cluster was created with defaults
        from async_cassandra.cluster import Cluster as ClusterImport

        ClusterImport.assert_called_once()
        call_args = ClusterImport.call_args

        assert call_args.kwargs["contact_points"] == ["127.0.0.1"]
        assert call_args.kwargs["port"] == 9042
        assert isinstance(call_args.kwargs["load_balancing_policy"], TokenAwarePolicy)
        assert isinstance(call_args.kwargs["reconnection_policy"], ExponentialReconnectionPolicy)
        assert isinstance(call_args.kwargs["default_retry_policy"], AsyncRetryPolicy)

    def test_init_with_custom_values(self, mock_cluster):
        """Test initialization with custom values."""
        contact_points = ["192.168.1.1", "192.168.1.2"]
        port = 9043
        auth_provider = PlainTextAuthProvider("user", "pass")

        AsyncCluster(
            contact_points=contact_points,
            port=port,
            auth_provider=auth_provider,
            executor_threads=4,
            protocol_version=4,
        )

        from async_cassandra.cluster import Cluster as ClusterImport

        call_args = ClusterImport.call_args

        assert call_args.kwargs["contact_points"] == contact_points
        assert call_args.kwargs["port"] == port
        assert call_args.kwargs["auth_provider"] == auth_provider
        assert call_args.kwargs["executor_threads"] == 4
        assert call_args.kwargs["protocol_version"] == 4

    def test_create_with_auth(self, mock_cluster):
        """Test creating cluster with authentication."""
        contact_points = ["localhost"]
        username = "testuser"
        password = "testpass"

        AsyncCluster.create_with_auth(
            contact_points=contact_points, username=username, password=password
        )

        from async_cassandra.cluster import Cluster as ClusterImport

        call_args = ClusterImport.call_args

        assert call_args.kwargs["contact_points"] == contact_points
        auth_provider = call_args.kwargs["auth_provider"]
        assert isinstance(auth_provider, PlainTextAuthProvider)

    @pytest.mark.asyncio
    async def test_connect_without_keyspace(self, mock_cluster):
        """Test connecting without keyspace."""
        async_cluster = AsyncCluster()

        with patch("async_cassandra.cluster.AsyncCassandraSession.create") as mock_create:
            mock_session = Mock(spec=AsyncCassandraSession)
            mock_create.return_value = mock_session

            session = await async_cluster.connect()

            assert session == mock_session
            mock_create.assert_called_once_with(mock_cluster, None)

    @pytest.mark.asyncio
    async def test_connect_with_keyspace(self, mock_cluster):
        """Test connecting with keyspace."""
        async_cluster = AsyncCluster()
        keyspace = "test_keyspace"

        with patch("async_cassandra.cluster.AsyncCassandraSession.create") as mock_create:
            mock_session = Mock(spec=AsyncCassandraSession)
            mock_create.return_value = mock_session

            session = await async_cluster.connect(keyspace)

            assert session == mock_session
            mock_create.assert_called_once_with(mock_cluster, keyspace)

    @pytest.mark.asyncio
    async def test_connect_error(self, mock_cluster):
        """Test handling connection error."""
        async_cluster = AsyncCluster()

        with patch("async_cassandra.cluster.AsyncCassandraSession.create") as mock_create:
            mock_create.side_effect = Exception("Connection failed")

            with pytest.raises(ConnectionError) as exc_info:
                await async_cluster.connect()

            assert "Failed to connect to cluster" in str(exc_info.value)
            assert exc_info.value.cause is not None

    @pytest.mark.asyncio
    async def test_connect_on_closed_cluster(self, mock_cluster):
        """Test connecting on closed cluster."""
        async_cluster = AsyncCluster()
        await async_cluster.shutdown()

        with pytest.raises(ConnectionError) as exc_info:
            await async_cluster.connect()

        assert "Cluster is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_cluster):
        """Test shutting down the cluster."""
        async_cluster = AsyncCluster()

        await async_cluster.shutdown()

        assert async_cluster.is_closed
        mock_cluster.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self, mock_cluster):
        """Test that shutdown is idempotent."""
        async_cluster = AsyncCluster()

        await async_cluster.shutdown()
        await async_cluster.shutdown()

        # Should only be called once
        mock_cluster.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_cluster):
        """Test using cluster as async context manager."""
        async with AsyncCluster() as cluster:
            assert isinstance(cluster, AsyncCluster)
            assert not cluster.is_closed

        # Cluster should be shut down after exiting context
        mock_cluster.shutdown.assert_called_once()

    def test_is_closed_property(self, mock_cluster):
        """Test is_closed property."""
        async_cluster = AsyncCluster()

        assert not async_cluster.is_closed
        async_cluster._closed = True
        assert async_cluster.is_closed

    def test_metadata_property(self, mock_cluster):
        """Test metadata property."""
        async_cluster = AsyncCluster()

        assert async_cluster.metadata == {"test": "metadata"}

    def test_register_user_type(self, mock_cluster):
        """Test registering user-defined type."""
        async_cluster = AsyncCluster()

        keyspace = "test_keyspace"
        user_type = "address"
        klass = type("Address", (), {})

        async_cluster.register_user_type(keyspace, user_type, klass)

        mock_cluster.register_user_type.assert_called_once_with(keyspace, user_type, klass)

    def test_ssl_context(self, mock_cluster):
        """Test initialization with SSL context."""
        ssl_context = SSLContext(PROTOCOL_TLS_CLIENT)

        AsyncCluster(ssl_context=ssl_context)

        from async_cassandra.cluster import Cluster as ClusterImport

        call_args = ClusterImport.call_args

        assert call_args.kwargs["ssl_context"] == ssl_context
