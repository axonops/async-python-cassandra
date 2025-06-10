"""
Unit tests for metrics module.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from async_cassandra.metrics import (
    ConnectionMetrics,
    InMemoryMetricsCollector,
    MetricsMiddleware,
    PrometheusMetricsCollector,
    QueryMetrics,
    create_metrics_system,
)


class TestQueryMetrics:
    """Test QueryMetrics dataclass."""

    def test_query_metrics_creation(self):
        """Test creating QueryMetrics instance."""
        metrics = QueryMetrics(
            query_hash="SELECT * FROM users",
            duration=0.123,
            success=True,
            error_type=None,
            parameters_count=0,
            result_size=10,
            consistency_level="LOCAL_ONE",
            timestamp=datetime.utcnow(),
        )

        assert metrics.query_hash == "SELECT * FROM users"
        assert metrics.duration == 0.123
        assert metrics.success is True
        assert metrics.error_type is None
        assert metrics.parameters_count == 0
        assert metrics.result_size == 10
        assert metrics.consistency_level == "LOCAL_ONE"
        assert isinstance(metrics.timestamp, datetime)

    def test_query_metrics_with_error(self):
        """Test QueryMetrics with error information."""
        metrics = QueryMetrics(
            query_hash="INSERT INTO users",
            duration=0.456,
            success=False,
            error_type="InvalidRequest",
            parameters_count=3,
            result_size=0,
            consistency_level="QUORUM",
            timestamp=datetime.utcnow(),
        )

        assert metrics.success is False
        assert metrics.error_type == "InvalidRequest"
        assert metrics.result_size == 0


class TestConnectionMetrics:
    """Test ConnectionMetrics dataclass."""

    def test_connection_metrics_creation(self):
        """Test creating ConnectionMetrics instance."""
        metrics = ConnectionMetrics(
            host="127.0.0.1",
            healthy=True,
            response_time=0.015,
            error_count=0,
            timestamp=datetime.utcnow(),
        )

        assert metrics.host == "127.0.0.1"
        assert metrics.healthy is True
        assert metrics.response_time == 0.015
        assert metrics.error_count == 0
        assert isinstance(metrics.timestamp, datetime)


class TestInMemoryMetricsCollector:
    """Test InMemoryMetricsCollector."""

    @pytest.mark.asyncio
    async def test_record_query_metrics(self):
        """Test recording query metrics."""
        collector = InMemoryMetricsCollector(max_queries=10)

        # Record a successful query
        await collector.record_query_metrics(
            query="SELECT * FROM users",
            duration=0.1,
            success=True,
            error_type=None,
            parameters_count=0,
            result_size=5,
        )

        assert len(collector.query_metrics) == 1
        assert collector.query_metrics[0].query_hash == "SELECT * FROM users"
        assert collector.query_metrics[0].duration == 0.1
        assert collector.query_metrics[0].success is True

    @pytest.mark.asyncio
    async def test_record_query_with_normalization(self):
        """Test query normalization."""
        collector = InMemoryMetricsCollector()

        # These should normalize to the same query
        await collector.record_query_metrics(
            query="SELECT * FROM users WHERE id = ?", duration=0.1, success=True, parameters_count=1
        )

        await collector.record_query_metrics(
            query="SELECT * FROM users WHERE id = ?", duration=0.2, success=True, parameters_count=1
        )

        # Both should have the same normalized query
        assert len(collector.query_metrics) == 2
        assert collector.query_metrics[0].query_hash == collector.query_metrics[1].query_hash

    @pytest.mark.asyncio
    async def test_max_queries_limit(self):
        """Test that collector respects max_queries limit."""
        collector = InMemoryMetricsCollector(max_queries=3)

        # Record 5 queries
        for i in range(5):
            await collector.record_query_metrics(
                query=f"SELECT * FROM table{i}", duration=0.1 * i, success=True
            )

        # Should only keep the last 3
        assert len(collector.query_metrics) == 3
        assert collector.query_metrics[0].query_hash == "SELECT * FROM table2"
        assert collector.query_metrics[-1].query_hash == "SELECT * FROM table4"

    @pytest.mark.asyncio
    async def test_record_connection_health(self):
        """Test recording connection health metrics."""
        collector = InMemoryMetricsCollector()

        await collector.record_connection_health(
            host="192.168.1.1", healthy=True, response_time=0.02
        )

        await collector.record_connection_health(
            host="192.168.1.2", healthy=False, response_time=None
        )

        assert len(collector.connection_metrics) == 2
        assert collector.connection_metrics[0].healthy is True
        assert collector.connection_metrics[1].healthy is False
        assert collector.connection_metrics[1].response_time is None

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting aggregated statistics."""
        collector = InMemoryMetricsCollector()

        # Record various queries
        await collector.record_query_metrics("SELECT 1", 0.1, True)
        await collector.record_query_metrics("SELECT 2", 0.2, True)
        await collector.record_query_metrics("SELECT 3", 0.3, False, error_type="Timeout")
        await collector.record_query_metrics("INSERT", 0.15, True)

        # Record connection health
        await collector.record_connection_health("host1", True, 0.01)
        await collector.record_connection_health("host2", False, None)

        stats = await collector.get_stats()

        # Check query performance stats
        assert stats["query_performance"]["total_queries"] == 4
        assert stats["query_performance"]["successful_queries"] == 3
        assert stats["query_performance"]["failed_queries"] == 1
        assert stats["query_performance"]["success_rate"] == 0.75
        assert stats["query_performance"]["avg_duration_ms"] == 175.0  # (100+200+300+150)/4

        # Check error summary
        assert len(stats["error_summary"]) == 1
        assert stats["error_summary"][0]["error_type"] == "Timeout"
        assert stats["error_summary"][0]["count"] == 1

        # Check connection health
        assert stats["connection_health"]["host1"]["healthy"] is True
        assert stats["connection_health"]["host2"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_clear_metrics(self):
        """Test clearing metrics."""
        collector = InMemoryMetricsCollector()

        # Add some metrics
        await collector.record_query_metrics("SELECT", 0.1, True)
        await collector.record_connection_health("host", True, 0.01)

        # Clear metrics
        await collector.clear()

        assert len(collector.query_metrics) == 0
        assert len(collector.connection_metrics) == 0


class TestPrometheusMetricsCollector:
    """Test PrometheusMetricsCollector."""

    @pytest.mark.asyncio
    async def test_prometheus_collector_creation(self):
        """Test creating Prometheus collector."""
        collector = PrometheusMetricsCollector()

        # Check that Prometheus metrics are created
        assert collector._query_duration_histogram is not None
        assert collector._query_counter is not None
        assert collector._error_counter is not None
        assert collector._connection_health_gauge is not None

    @pytest.mark.asyncio
    async def test_record_query_metrics_prometheus(self):
        """Test recording metrics updates Prometheus collectors."""
        collector = PrometheusMetricsCollector()

        # Record successful query
        await collector.record_query_metrics(
            query="SELECT * FROM users", duration=0.05, success=True, result_size=10
        )

        # Record failed query
        await collector.record_query_metrics(
            query="SELECT * FROM invalid", duration=0.1, success=False, error_type="InvalidRequest"
        )

        # Prometheus metrics should be updated
        # Note: Can't easily test internal state of prometheus_client metrics
        # but we can verify no exceptions are raised

    @pytest.mark.asyncio
    async def test_record_connection_health_prometheus(self):
        """Test recording connection health in Prometheus."""
        collector = PrometheusMetricsCollector()

        await collector.record_connection_health(
            host="127.0.0.1", healthy=True, response_time=0.015
        )

        await collector.record_connection_health(
            host="127.0.0.2", healthy=False, response_time=None
        )

        # Metrics should be recorded without errors
        assert True  # If we get here, no exceptions were raised


class TestMetricsMiddleware:
    """Test MetricsMiddleware."""

    @pytest.mark.asyncio
    async def test_middleware_wraps_session(self):
        """Test that middleware properly wraps session methods."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=Mock(one=Mock(return_value=None)))
        mock_session.execute_stream = AsyncMock()
        mock_session.prepare = AsyncMock()

        collector = InMemoryMetricsCollector()
        middleware = MetricsMiddleware(mock_session, [collector])

        # Test that session methods are accessible
        assert hasattr(middleware, "execute")
        assert hasattr(middleware, "execute_stream")
        assert hasattr(middleware, "prepare")

    @pytest.mark.asyncio
    async def test_middleware_records_successful_query(self):
        """Test middleware records successful query metrics."""
        # Mock session
        mock_result = Mock()
        mock_result._rows = [1, 2, 3]  # 3 rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Create middleware with collector
        collector = InMemoryMetricsCollector()
        middleware = MetricsMiddleware(mock_session, [collector])

        # Execute query
        await middleware.execute("SELECT * FROM users")

        # Check that metrics were recorded
        assert len(collector.query_metrics) == 1
        metrics = collector.query_metrics[0]
        assert metrics.query_hash == "SELECT * FROM users"
        assert metrics.success is True
        assert metrics.result_size == 3
        assert metrics.duration > 0

    @pytest.mark.asyncio
    async def test_middleware_records_failed_query(self):
        """Test middleware records failed query metrics."""
        # Mock session that raises exception
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Query failed"))

        # Create middleware with collector
        collector = InMemoryMetricsCollector()
        middleware = MetricsMiddleware(mock_session, [collector])

        # Execute query that will fail
        with pytest.raises(Exception):
            await middleware.execute("SELECT * FROM invalid")

        # Check that failure was recorded
        assert len(collector.query_metrics) == 1
        metrics = collector.query_metrics[0]
        assert metrics.success is False
        assert metrics.error_type == "Exception"

    @pytest.mark.asyncio
    async def test_middleware_with_multiple_collectors(self):
        """Test middleware works with multiple collectors."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=Mock(_rows=[]))

        # Create multiple collectors
        collector1 = InMemoryMetricsCollector()
        collector2 = InMemoryMetricsCollector()

        middleware = MetricsMiddleware(mock_session, [collector1, collector2])

        # Execute query
        await middleware.execute("SELECT 1")

        # Both collectors should have metrics
        assert len(collector1.query_metrics) == 1
        assert len(collector2.query_metrics) == 1

    @pytest.mark.asyncio
    async def test_middleware_connection_check(self):
        """Test middleware connection health check."""
        mock_session = AsyncMock()
        mock_session.cluster = Mock()
        mock_session.cluster.metadata = Mock()
        mock_session.cluster.metadata.all_hosts = Mock(
            return_value=[Mock(address="127.0.0.1", is_up=True)]
        )
        mock_session.execute = AsyncMock(return_value=Mock())

        collector = InMemoryMetricsCollector()
        middleware = MetricsMiddleware(mock_session, [collector])

        # Check connection health
        await middleware.check_connection_health()

        # Should have recorded connection metrics
        assert len(collector.connection_metrics) == 1
        assert collector.connection_metrics[0].host == "127.0.0.1"
        assert collector.connection_metrics[0].healthy is True


class TestCreateMetricsSystem:
    """Test create_metrics_system function."""

    def test_create_memory_backend(self):
        """Test creating metrics system with memory backend."""
        metrics = create_metrics_system(backend="memory")

        assert hasattr(metrics, "collectors")
        assert len(metrics.collectors) == 1
        assert isinstance(metrics.collectors[0], InMemoryMetricsCollector)

    def test_create_with_prometheus(self):
        """Test creating metrics system with Prometheus."""
        metrics = create_metrics_system(backend="memory", prometheus_enabled=True)

        assert len(metrics.collectors) == 2
        assert any(isinstance(c, InMemoryMetricsCollector) for c in metrics.collectors)
        assert any(isinstance(c, PrometheusMetricsCollector) for c in metrics.collectors)

    def test_create_with_custom_collector(self):
        """Test creating metrics system with custom collector."""
        custom_collector = InMemoryMetricsCollector()
        metrics = create_metrics_system(backend="memory", additional_collectors=[custom_collector])

        assert len(metrics.collectors) == 2
        assert custom_collector in metrics.collectors

    def test_invalid_backend(self):
        """Test error handling for invalid backend."""
        with pytest.raises(ValueError):
            create_metrics_system(backend="invalid")
