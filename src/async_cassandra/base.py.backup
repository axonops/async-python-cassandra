"""
Base classes and mixins for async-cassandra.

This module provides common functionality to reduce code duplication
across the library.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional, TypeVar

from .exceptions import ConnectionError

T = TypeVar("T")
TResult = TypeVar("TResult")


class AsyncCloseable(ABC):
    """
    Base class for objects that can be closed asynchronously.

    Provides idempotent close/shutdown functionality with proper locking.
    """

    def __init__(self) -> None:
        self._closed = False
        self._close_lock = asyncio.Lock()
        # Lock for atomic operations that need to check closed state
        self._operation_lock = asyncio.Lock()
        # Track active operations to ensure clean shutdown
        self._active_operations = 0
        self._close_event: Optional[asyncio.Event] = None

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
                # Mark as closed to prevent new operations
                async with self._operation_lock:
                    self._closed = True
                    # Wait for active operations to complete if any
                    if self._active_operations > 0:
                        self._close_event = asyncio.Event()

                # Wait outside the lock to avoid blocking new checks
                if self._close_event:
                    await self._close_event.wait()

                # Now safe to close
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

    async def _execute_if_not_closed(self, operation: Callable[[], Awaitable[TResult]]) -> TResult:
        """
        Execute an operation atomically with closed state check.

        This method ensures that the closed state check and operation
        start are atomic, preventing TOCTOU race conditions while
        minimizing lock contention.

        Args:
            operation: Async callable to execute if not closed.

        Returns:
            Result of the operation.

        Raises:
            ConnectionError: If the resource is closed.
        """
        # Only hold the lock briefly to check state and increment counter
        async with self._operation_lock:
            if self._closed:
                raise ConnectionError(f"{self.__class__.__name__} is closed")
            # Increment active operations counter to prevent close during execution
            if not hasattr(self, "_active_operations"):
                self._active_operations = 0
            self._active_operations += 1

        try:
            # Execute operation outside the lock for better concurrency
            return await operation()
        finally:
            # Decrement counter when done
            async with self._operation_lock:
                self._active_operations -= 1
                # Signal close() if it's waiting for operations to complete
                if self._active_operations == 0 and self._close_event is not None:
                    self._close_event.set()


class AsyncContextManageable:
    """
    Mixin to add async context manager support.

    Classes using this mixin must implement an async close() method.
    """

    async def __aenter__(self: T) -> T:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()  # type: ignore
