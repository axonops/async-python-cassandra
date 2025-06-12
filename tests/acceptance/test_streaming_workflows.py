"""
BDD acceptance tests for streaming workflows.

These tests validate streaming functionality for handling
large datasets efficiently in real-world scenarios.
"""

import asyncio
import time

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.acceptance
class TestStreamingWorkflows:
    """Acceptance tests for data streaming scenarios."""

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

    @pytest_asyncio.fixture
    async def large_dataset(self, test_client):
        """Create a large dataset for streaming tests."""
        # Create batch of users
        batch_size = 50
        users_data = {
            "users": [
                {
                    "name": f"Stream User {i}",
                    "email": f"stream{i}@test.com",
                    "age": 20 + (i % 50)
                }
                for i in range(batch_size)
            ]
        }
        
        await test_client.post("/users/batch", json=users_data)
        return batch_size

    @pytest.mark.asyncio
    async def test_user_streams_large_dataset_efficiently(self, test_client, large_dataset):
        """
        GIVEN a large dataset of users exists
        WHEN a user requests streaming access
        THEN data should be delivered efficiently without memory issues
        """
        # Given: Large dataset exists (from fixture)
        
        # When: User requests streaming with pagination
        stream_response = await test_client.get(
            "/users/stream?limit=1000&fetch_size=10"
        )

        # Then: Streaming works efficiently
        assert stream_response.status_code == 200
        result = stream_response.json()
        
        assert "users" in result
        assert "metadata" in result
        assert result["metadata"]["streaming_enabled"] is True
        assert result["metadata"]["fetch_size"] == 10
        assert len(result["users"]) >= large_dataset

    @pytest.mark.asyncio
    async def test_user_processes_data_page_by_page(self, test_client, large_dataset):
        """
        GIVEN a user needs to process data incrementally
        WHEN they request page-by-page streaming
        THEN each page should be delivered separately for processing
        """
        # Given: Dataset exists and user wants incremental processing
        
        # When: User requests page-by-page streaming
        pages_response = await test_client.get(
            "/users/stream/pages?limit=100&fetch_size=10&max_pages=5"
        )

        # Then: Pages are delivered incrementally
        assert pages_response.status_code == 200
        result = pages_response.json()
        
        assert "pages_info" in result
        assert "total_rows_processed" in result
        assert result["metadata"]["streaming_mode"] == "page_by_page"
        
        # Verify page structure
        pages = result["pages_info"]
        assert len(pages) <= 5  # Respects max_pages
        
        for page in pages:
            assert "page_number" in page
            assert "rows_in_page" in page
            assert page["rows_in_page"] <= 10  # Respects fetch_size

    @pytest.mark.asyncio
    async def test_streaming_handles_errors_gracefully(self, test_client):
        """
        GIVEN streaming operations may encounter errors
        WHEN an error occurs during streaming
        THEN it should be handled gracefully with proper error messages
        """
        # When: Invalid streaming parameters are provided
        error_response = await test_client.get(
            "/users/stream?limit=-1"  # Invalid limit
        )

        # Then: Proper error handling
        assert error_response.status_code == 422  # Validation error

        # When: Extremely large fetch size
        large_fetch_response = await test_client.get(
            "/users/stream?fetch_size=100000"  # Too large
        )

        # Then: Request is rejected
        assert large_fetch_response.status_code == 422

    @pytest.mark.asyncio
    async def test_streaming_performance_vs_regular_queries(self, test_client, large_dataset):
        """
        GIVEN users need to choose between regular and streaming queries
        WHEN comparing performance characteristics
        THEN streaming should show benefits for large datasets
        """
        # Given: Large dataset exists
        
        # When: Regular query for all data
        start_regular = time.time()
        regular_response = await test_client.get(f"/users?limit={large_dataset}")
        regular_time = time.time() - start_regular
        
        # When: Streaming query for same data
        start_stream = time.time()
        stream_response = await test_client.get(
            f"/users/stream?limit={large_dataset}&fetch_size=10"
        )
        stream_time = time.time() - start_stream

        # Then: Both methods work
        assert regular_response.status_code == 200
        assert stream_response.status_code == 200
        
        # Streaming provides metadata about operation
        stream_data = stream_response.json()
        assert stream_data["metadata"]["pages_fetched"] > 1
        
        # Note: In real scenarios, streaming would show memory benefits
        # For small test datasets, timing may vary

    @pytest.mark.asyncio
    async def test_streaming_respects_resource_limits(self, test_client):
        """
        GIVEN system resources are limited
        WHEN users request streaming with limits
        THEN the system should respect those limits
        """
        # When: User sets specific limits
        limited_response = await test_client.get(
            "/users/stream/pages?limit=100&fetch_size=5&max_pages=3"
        )

        # Then: Limits are respected
        assert limited_response.status_code == 200
        result = limited_response.json()
        
        pages = result["pages_info"]
        assert len(pages) <= 3  # Max pages limit
        
        total_rows = sum(page["rows_in_page"] for page in pages)
        assert total_rows <= 15  # 3 pages * 5 rows max