"""
BDD acceptance tests for performance and reliability workflows.

These tests validate that the async-cassandra library delivers
on its performance promises in real-world scenarios.
"""

import asyncio
import time
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.mark.acceptance
class TestPerformanceWorkflows:
    """Acceptance tests for performance-critical scenarios."""

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
    async def test_developer_achieves_high_concurrency(self, test_client):
        """
        GIVEN a developer needs high-concurrency database access
        WHEN they use async operations
        THEN they should achieve better performance than sequential operations
        """
        # Given: Developer wants to compare async vs sync performance
        num_requests = 50

        # When: Using async operations
        async_response = await test_client.get(f"/performance/async?requests={num_requests}")

        # When: Using sync-style operations
        sync_response = await test_client.get(f"/performance/sync?requests={num_requests}")

        # Then: Both complete successfully
        assert async_response.status_code == 200
        assert sync_response.status_code == 200

        async_data = async_response.json()
        sync_data = sync_response.json()

        # Async should complete faster for concurrent operations
        assert async_data["total_time"] < sync_data["total_time"]
        assert async_data["requests_per_second"] > sync_data["requests_per_second"]

    @pytest.mark.asyncio
    async def test_application_handles_concurrent_users(self, test_client):
        """
        GIVEN multiple users access the application simultaneously
        WHEN they perform various operations concurrently
        THEN all operations should complete successfully without conflicts
        """
        # Given: Multiple concurrent users
        num_users = 10

        async def user_journey(user_id: int):
            """Simulate a complete user journey."""
            # Create profile
            create_data = {
                "name": f"Concurrent User {user_id}",
                "email": f"concurrent{user_id}@test.com",
                "age": 25 + user_id,
            }
            create_resp = await test_client.post("/users", json=create_data)
            assert create_resp.status_code == 201

            user = create_resp.json()
            user_uuid = user["id"]

            # Read profile
            read_resp = await test_client.get(f"/users/{user_uuid}")
            assert read_resp.status_code == 200

            # Update profile
            update_data = {"age": 26 + user_id}
            update_resp = await test_client.patch(f"/users/{user_uuid}", json=update_data)
            assert update_resp.status_code == 200

            # List users
            list_resp = await test_client.get("/users?limit=100")
            assert list_resp.status_code == 200

            return user_uuid

        # When: All users perform operations concurrently
        start_time = time.time()
        user_ids = await asyncio.gather(*[user_journey(i) for i in range(num_users)])
        duration = time.time() - start_time

        # Then: All operations complete successfully
        assert len(user_ids) == num_users
        assert len(set(user_ids)) == num_users  # All unique IDs

        # Performance is reasonable
        assert duration < 10.0  # Should complete within 10 seconds

    @pytest.mark.asyncio
    async def test_application_recovers_from_errors(self, test_client):
        """
        GIVEN the application may encounter errors
        WHEN errors occur during operation
        THEN the application should handle them gracefully and continue functioning
        """
        # Given: Application is running normally
        health_response = await test_client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "healthy"

        # When: Invalid operations occur
        error_operations = [
            # Invalid UUID
            test_client.get("/users/invalid-uuid"),
            # Missing required fields
            test_client.post("/users", json={"name": "No Email"}),
            # Update non-existent user
            test_client.put(f"/users/{str(uuid.uuid4())}", json={"name": "Ghost"}),
        ]

        error_responses = await asyncio.gather(*error_operations, return_exceptions=True)

        # Then: Errors are handled gracefully
        for response in error_responses:
            if not isinstance(response, Exception):
                assert response.status_code in [400, 404, 422]

        # And: Application continues to function
        health_check = await test_client.get("/health")
        assert health_check.status_code == 200
        assert health_check.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_application_handles_slow_operations(self, test_client):
        """
        GIVEN some operations may be slow
        WHEN users encounter slow operations
        THEN the application should handle timeouts appropriately
        """
        # Given: User has a short timeout requirement

        # When: Operation would exceed timeout
        timeout_response = await test_client.get(
            "/slow_query", headers={"X-Request-Timeout": "0.5"}  # 500ms timeout
        )

        # Then: Timeout is detected and handled
        assert timeout_response.status_code == 504
        assert "Gateway Timeout" in timeout_response.json()["detail"]

        # When: Adequate timeout is provided
        success_response = await test_client.get(
            "/slow_query", headers={"X-Request-Timeout": "10.0"}  # 10s timeout
        )

        # Then: Operation completes successfully
        assert success_response.status_code == 200

    @pytest.mark.asyncio
    async def test_batch_operations_improve_efficiency(self, test_client):
        """
        GIVEN users need to create multiple records
        WHEN they use batch operations
        THEN it should be more efficient than individual operations
        """
        # Given: Multiple users to create
        batch_size = 20
        users_data = [
            {"name": f"Batch User {i}", "email": f"batch{i}@test.com", "age": 30 + i}
            for i in range(batch_size)
        ]

        # When: Creating users individually
        start_individual = time.time()
        individual_responses = await asyncio.gather(
            *[test_client.post("/users", json=user_data) for user_data in users_data]
        )
        individual_time = time.time() - start_individual

        # When: Creating users in batch
        start_batch = time.time()
        batch_response = await test_client.post("/users/batch", json={"users": users_data})
        batch_time = time.time() - start_batch

        # Then: Both methods work
        assert all(r.status_code == 201 for r in individual_responses)
        assert batch_response.status_code == 201

        # Batch operation is more efficient
        assert batch_time < individual_time
        assert len(batch_response.json()["created"]) == batch_size
