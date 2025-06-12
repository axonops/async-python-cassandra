"""
Base classes and mixins for async-cassandra.

This module provides common functionality to reduce code duplication
across the library.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from .exceptions import ConnectionError

T = TypeVar("T")


class AsyncCloseable(ABC):
    """
    Base class for objects that can be closed asynchronously.

    Provides idempotent close/shutdown functionality with proper locking.
    """

    def __init__(self) -> None:
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

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()  # type: ignore
