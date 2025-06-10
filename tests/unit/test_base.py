"""
Unit tests for base module decorators and utilities.
"""

import pytest

from async_cassandra.base import check_not_closed, ExceptionHandler
from async_cassandra.exceptions import AsyncCassandraError, ConnectionError


class MockSession:
    """Mock session for testing decorators."""
    
    def __init__(self, is_closed=False):
        self._closed = is_closed
        self.call_count = 0
    
    @property
    def is_closed(self):
        return self._closed
    
    def _check_not_closed(self):
        if self._closed:
            raise ConnectionError("Session is closed")
    
    @check_not_closed
    async def async_method(self, arg1, arg2=None):
        """Async method with decorator."""
        self.call_count += 1
        return f"async_result: {arg1}, {arg2}"
    
    @check_not_closed
    async def another_async_method(self, arg1):
        """Another async method with decorator."""
        self.call_count += 1
        return f"another_async_result: {arg1}"


class TestCheckNotClosedDecorator:
    """Test check_not_closed decorator."""
    
    @pytest.mark.asyncio
    async def test_async_method_when_open(self):
        """Test decorator allows async method when session is open."""
        session = MockSession(is_closed=False)
        result = await session.async_method("test", arg2="value")
        
        assert result == "async_result: test, value"
        assert session.call_count == 1
    
    @pytest.mark.asyncio
    async def test_async_method_when_closed(self):
        """Test decorator raises error for async method when session is closed."""
        session = MockSession(is_closed=True)
        
        with pytest.raises(ConnectionError) as exc_info:
            await session.async_method("test")
        
        assert str(exc_info.value) == "Session is closed"
        assert session.call_count == 0  # Method should not be called
    
    @pytest.mark.asyncio
    async def test_another_async_method_when_open(self):
        """Test decorator allows another async method when session is open."""
        session = MockSession(is_closed=False)
        result = await session.another_async_method("test")
        
        assert result == "another_async_result: test"
        assert session.call_count == 1
    
    @pytest.mark.asyncio
    async def test_another_async_method_when_closed(self):
        """Test decorator raises error for another async method when session is closed."""
        session = MockSession(is_closed=True)
        
        with pytest.raises(ConnectionError) as exc_info:
            await session.another_async_method("test")
        
        assert str(exc_info.value) == "Session is closed"
        assert session.call_count == 0
    
    def test_decorator_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""
        session = MockSession()
        
        assert session.async_method.__name__ == "async_method"
        assert session.async_method.__doc__ == "Async method with decorator."
        assert session.another_async_method.__name__ == "another_async_method"
        assert session.another_async_method.__doc__ == "Another async method with decorator."
    
    @pytest.mark.asyncio
    async def test_decorator_with_no_check_method(self):
        """Test decorator handles objects without _check_not_closed method."""
        class NoCheckObject:
            @check_not_closed
            async def method(self):
                return "success"
        
        obj = NoCheckObject()
        # Should work without _check_not_closed method
        result = await obj.method()
        assert result == "success"


class TestExceptionHandler:
    """Test ExceptionHandler context manager."""
    
    @pytest.mark.asyncio
    async def test_no_exception(self):
        """Test handler when no exception is raised."""
        async with ExceptionHandler("Test operation", AsyncCassandraError):
            result = 1 + 1
        
        assert result == 2  # Normal execution
    
    @pytest.mark.asyncio
    async def test_wrap_exception(self):
        """Test handler wraps exceptions."""
        with pytest.raises(AsyncCassandraError) as exc_info:
            async with ExceptionHandler("Test operation failed", AsyncCassandraError):
                raise ValueError("Original error")
        
        assert str(exc_info.value) == "Test operation failed: Original error"
        assert isinstance(exc_info.value.__cause__, ValueError)
    
    @pytest.mark.asyncio
    async def test_reraise_exceptions(self):
        """Test handler passes through specified exceptions."""
        class CustomError(Exception):
            pass
        
        with pytest.raises(CustomError) as exc_info:
            async with ExceptionHandler(
                "Test operation",
                AsyncCassandraError,
                reraise_exceptions=(CustomError,)
            ):
                raise CustomError("Should not be wrapped")
        
        # Original exception should be raised, not wrapped
        assert type(exc_info.value) is CustomError
        assert str(exc_info.value) == "Should not be wrapped"
    
    @pytest.mark.asyncio
    async def test_multiple_reraise_exceptions(self):
        """Test handler with multiple passthrough exceptions."""
        class Error1(Exception):
            pass
        
        class Error2(Exception):
            pass
        
        # Test first exception type
        with pytest.raises(Error1):
            async with ExceptionHandler(
                "Operation",
                AsyncCassandraError,
                reraise_exceptions=(Error1, Error2)
            ):
                raise Error1("Error 1")
        
        # Test second exception type
        with pytest.raises(Error2):
            async with ExceptionHandler(
                "Operation",
                AsyncCassandraError,
                reraise_exceptions=(Error1, Error2)
            ):
                raise Error2("Error 2")
        
        # Test non-passthrough exception
        with pytest.raises(AsyncCassandraError):
            async with ExceptionHandler(
                "Operation",
                AsyncCassandraError,
                reraise_exceptions=(Error1, Error2)
            ):
                raise ValueError("Should be wrapped")
    
    @pytest.mark.asyncio
    async def test_sync_context_manager(self):
        """Test ExceptionHandler works as sync context manager too."""
        with pytest.raises(AsyncCassandraError):
            with ExceptionHandler("Sync operation failed", AsyncCassandraError):
                raise RuntimeError("Sync error")
    
    @pytest.mark.asyncio
    async def test_exception_handler_with_empty_message(self):
        """Test handler with empty error message."""
        with pytest.raises(AsyncCassandraError) as exc_info:
            async with ExceptionHandler("", AsyncCassandraError):
                raise ValueError("Error")
        
        assert str(exc_info.value) == ": Error"
    
    @pytest.mark.asyncio
    async def test_exception_handler_preserves_traceback(self):
        """Test handler preserves original exception traceback."""
        try:
            async with ExceptionHandler("Operation failed", AsyncCassandraError):
                raise ValueError("Original error")
        except AsyncCassandraError as e:
            import traceback
            
            # Check that the cause is properly chained
            assert e.__cause__ is not None
            assert isinstance(e.__cause__, ValueError)
            assert str(e.__cause__) == "Original error"
            
            # Check that original traceback is preserved in __cause__
            cause_tb_str = ''.join(traceback.format_exception(type(e.__cause__), e.__cause__, e.__cause__.__traceback__))
            assert "raise ValueError" in cause_tb_str
            assert "test_exception_handler_preserves_traceback" in cause_tb_str
    
    @pytest.mark.asyncio
    async def test_nested_exception_handlers(self):
        """Test nested ExceptionHandler usage."""
        class OuterError(Exception):
            pass
        
        class InnerError(Exception):
            pass
        
        with pytest.raises(OuterError) as exc_info:
            async with ExceptionHandler("Outer operation", OuterError):
                async with ExceptionHandler("Inner operation", InnerError):
                    raise ValueError("Deep error")
        
        # Should be wrapped by inner handler first, then outer
        assert isinstance(exc_info.value, OuterError)
        assert isinstance(exc_info.value.__cause__, InnerError)
        assert isinstance(exc_info.value.__cause__.__cause__, ValueError)