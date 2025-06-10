"""
Base classes and mixins for async-cassandra.

This module provides common functionality to reduce code duplication
across the library.
"""

import asyncio
from typing import Optional, TypeVar, Protocol, Type, Tuple, Any
from abc import ABC, abstractmethod

from .exceptions import ConnectionError


T = TypeVar('T')


class AsyncCloseable(ABC):
    """
    Base class for objects that can be closed asynchronously.
    
    Provides idempotent close/shutdown functionality with proper locking.
    """
    
    def __init__(self):
        self._closed = False
        self._close_lock = asyncio.Lock()
    
    @abstractmethod
    async def _do_close(self) -> None:
        """
        Perform the actual close operation.
        
        This method should contain the actual cleanup logic.
        Subclasses must implement this method.
        """
        pass
    
    async def close(self) -> None:
        """
        Close the resource idempotently.
        
        This method ensures that the resource is only closed once,
        even if called multiple times concurrently.
        """
        async with self._close_lock:
            if not self._closed:
                self._closed = True
                await self._do_close()
    
    @property
    def is_closed(self) -> bool:
        """Check if the resource is closed."""
        return self._closed
    
    def _check_not_closed(self) -> None:
        """
        Check that the resource is not closed.
        
        Raises:
            ConnectionError: If the resource is closed.
        """
        if self._closed:
            raise ConnectionError(f"{self.__class__.__name__} is closed")


class AsyncContextManageable:
    """
    Mixin to add async context manager support.
    
    Classes using this mixin must implement an async close() method.
    """
    
    async def __aenter__(self: T) -> T:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[Any]) -> None:
        """Async context manager exit."""
        if hasattr(self, 'close'):
            await self.close()
        elif hasattr(self, 'shutdown'):
            await self.shutdown()
        else:
            raise NotImplementedError(
                f"{self.__class__.__name__} must implement close() or shutdown()"
            )


class CloseableProtocol(Protocol):
    """Protocol for objects that can be closed."""
    
    async def close(self) -> None:
        """Close the resource."""
        ...


def check_not_closed(method):
    """
    Decorator to check if a resource is closed before executing a method.
    
    The decorated class must have a _check_not_closed() method.
    """
    async def wrapper(self, *args, **kwargs):
        self._check_not_closed()
        return await method(self, *args, **kwargs)
    
    # Preserve function metadata
    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    wrapper.__annotations__ = method.__annotations__
    
    return wrapper


class ExceptionHandler:
    """
    Context manager for consistent exception handling.
    
    Usage:
        async with ExceptionHandler("Operation failed", QueryError):
            # Code that might raise exceptions
            pass
    """
    
    def __init__(self, error_message: str, wrapper_exception: Type[Exception], 
                 reraise_exceptions: Optional[Tuple[Type[Exception], ...]] = None):
        """
        Initialize the exception handler.
        
        Args:
            error_message: Message to include in wrapped exceptions
            wrapper_exception: Exception class to wrap unexpected errors
            reraise_exceptions: Tuple of exceptions to reraise without wrapping
        """
        self.error_message = error_message
        self.wrapper_exception = wrapper_exception
        self.reraise_exceptions = reraise_exceptions or ()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[Any]) -> Optional[bool]:
        if exc_type is None:
            return False
        
        # Reraise specific exceptions as-is
        if isinstance(exc_val, self.reraise_exceptions):
            return False
        
        # Wrap other exceptions
        if not isinstance(exc_val, self.wrapper_exception):
            raise self.wrapper_exception(
                f"{self.error_message}: {str(exc_val)}", 
                cause=exc_val
            )
        
        return False