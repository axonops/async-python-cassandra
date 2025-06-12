"""
BDD acceptance tests for error handling and edge case workflows.

These tests validate that the application handles errors gracefully
and provides meaningful feedback in edge cases.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.mark.acceptance
class TestErrorHandlingWorkflows:
    """Acceptance tests for error handling and edge cases."""

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
        """Create test client for FastAPI app with proper lifespan management."""
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            # Start the lifespan context
            await stack.enter_async_context(fastapi_app.router.lifespan_context(fastapi_app))

            # Create the test client
            transport = ASGITransport(app=fastapi_app)
            client = await stack.enter_async_context(
                AsyncClient(transport=transport, base_url="http://test")
            )
            yield client

    @pytest.mark.asyncio
    async def test_user_receives_clear_validation_errors(self, test_client):
        """
        GIVEN a user provides invalid input
        WHEN validation fails
        THEN they should receive clear, actionable error messages
        """
        # When: Invalid email format
        invalid_email_response = await test_client.post(
            "/users", json={"name": "Test User", "email": "not-an-email", "age": 25}
        )

        # Then: Clear validation error
        assert invalid_email_response.status_code == 422
        error_detail = invalid_email_response.json()["detail"]
        assert any("email" in str(error).lower() for error in error_detail)

        # When: Missing required field
        missing_field_response = await test_client.post(
            "/users", json={"name": "Test User", "age": 25}
        )

        # Then: Clear error about missing field
        assert missing_field_response.status_code == 422

        # When: Invalid data type
        invalid_type_response = await test_client.post(
            "/users",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "age": "twenty-five",  # Should be integer
            },
        )

        # Then: Type error is clear
        assert invalid_type_response.status_code == 422

    @pytest.mark.asyncio
    async def test_system_handles_resource_not_found_gracefully(self, test_client):
        """
        GIVEN users may request non-existent resources
        WHEN accessing missing resources
        THEN appropriate 404 errors should be returned
        """
        # When: Non-existent user ID
        fake_id = str(uuid.uuid4())
        missing_user_response = await test_client.get(f"/users/{fake_id}")

        # Then: Clear 404 error
        assert missing_user_response.status_code == 404
        assert "User not found" in missing_user_response.json()["detail"]

        # When: Updating non-existent user
        update_missing_response = await test_client.put(
            f"/users/{fake_id}", json={"name": "Updated Name"}
        )

        # Then: Consistent 404 error
        assert update_missing_response.status_code == 404
        assert "User not found" in update_missing_response.json()["detail"]

        # When: Deleting non-existent user (idempotent)
        delete_missing_response = await test_client.delete(f"/users/{fake_id}")

        # Then: Successful (idempotent delete)
        assert delete_missing_response.status_code == 204

    @pytest.mark.asyncio
    async def test_application_handles_concurrent_modifications(self, test_client):
        """
        GIVEN multiple users may modify the same resource
        WHEN concurrent modifications occur
        THEN the system should handle them safely
        """
        # Given: A user exists
        create_response = await test_client.post(
            "/users", json={"name": "Concurrent Test", "email": "concurrent@test.com", "age": 30}
        )
        user_id = create_response.json()["id"]

        # When: Multiple concurrent updates
        async def update_user(field, value):
            return await test_client.patch(f"/users/{user_id}", json={field: value})

        update_tasks = [update_user("name", f"Updated Name {i}") for i in range(5)]
        update_tasks.extend([update_user("age", 30 + i) for i in range(5)])

        responses = await asyncio.gather(*update_tasks, return_exceptions=True)

        # Then: All updates complete (last write wins)
        successful_updates = [
            r for r in responses if not isinstance(r, Exception) and r.status_code == 200
        ]
        assert len(successful_updates) == 10

        # Final state is consistent
        final_response = await test_client.get(f"/users/{user_id}")
        assert final_response.status_code == 200

    @pytest.mark.asyncio
    async def test_system_prevents_invalid_operations(self, test_client):
        """
        GIVEN users may attempt invalid operations
        WHEN invalid operations are requested
        THEN they should be prevented with appropriate errors
        """
        # When: Invalid UUID format
        invalid_uuid_response = await test_client.get("/users/not-a-valid-uuid")

        # Then: Clear error about invalid format
        assert invalid_uuid_response.status_code == 400
        assert "Invalid UUID" in invalid_uuid_response.json()["detail"]

        # When: Update with no fields
        create_response = await test_client.post(
            "/users", json={"name": "Test User", "email": "test@example.com", "age": 25}
        )
        user_id = create_response.json()["id"]

        empty_update_response = await test_client.put(f"/users/{user_id}", json={})

        # Then: Error about no fields to update
        assert empty_update_response.status_code == 400
        assert "No fields to update" in empty_update_response.json()["detail"]

    @pytest.mark.asyncio
    async def test_streaming_handles_edge_cases(self, test_client):
        """
        GIVEN streaming operations have edge cases
        WHEN edge cases occur
        THEN they should be handled appropriately
        """
        # When: Streaming with no data
        empty_stream_response = await test_client.get("/users/stream?limit=0")

        # Then: Empty result is handled
        if empty_stream_response.status_code != 200:
            print(f"Error response: {empty_stream_response.json()}")
        assert empty_stream_response.status_code == 200
        result = empty_stream_response.json()
        assert len(result["users"]) == 0

        # When: Invalid streaming parameters
        invalid_params_response = await test_client.get("/users/stream?fetch_size=0")

        # Then: Validation error
        assert invalid_params_response.status_code == 422

        # When: Extremely high limits (protected by validation)
        high_limit_response = await test_client.get("/users/stream?limit=100000")

        # Then: Rejected due to limit
        assert high_limit_response.status_code == 422
