#!/usr/bin/env python3
"""
Test the FastAPI application with mocked Cassandra to verify async wrapper integration.
"""

import asyncio
import pytest
import uuid
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path to import the app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import FastAPI app
from main import app, cluster, session


class TestFastAPIWithMockedCassandra:
    """Test FastAPI endpoints with mocked Cassandra."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        mock = Mock()
        mock.execute_async = Mock()
        mock.prepare = Mock()
        mock.keyspace = "fastapi_example"
        mock.shutdown = Mock()
        return mock
    
    def test_health_endpoint_mock(self, client):
        """Test health endpoint without real Cassandra."""
        # Mock the session execute method
        with patch('main.session') as mock_session:
            # Create a mock result
            mock_result = Mock()
            mock_result.one = Mock(return_value={'release_version': '5.0.0'})
            
            # Create async mock for execute
            async def mock_execute(*args, **kwargs):
                return mock_result
            
            mock_session.execute = mock_execute
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "timestamp" in data
    
    def test_create_user_mock(self, client):
        """Test create user endpoint with mock."""
        with patch('main.session') as mock_session:
            # Mock execute to return success
            mock_result = Mock()
            
            async def mock_execute(*args, **kwargs):
                return mock_result
            
            mock_session.execute = mock_execute
            
            # Test data
            user_data = {
                "name": "Test User",
                "email": "test@example.com",
                "age": 25
            }
            
            response = client.post("/users", json=user_data)
            assert response.status_code == 201
            data = response.json()
            assert "id" in data
            assert data["name"] == user_data["name"]
            assert data["email"] == user_data["email"]
            assert data["age"] == user_data["age"]
    
    def test_get_user_mock(self, client):
        """Test get user endpoint with mock."""
        test_user_id = str(uuid.uuid4())
        
        with patch('main.session') as mock_session:
            # Mock user data
            mock_user = {
                "id": uuid.UUID(test_user_id),
                "name": "Test User",
                "email": "test@example.com", 
                "age": 25,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Mock result
            mock_result = Mock()
            mock_result.one = Mock(return_value=mock_user)
            
            async def mock_execute(*args, **kwargs):
                return mock_result
            
            mock_session.execute = mock_execute
            
            response = client.get(f"/users/{test_user_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == test_user_id
            assert data["name"] == mock_user["name"]
    
    def test_list_users_mock(self, client):
        """Test list users endpoint with mock."""
        with patch('main.session') as mock_session:
            # Mock multiple users
            mock_users = [
                {
                    "id": uuid.uuid4(),
                    "name": f"User {i}",
                    "email": f"user{i}@example.com",
                    "age": 20 + i,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                for i in range(5)
            ]
            
            # Mock async iterator
            class MockAsyncIterator:
                def __init__(self, items):
                    self.items = items
                    self.index = 0
                    
                def __aiter__(self):
                    return self
                    
                async def __anext__(self):
                    if self.index >= len(self.items):
                        raise StopAsyncIteration
                    item = self.items[self.index]
                    self.index += 1
                    return item
            
            mock_result = MockAsyncIterator(mock_users)
            
            async def mock_execute(*args, **kwargs):
                return mock_result
            
            mock_session.execute = mock_execute
            
            response = client.get("/users?limit=10")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 5
            assert data[0]["name"] == "User 0"
    
    def test_invalid_user_id(self, client):
        """Test invalid user ID format."""
        response = client.get("/users/invalid-uuid")
        assert response.status_code == 400
        assert "Invalid user ID format" in response.json()["detail"]
    
    def test_validation_error(self, client):
        """Test validation error for invalid data."""
        invalid_data = {
            "name": "",  # Empty name
            "email": "invalid-email",  # Invalid email
            "age": -1  # Negative age
        }
        
        response = client.post("/users", json=invalid_data)
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert len(errors) > 0


def test_async_wrapper_integration():
    """Test that the async wrapper is properly integrated."""
    # Test imports from async_cassandra
    from async_cassandra import AsyncCluster, AsyncCassandraSession
    from async_cassandra.exceptions import QueryError, ConnectionError
    
    print("✓ async_cassandra imports successful")
    
    # Test that the app uses AsyncCluster
    from main import AsyncCluster as AppAsyncCluster
    assert AppAsyncCluster is AsyncCluster
    print("✓ FastAPI app uses async_cassandra.AsyncCluster")
    
    # Test basic cluster creation (mocked)
    with patch('async_cassandra.cluster.Cluster'):
        test_cluster = AsyncCluster(contact_points=["localhost"])
        assert test_cluster is not None
        print("✓ Can create AsyncCluster instance")
    
    print("\nAsync wrapper integration test passed! ✅")


def test_performance_comparison():
    """Test performance comparison between async and sync (simulated)."""
    from main import app
    from httpx import AsyncClient
    
    print("\nTesting performance endpoints...")
    
    with patch('main.session') as mock_session:
        # Mock execute to return quickly
        mock_result = Mock()
        mock_result.one = Mock(return_value={"test": "data"})
        
        async def mock_execute(*args, **kwargs):
            await asyncio.sleep(0.001)  # Simulate 1ms query time
            return mock_result
        
        mock_session.execute = mock_execute
        
        # Use TestClient for sync testing instead
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            # Test async performance endpoint
            print("Testing async performance endpoint...")
            response = client.get("/performance/async?requests=10")
            assert response.status_code == 200
            async_data = response.json()
            print(f"✓ Async: {async_data['requests']} requests in {async_data['total_time']:.3f}s")
            print(f"  ({async_data['requests_per_second']:.1f} req/s)")
            
            # Test sync performance endpoint (simulated)
            print("\nTesting sync performance endpoint...")
            response = client.get("/performance/sync?requests=10")
            assert response.status_code == 200
            sync_data = response.json()
            print(f"✓ Sync: {sync_data['requests']} requests in {sync_data['total_time']:.3f}s")
            print(f"  ({sync_data['requests_per_second']:.1f} req/s)")
            
            # Compare performance
            speedup = sync_data['total_time'] / async_data['total_time']
            print(f"\n✨ Async is {speedup:.1f}x faster than sync!")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing FastAPI + async-cassandra Integration")
    print("=" * 60)
    
    # Test async wrapper integration
    test_async_wrapper_integration()
    
    # Run performance comparison
    print("\n" + "-" * 60)
    test_performance_comparison()
    
    # Run pytest for detailed tests
    print("\n" + "-" * 60)
    print("Running detailed pytest suite...")
    pytest.main([__file__, "-v", "-s"])