"""
BDD acceptance tests for monitoring and observability workflows.

These tests validate that developers can effectively monitor
and understand their application's behavior in production.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.mark.acceptance
class TestMonitoringWorkflows:
    """Acceptance tests for monitoring and observability scenarios."""

    @pytest_asyncio.fixture
    async def fastapi_app(self):
        """Create FastAPI application for testing."""
        import os
        import sys

        # Add examples directory to path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../examples/fastapi_app"))

        from main import app

        return app

    @pytest_asyncio.fixture
    async def test_client(self, fastapi_app):
        """Create test client for FastAPI app."""
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_operations_team_monitors_application_health(self, test_client):
        """
        GIVEN operations team needs to monitor application health
        WHEN they check health endpoints
        THEN they should receive comprehensive health status
        """
        # When: Operations team checks health
        health_response = await test_client.get("/health")

        # Then: Health status is available
        assert health_response.status_code == 200
        health_data = health_response.json()

        assert "status" in health_data
        assert "cassandra_connected" in health_data
        assert "timestamp" in health_data
        assert health_data["status"] in ["healthy", "unhealthy"]

    @pytest.mark.asyncio
    async def test_developer_accesses_performance_metrics(self, test_client):
        """
        GIVEN developers need to understand performance characteristics
        WHEN they access metrics endpoints
        THEN they should receive actionable performance data
        """
        # When: Developer checks metrics
        metrics_response = await test_client.get("/metrics")

        # Then: Comprehensive metrics are available
        assert metrics_response.status_code == 200
        metrics = metrics_response.json()

        assert "total_requests" in metrics
        assert "query_performance" in metrics
        assert "cassandra_connections" in metrics

        # Performance metrics structure
        perf = metrics["query_performance"]
        assert "avg_response_time_ms" in perf
        assert "p95_response_time_ms" in perf
        assert "p99_response_time_ms" in perf

        # Connection pool metrics
        connections = metrics["cassandra_connections"]
        assert "active" in connections
        assert "idle" in connections
        assert "total" in connections

    @pytest.mark.asyncio
    async def test_system_provides_detailed_operation_metadata(self, test_client):
        """
        GIVEN developers need to understand operation details
        WHEN they perform operations
        THEN metadata about the operation should be available
        """
        # Given: Some test data
        await test_client.post(
            "/users/batch",
            json={
                "users": [
                    {"name": f"Meta User {i}", "email": f"meta{i}@test.com", "age": 25}
                    for i in range(10)
                ]
            },
        )

        # When: Streaming operation with metadata
        stream_response = await test_client.get("/users/stream?limit=10&fetch_size=5")

        # Then: Metadata is provided
        assert stream_response.status_code == 200
        result = stream_response.json()

        metadata = result["metadata"]
        assert metadata["streaming_enabled"] is True
        assert "total_returned" in metadata
        assert "pages_fetched" in metadata
        assert "fetch_size" in metadata

    @pytest.mark.asyncio
    async def test_application_provides_graceful_shutdown(self, test_client):
        """
        GIVEN operations team needs to perform maintenance
        WHEN they initiate shutdown
        THEN the application should shut down gracefully
        """
        # When: Shutdown is initiated
        shutdown_response = await test_client.post("/shutdown")

        # Then: Shutdown is acknowledged
        assert shutdown_response.status_code == 200
        assert "message" in shutdown_response.json()
        assert "Shutdown initiated" in shutdown_response.json()["message"]

    @pytest.mark.asyncio
    async def test_developer_debugs_slow_queries(self, test_client):
        """
        GIVEN developers need to identify performance issues
        WHEN they test slow query scenarios
        THEN they should be able to identify bottlenecks
        """
        # When: Testing known slow endpoint
        slow_response = await test_client.get("/long_running_query", timeout=15.0)

        # Then: Slow query completes (for testing purposes)
        assert slow_response.status_code == 200
        assert "Long query completed" in slow_response.json()["message"]

        # In real scenarios, this would help identify:
        # - Which queries are slow
        # - Timeout configurations
        # - Performance bottlenecks
