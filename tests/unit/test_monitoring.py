"""
Unit tests for monitoring module.
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import pytest

from async_cassandra.monitoring import (
    HostStatus, HostMetrics, ClusterMetrics,
    ConnectionMonitor, RateLimitedSession,
    create_monitored_session
)
from cassandra.cluster import Host


class TestHostStatus:
    """Test HostStatus dataclass."""
    
    def test_host_status_creation(self):
        """Test creating HostStatus instance."""
        status = HostStatus(
            address="192.168.1.1",
            port=9042,
            is_up=True,
            datacenter="dc1",
            rack="rack1",
            release_version="4.0.0",
            tokens=["token1", "token2"],
            host_id="host-123"
        )
        
        assert status.address == "192.168.1.1"
        assert status.port == 9042
        assert status.is_up is True
        assert status.datacenter == "dc1"
        assert status.rack == "rack1"
        assert status.release_version == "4.0.0"
        assert len(status.tokens) == 2
        assert status.host_id == "host-123"


class TestHostMetrics:
    """Test HostMetrics dataclass."""
    
    def test_host_metrics_creation(self):
        """Test creating HostMetrics instance."""
        metrics = HostMetrics(
            address="192.168.1.1",
            total_connections=1,
            available_connections=1,
            in_flight_queries=5,
            response_time_ms=15.5
        )
        
        assert metrics.address == "192.168.1.1"
        assert metrics.total_connections == 1
        assert metrics.available_connections == 1
        assert metrics.in_flight_queries == 5
        assert metrics.response_time_ms == 15.5


class TestClusterMetrics:
    """Test ClusterMetrics dataclass."""
    
    def test_cluster_metrics_creation(self):
        """Test creating ClusterMetrics instance."""
        host_metrics = [
            HostMetrics("host1", 1, 1, 0, 10.0),
            HostMetrics("host2", 1, 0, 5, 20.0)
        ]
        
        metrics = ClusterMetrics(
            cluster_name="TestCluster",
            total_hosts=2,
            up_hosts=2,
            down_hosts=0,
            total_connections=2,
            available_connections=1,
            total_in_flight=5,
            avg_response_time_ms=15.0,
            host_metrics=host_metrics
        )
        
        assert metrics.cluster_name == "TestCluster"
        assert metrics.total_hosts == 2
        assert metrics.up_hosts == 2
        assert metrics.down_hosts == 0
        assert metrics.total_connections == 2
        assert metrics.available_connections == 1
        assert metrics.total_in_flight == 5
        assert metrics.avg_response_time_ms == 15.0
        assert len(metrics.host_metrics) == 2


class TestConnectionMonitor:
    """Test ConnectionMonitor."""
    
    def create_mock_host(self, address="127.0.0.1", is_up=True):
        """Create a mock Host object."""
        host = Mock(spec=Host)
        host.address = address
        host.is_up = is_up
        host.datacenter = "dc1"
        host.rack = "rack1"
        host.release_version = "4.0.0"
        host.host_id = f"host-{address}"
        return host
    
    def create_mock_session(self, hosts=None):
        """Create a mock session with cluster metadata."""
        session = AsyncMock()
        session.cluster = Mock()
        session.cluster.metadata = Mock()
        session.cluster.metadata.cluster_name = "TestCluster"
        session.cluster.metadata.all_hosts = Mock(return_value=hosts or [])
        session.execute = AsyncMock()
        return session
    
    @pytest.mark.asyncio
    async def test_monitor_creation(self):
        """Test creating ConnectionMonitor."""
        session = self.create_mock_session()
        monitor = ConnectionMonitor(session, check_interval=30)
        
        assert monitor.session == session
        assert monitor.check_interval == 30
        assert monitor._monitoring_task is None
        assert not monitor._running
    
    @pytest.mark.asyncio
    async def test_get_host_status(self):
        """Test getting host status."""
        hosts = [
            self.create_mock_host("127.0.0.1", True),
            self.create_mock_host("127.0.0.2", False)
        ]
        session = self.create_mock_session(hosts)
        monitor = ConnectionMonitor(session)
        
        statuses = await monitor.get_host_status()
        
        assert len(statuses) == 2
        assert statuses[0].address == "127.0.0.1"
        assert statuses[0].is_up is True
        assert statuses[1].address == "127.0.0.2"
        assert statuses[1].is_up is False
    
    @pytest.mark.asyncio
    async def test_check_host_health_success(self):
        """Test checking health of a healthy host."""
        host = self.create_mock_host("127.0.0.1", True)
        session = self.create_mock_session([host])
        session.execute.return_value = Mock()  # Successful response
        
        monitor = ConnectionMonitor(session)
        
        is_healthy, response_time = await monitor._check_host_health(host)
        
        assert is_healthy is True
        assert response_time > 0
        assert response_time < 1.0  # Should be very fast for mock
    
    @pytest.mark.asyncio
    async def test_check_host_health_failure(self):
        """Test checking health of an unhealthy host."""
        host = self.create_mock_host("127.0.0.1", False)
        session = self.create_mock_session([host])
        session.execute.side_effect = Exception("Connection failed")
        
        monitor = ConnectionMonitor(session)
        
        is_healthy, response_time = await monitor._check_host_health(host)
        
        assert is_healthy is False
        assert response_time is None
    
    @pytest.mark.asyncio
    async def test_get_cluster_metrics(self):
        """Test getting cluster metrics."""
        hosts = [
            self.create_mock_host("127.0.0.1", True),
            self.create_mock_host("127.0.0.2", True),
            self.create_mock_host("127.0.0.3", False)
        ]
        session = self.create_mock_session(hosts)
        
        # Mock successful health checks for up hosts
        async def mock_execute(query, host=None):
            if "127.0.0.3" in str(host):
                raise Exception("Host down")
            return Mock()
        
        session.execute = mock_execute
        
        monitor = ConnectionMonitor(session)
        metrics = await monitor.get_cluster_metrics()
        
        assert metrics.cluster_name == "TestCluster"
        assert metrics.total_hosts == 3
        assert metrics.up_hosts == 2
        assert metrics.down_hosts == 1
        assert len(metrics.host_metrics) == 3
    
    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        """Test starting monitoring task."""
        session = self.create_mock_session([])
        monitor = ConnectionMonitor(session, check_interval=0.1)
        
        # Start monitoring
        monitor.start_monitoring()
        
        assert monitor._running is True
        assert monitor._monitoring_task is not None
        
        # Let it run briefly
        await asyncio.sleep(0.2)
        
        # Stop monitoring
        await monitor.stop_monitoring()
        
        assert monitor._running is False
        assert monitor._monitoring_task is None
    
    @pytest.mark.asyncio
    async def test_monitoring_with_callbacks(self):
        """Test monitoring with health check callbacks."""
        hosts = [self.create_mock_host("127.0.0.1", True)]
        session = self.create_mock_session(hosts)
        monitor = ConnectionMonitor(session, check_interval=0.1)
        
        # Track callback invocations
        callback_results = []
        
        async def health_callback(cluster_metrics):
            callback_results.append(cluster_metrics)
        
        monitor.add_health_check_callback(health_callback)
        
        # Start monitoring
        monitor.start_monitoring()
        await asyncio.sleep(0.3)  # Let it run a few checks
        await monitor.stop_monitoring()
        
        # Callbacks should have been invoked
        assert len(callback_results) >= 2
        assert all(isinstance(m, ClusterMetrics) for m in callback_results)
    
    @pytest.mark.asyncio
    async def test_get_unhealthy_hosts(self):
        """Test identifying unhealthy hosts."""
        hosts = [
            self.create_mock_host("127.0.0.1", True),
            self.create_mock_host("127.0.0.2", False),
            self.create_mock_host("127.0.0.3", True)
        ]
        session = self.create_mock_session(hosts)
        
        # Make 127.0.0.3 fail health check
        async def mock_execute(query, host=None):
            if "127.0.0.3" in str(host):
                raise Exception("Health check failed")
            return Mock()
        
        session.execute = mock_execute
        
        monitor = ConnectionMonitor(session)
        unhealthy = await monitor.get_unhealthy_hosts()
        
        assert len(unhealthy) == 2  # 127.0.0.2 (is_up=False) and 127.0.0.3 (health check failed)
        assert any(h.address == "127.0.0.2" for h in unhealthy)
        assert any(h.address == "127.0.0.3" for h in unhealthy)


class TestRateLimitedSession:
    """Test RateLimitedSession."""
    
    @pytest.mark.asyncio
    async def test_rate_limited_session_creation(self):
        """Test creating RateLimitedSession."""
        mock_session = AsyncMock()
        rate_limited = RateLimitedSession(mock_session, max_concurrent=10)
        
        assert rate_limited._session == mock_session
        assert rate_limited._semaphore._value == 10
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting works."""
        # Create session with very low limit
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        
        # Add delay to simulate slow queries
        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(0.1)
            return Mock()
        
        mock_session.execute = slow_execute
        
        rate_limited = RateLimitedSession(mock_session, max_concurrent=2)
        
        # Start 5 concurrent queries
        start_time = time.time()
        tasks = [
            rate_limited.execute(f"SELECT {i}")
            for i in range(5)
        ]
        await asyncio.gather(*tasks)
        duration = time.time() - start_time
        
        # With limit of 2 and 0.1s per query, should take at least 0.3s
        # (2 batches of 2, then 1 more)
        assert duration >= 0.25  # Allow some margin
    
    @pytest.mark.asyncio
    async def test_method_forwarding(self):
        """Test that other methods are forwarded correctly."""
        mock_session = AsyncMock()
        mock_session.prepare = AsyncMock(return_value="prepared_stmt")
        mock_session.execute_stream = AsyncMock(return_value="stream_result")
        mock_session.set_keyspace = AsyncMock()
        
        rate_limited = RateLimitedSession(mock_session, max_concurrent=10)
        
        # Test prepare
        result = await rate_limited.prepare("SELECT * FROM test")
        assert result == "prepared_stmt"
        mock_session.prepare.assert_called_once_with("SELECT * FROM test")
        
        # Test execute_stream
        result = await rate_limited.execute_stream("SELECT * FROM large")
        assert result == "stream_result"
        
        # Test set_keyspace
        await rate_limited.set_keyspace("test_ks")
        mock_session.set_keyspace.assert_called_once_with("test_ks")
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test that errors are propagated correctly."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Query failed"))
        
        rate_limited = RateLimitedSession(mock_session, max_concurrent=10)
        
        with pytest.raises(Exception) as exc_info:
            await rate_limited.execute("SELECT * FROM fail")
        
        assert str(exc_info.value) == "Query failed"
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using rate limited session as context manager."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        rate_limited = RateLimitedSession(mock_session, max_concurrent=10)
        
        async with rate_limited as session:
            assert session == rate_limited
        
        # Original session's context manager should be called
        mock_session.__aenter__.assert_called_once()
        mock_session.__aexit__.assert_called_once()


class TestCreateMonitoredSession:
    """Test create_monitored_session function."""
    
    @pytest.mark.asyncio
    async def test_create_monitored_session_basic(self):
        """Test creating basic monitored session."""
        mock_cluster = AsyncMock()
        mock_session = AsyncMock()
        mock_cluster.connect = AsyncMock(return_value=mock_session)
        
        result = await create_monitored_session(
            mock_cluster,
            enable_monitoring=True,
            enable_rate_limiting=False
        )
        
        assert isinstance(result, dict)
        assert result['session'] == mock_session
        assert isinstance(result['monitor'], ConnectionMonitor)
        assert result['monitor']._running is True
    
    @pytest.mark.asyncio
    async def test_create_monitored_session_with_rate_limiting(self):
        """Test creating monitored session with rate limiting."""
        mock_cluster = AsyncMock()
        mock_session = AsyncMock()
        mock_cluster.connect = AsyncMock(return_value=mock_session)
        
        result = await create_monitored_session(
            mock_cluster,
            enable_monitoring=False,
            enable_rate_limiting=True,
            max_concurrent_requests=50
        )
        
        assert isinstance(result['session'], RateLimitedSession)
        assert result['session']._semaphore._value == 50
        assert result['monitor'] is None
    
    @pytest.mark.asyncio
    async def test_create_monitored_session_with_both(self):
        """Test creating monitored session with both monitoring and rate limiting."""
        mock_cluster = AsyncMock()
        mock_session = AsyncMock()
        mock_cluster.connect = AsyncMock(return_value=mock_session)
        
        result = await create_monitored_session(
            mock_cluster,
            enable_monitoring=True,
            enable_rate_limiting=True,
            max_concurrent_requests=100,
            health_check_interval=60
        )
        
        assert isinstance(result['session'], RateLimitedSession)
        assert isinstance(result['monitor'], ConnectionMonitor)
        assert result['monitor'].check_interval == 60
        assert result['monitor']._running is True
    
    @pytest.mark.asyncio
    async def test_create_monitored_session_with_keyspace(self):
        """Test creating monitored session with keyspace."""
        mock_cluster = AsyncMock()
        mock_session = AsyncMock()
        mock_cluster.connect = AsyncMock(return_value=mock_session)
        
        result = await create_monitored_session(
            mock_cluster,
            keyspace="test_ks"
        )
        
        mock_cluster.connect.assert_called_once_with("test_ks")
        assert result['session'] == mock_session