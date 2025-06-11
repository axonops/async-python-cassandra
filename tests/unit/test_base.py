"""
Unit tests for base module decorators and utilities.
"""

import pytest

from async_cassandra.base import AsyncCloseable, AsyncContextManageable
from async_cassandra.exceptions import ConnectionError


class TestAsyncCloseable:
    """Test AsyncCloseable base class."""

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Test that close can be called multiple times safely."""

        class TestResource(AsyncCloseable):
            close_count = 0

            async def _do_close(self):
                self.close_count += 1

        resource = TestResource()
        assert not resource.is_closed

        # First close
        await resource.close()
        assert resource.is_closed
        assert resource.close_count == 1

        # Second close should not call _do_close again
        await resource.close()
        assert resource.is_closed
        assert resource.close_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_close(self):
        """Test that concurrent close calls are handled properly."""
        import asyncio

        class TestResource(AsyncCloseable):
            close_count = 0

            async def _do_close(self):
                await asyncio.sleep(0.1)  # Simulate slow close
                self.close_count += 1

        resource = TestResource()

        # Call close concurrently
        await asyncio.gather(
            resource.close(),
            resource.close(),
            resource.close(),
        )

        # Should only close once
        assert resource.is_closed
        assert resource.close_count == 1

    @pytest.mark.asyncio
    async def test_check_not_closed(self):
        """Test _check_not_closed method."""

        class TestResource(AsyncCloseable):
            async def _do_close(self):
                pass

            def use_resource(self):
                self._check_not_closed()
                return "success"

        resource = TestResource()

        # Should work when not closed
        assert resource.use_resource() == "success"

        # Close the resource
        await resource.close()

        # Should raise when closed
        with pytest.raises(ConnectionError) as exc_info:
            resource.use_resource()

        assert "TestResource is closed" in str(exc_info.value)


class TestAsyncContextManageable:
    """Test AsyncContextManageable mixin."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager functionality."""

        class TestResource(AsyncCloseable, AsyncContextManageable):
            close_count = 0

            async def _do_close(self):
                self.close_count += 1

        # Use as context manager
        async with TestResource() as resource:
            assert not resource.is_closed
            assert resource.close_count == 0

        # Should be closed after exiting context
        assert resource.is_closed
        assert resource.close_count == 1

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test context manager closes resource on exception."""

        class TestResource(AsyncCloseable, AsyncContextManageable):
            close_count = 0

            async def _do_close(self):
                self.close_count += 1

        resource = None
        try:
            async with TestResource() as res:
                resource = res
                raise ValueError("Test error")
        except ValueError:
            pass

        # Should still close resource on exception
        assert resource is not None
        assert resource.is_closed
        assert resource.close_count == 1
