"""
BDD acceptance tests for user workflows in the FastAPI application.

These tests follow the Given-When-Then format to validate
complete user journeys through the async-cassandra library.
"""

import asyncio
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient

from async_cassandra import AsyncCluster


@pytest.mark.acceptance
class TestUserWorkflows:
    """Acceptance tests for user-facing workflows."""

    @pytest_asyncio.fixture
    async def fastapi_app(self):
        """Create FastAPI application for testing."""
        import sys
        import os
        
        # Add examples directory to path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../examples/fastapi_app"))
        
        from main import app
        return app

    @pytest_asyncio.fixture
    async def test_client(self, fastapi_app):
        """Create test client for FastAPI app."""
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_user_creates_and_retrieves_profile(self, test_client):
        """
        GIVEN a user wants to create a profile
        WHEN they submit valid user data
        THEN the profile should be created and retrievable
        """
        # Given: Valid user data
        user_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "age": 30
        }

        # When: User creates profile
        create_response = await test_client.post("/users", json=user_data)
        
        # Then: Profile is created successfully
        assert create_response.status_code == 201
        created_user = create_response.json()
        assert created_user["name"] == user_data["name"]
        assert created_user["email"] == user_data["email"]
        assert created_user["age"] == user_data["age"]
        assert "id" in created_user
        assert "created_at" in created_user
        assert "updated_at" in created_user

        # And: Profile can be retrieved
        user_id = created_user["id"]
        get_response = await test_client.get(f"/users/{user_id}")
        assert get_response.status_code == 200
        retrieved_user = get_response.json()
        assert retrieved_user == created_user

    @pytest.mark.asyncio
    async def test_user_updates_profile_information(self, test_client):
        """
        GIVEN a user has an existing profile
        WHEN they update their information
        THEN the changes should be persisted and reflected
        """
        # Given: Existing user profile
        initial_data = {
            "name": "Jane Smith",
            "email": "jane@example.com",
            "age": 25
        }
        create_response = await test_client.post("/users", json=initial_data)
        user = create_response.json()
        user_id = user["id"]
        original_updated_at = user["updated_at"]

        # When: User updates their profile
        update_data = {
            "name": "Jane Johnson",
            "age": 26
        }
        update_response = await test_client.put(f"/users/{user_id}", json=update_data)

        # Then: Updates are successful
        assert update_response.status_code == 200
        updated_user = update_response.json()
        assert updated_user["name"] == update_data["name"]
        assert updated_user["age"] == update_data["age"]
        assert updated_user["email"] == initial_data["email"]  # Unchanged
        assert updated_user["updated_at"] > original_updated_at

    @pytest.mark.asyncio
    async def test_user_deletes_their_account(self, test_client):
        """
        GIVEN a user wants to delete their account
        WHEN they request deletion
        THEN their profile should be removed completely
        """
        # Given: User with existing account
        user_data = {
            "name": "Delete Me",
            "email": "delete@example.com",
            "age": 35
        }
        create_response = await test_client.post("/users", json=user_data)
        user_id = create_response.json()["id"]

        # When: User deletes their account
        delete_response = await test_client.delete(f"/users/{user_id}")

        # Then: Account is deleted
        assert delete_response.status_code == 204

        # And: Profile no longer exists
        get_response = await test_client.get(f"/users/{user_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_user_searches_through_user_list(self, test_client):
        """
        GIVEN multiple users exist in the system
        WHEN a user searches for all users
        THEN they should see a paginated list
        """
        # Given: Multiple users exist
        test_users = [
            {"name": f"User {i}", "email": f"user{i}@test.com", "age": 20 + i}
            for i in range(5)
        ]
        
        for user_data in test_users:
            await test_client.post("/users", json=user_data)

        # When: User lists all users
        list_response = await test_client.get("/users?limit=10")

        # Then: Users are returned
        assert list_response.status_code == 200
        users = list_response.json()
        assert isinstance(users, list)
        assert len(users) >= 5  # At least our test users

    @pytest.mark.asyncio
    async def test_user_handles_invalid_operations_gracefully(self, test_client):
        """
        GIVEN a user attempts invalid operations
        WHEN they provide invalid data or access non-existent resources
        THEN appropriate error messages should be returned
        """
        # Given/When: Invalid UUID format
        invalid_response = await test_client.get("/users/not-a-uuid")
        
        # Then: Proper error handling
        assert invalid_response.status_code == 400
        assert "Invalid UUID" in invalid_response.json()["detail"]

        # Given/When: Non-existent user
        fake_uuid = str(uuid.uuid4())
        missing_response = await test_client.get(f"/users/{fake_uuid}")
        
        # Then: 404 response
        assert missing_response.status_code == 404
        assert "User not found" in missing_response.json()["detail"]

        # Given/When: Invalid email format
        invalid_user = {
            "name": "Bad Email",
            "email": "not-an-email",
            "age": 30
        }
        create_response = await test_client.post("/users", json=invalid_user)
        
        # Then: Validation error
        assert create_response.status_code == 422