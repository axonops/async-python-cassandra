"""
Integration tests for FastAPI example application.
These tests ensure the example application continues to work correctly.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add examples directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples" / "fastapi_app"))

from main import app


@pytest_asyncio.fixture
async def fastapi_client(cassandra_session) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for FastAPI tests."""
    # Initialize the app lifespan context
    async with app.router.lifespan_context(app):
        # Use ASGI transport to test the app directly
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest.mark.integration
class TestFastAPIHealth:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, fastapi_client: AsyncClient):
        """Test health check returns healthy status."""
        response = await fastapi_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["cassandra_connected"] is True
        assert "timestamp" in data


@pytest.mark.integration
class TestFastAPIUserCRUD:
    """Test user CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_user(self, fastapi_client: AsyncClient):
        """Test creating a new user."""
        user_data = {"name": "John Doe", "email": "john@example.com", "age": 30}

        response = await fastapi_client.post("/users", json=user_data)

        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert data["name"] == user_data["name"]
        assert data["email"] == user_data["email"]
        assert data["age"] == user_data["age"]
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_user(self, fastapi_client: AsyncClient):
        """Test getting user by ID."""
        # First create a user
        user_data = {"name": "Jane Doe", "email": "jane@example.com", "age": 25}

        create_response = await fastapi_client.post("/users", json=user_data)
        created_user = create_response.json()
        user_id = created_user["id"]

        # Get the user
        response = await fastapi_client.get(f"/users/{user_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == user_id
        assert data["name"] == user_data["name"]
        assert data["email"] == user_data["email"]
        assert data["age"] == user_data["age"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, fastapi_client: AsyncClient):
        """Test getting non-existent user returns 404."""
        fake_id = str(uuid.uuid4())

        response = await fastapi_client.get(f"/users/{fake_id}")

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_user_id_format(self, fastapi_client: AsyncClient):
        """Test invalid user ID format returns 400."""
        response = await fastapi_client.get("/users/invalid-uuid")

        assert response.status_code == 400
        assert "Invalid user ID format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_users(self, fastapi_client: AsyncClient):
        """Test listing users."""
        # Create multiple users
        users = []
        for i in range(5):
            user_data = {
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "age": 20 + i,
            }
            response = await fastapi_client.post("/users", json=user_data)
            users.append(response.json())

        # List users
        response = await fastapi_client.get("/users?limit=10")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 5  # At least the users we created

    @pytest.mark.asyncio
    async def test_update_user(self, fastapi_client: AsyncClient):
        """Test updating user."""
        # Create a user
        user_data = {"name": "Update Test", "email": "update@example.com", "age": 30}

        create_response = await fastapi_client.post("/users", json=user_data)
        user_id = create_response.json()["id"]

        # Update the user
        update_data = {"name": "Updated Name", "age": 31}

        response = await fastapi_client.put(f"/users/{user_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == user_id
        assert data["name"] == update_data["name"]
        assert data["email"] == user_data["email"]  # Unchanged
        assert data["age"] == update_data["age"]
        assert data["updated_at"] > data["created_at"]

    @pytest.mark.asyncio
    async def test_partial_update(self, fastapi_client: AsyncClient):
        """Test partial update of user."""
        # Create a user
        user_data = {
            "name": "Partial Update",
            "email": "partial@example.com",
            "age": 25,
        }

        create_response = await fastapi_client.post("/users", json=user_data)
        user_id = create_response.json()["id"]

        # Update only email
        update_data = {"email": "newemail@example.com"}

        response = await fastapi_client.put(f"/users/{user_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()

        assert data["email"] == update_data["email"]
        assert data["name"] == user_data["name"]  # Unchanged
        assert data["age"] == user_data["age"]  # Unchanged

    @pytest.mark.asyncio
    async def test_delete_user(self, fastapi_client: AsyncClient):
        """Test deleting user."""
        # Create a user
        user_data = {"name": "Delete Test", "email": "delete@example.com", "age": 35}

        create_response = await fastapi_client.post("/users", json=user_data)
        user_id = create_response.json()["id"]

        # Delete the user
        response = await fastapi_client.delete(f"/users/{user_id}")

        assert response.status_code == 204

        # Verify user is deleted
        get_response = await fastapi_client.get(f"/users/{user_id}")
        assert get_response.status_code == 404


@pytest.mark.integration
class TestFastAPIPerformance:
    """Test performance endpoints."""

    @pytest.mark.asyncio
    async def test_async_performance(self, fastapi_client: AsyncClient):
        """Test async performance endpoint."""
        response = await fastapi_client.get("/performance/async?requests=10")

        assert response.status_code == 200
        data = response.json()

        assert data["requests"] == 10
        assert data["total_time"] > 0
        assert data["avg_time_per_request"] > 0
        assert data["requests_per_second"] > 0

    @pytest.mark.asyncio
    async def test_sync_performance(self, fastapi_client: AsyncClient):
        """Test sync performance endpoint."""
        response = await fastapi_client.get("/performance/sync?requests=10")

        assert response.status_code == 200
        data = response.json()

        assert data["requests"] == 10
        assert data["total_time"] > 0
        assert data["avg_time_per_request"] > 0
        assert data["requests_per_second"] > 0

    @pytest.mark.asyncio
    async def test_performance_comparison(self, fastapi_client: AsyncClient):
        """Test that async is faster than sync for concurrent operations."""
        # Run async test
        async_response = await fastapi_client.get("/performance/async?requests=50")
        async_data = async_response.json()

        # Run sync test
        sync_response = await fastapi_client.get("/performance/sync?requests=50")
        sync_data = sync_response.json()

        # Async should be significantly faster
        assert async_data["requests_per_second"] > sync_data["requests_per_second"]


@pytest.mark.integration
class TestFastAPIConcurrency:
    """Test concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_user_creation(self, fastapi_client: AsyncClient):
        """Test creating multiple users concurrently."""

        async def create_user(i: int):
            user_data = {
                "name": f"Concurrent User {i}",
                "email": f"concurrent{i}@example.com",
                "age": 20 + i,
            }
            response = await fastapi_client.post("/users", json=user_data)
            return response.json()

        # Create 20 users concurrently
        users = await asyncio.gather(*[create_user(i) for i in range(20)])

        assert len(users) == 20

        # Verify all users have unique IDs
        user_ids = [user["id"] for user in users]
        assert len(set(user_ids)) == 20

    @pytest.mark.asyncio
    async def test_concurrent_read_write(self, fastapi_client: AsyncClient):
        """Test concurrent read and write operations."""
        # Create initial user
        user_data = {
            "name": "Concurrent Test",
            "email": "concurrent@example.com",
            "age": 30,
        }

        create_response = await fastapi_client.post("/users", json=user_data)
        user_id = create_response.json()["id"]

        async def read_user():
            response = await fastapi_client.get(f"/users/{user_id}")
            return response.json()

        async def update_user(age: int):
            response = await fastapi_client.put(f"/users/{user_id}", json={"age": age})
            return response.json()

        # Run mixed read/write operations concurrently
        operations = []
        for i in range(10):
            if i % 2 == 0:
                operations.append(read_user())
            else:
                operations.append(update_user(30 + i))

        results = await asyncio.gather(*operations, return_exceptions=True)

        # Verify no errors occurred
        for result in results:
            assert not isinstance(result, Exception)
