# Error Handling Analysis for async-python-cassandra

## Summary

After analyzing the error handling implementation in async-python-cassandra, I've identified several potential issues and edge cases that could cause problems in production environments.

## Key Findings

### 1. **Race Condition in Result Handler Callbacks**

**Issue**: In `result.py`, the `_handle_page` and `_handle_error` callbacks use `call_soon_threadsafe` to set futures from potentially different threads. However, there's no synchronization between checking `has_more_pages` and calling `start_fetching_next_page()`.

```python
# In AsyncResultHandler._handle_page
if self.response_future.has_more_pages:
    self.response_future.start_fetching_next_page()  # Race condition here
else:
    # All pages fetched, set result
    self._loop.call_soon_threadsafe(self._future.set_result, AsyncResultSet(self.rows))
```

**Risk**: If the cassandra driver calls the callback from multiple threads, we could have multiple threads trying to fetch the next page simultaneously, potentially causing duplicate data or crashes.

### 2. **Memory Leak in Streaming Error Scenarios**

**Issue**: In `streaming.py`, when an error occurs, the `_error` is stored but the `_current_page` is not cleared. If the error happens after fetching a large page, that memory is retained.

```python
def _handle_error(self, exc: Exception) -> None:
    """Handle query execution error."""
    self._error = exc
    self._exhausted = True
    # _current_page is not cleared here!
    self._loop.call_soon_threadsafe(self._page_ready.set)
```

**Risk**: For large result sets, this could cause significant memory leaks if errors occur during streaming.

### 3. **Inconsistent Error Wrapping**

**Issue**: In `session.py`, the `execute()` method doesn't wrap Cassandra exceptions, but `execute_stream()` does wrap them in QueryError:

```python
# execute() - doesn't wrap Cassandra exceptions
except (InvalidRequest, Unavailable, ReadTimeout, WriteTimeout, OperationTimedOut) as e:
    # Re-raise Cassandra exceptions without wrapping
    error_type = type(e).__name__
    raise

# execute_stream() - wraps Cassandra exceptions
except (InvalidRequest, Unavailable, ReadTimeout, WriteTimeout, OperationTimedOut) as e:
    raise QueryError(f"Streaming query execution failed: {str(e)}") from e
```

**Risk**: This inconsistency makes error handling unpredictable for users. They need different exception handling logic for regular vs streaming queries.

### 4. **Missing NoHostAvailable Exception Handling**

**Issue**: The code handles specific Cassandra exceptions but doesn't handle `NoHostAvailable`, which is imported in tests but not in the main code.

**Risk**: When all Cassandra nodes are down, the exception will be wrapped as a generic QueryError, losing important connection failure context.

### 5. **Event Loop Reference Issues**

**Issue**: Both `AsyncResultHandler` and `AsyncStreamingResultSet` store a reference to the event loop at initialization:

```python
self._loop = asyncio.get_running_loop()
```

**Risk**: If the handler is created in one event loop but used in another (e.g., in multi-threaded scenarios), this will cause crashes. The event loop reference could also prevent garbage collection.

### 6. **No Timeout on Future.await**

**Issue**: In `AsyncResultHandler.get_result()`, we await the future without any timeout:

```python
async def get_result(self) -> "AsyncResultSet":
    result = await self._future  # No timeout!
    return result
```

**Risk**: If the cassandra driver never calls the callbacks (due to a bug or network issue), this will hang forever, even if the user specified a timeout for the query.

### 7. **Thread Safety in Streaming Page Callback**

**Issue**: The streaming result set's page callback can be called from user code and modify internal state:

```python
if self.config.page_callback:
    try:
        self.config.page_callback(self._page_number, len(rows))
    except Exception as e:
        logger.warning(f"Page callback error: {e}")
        # Continues execution despite callback error
```

**Risk**: If the callback raises an exception, the warning is logged but execution continues, which might leave the streaming in an inconsistent state.

### 8. **Cleanup Not Guaranteed in Error Cases**

**Issue**: There's no cleanup mechanism for pending futures or callbacks when an error occurs. The ResponseFuture from cassandra-driver might still hold references to our callbacks.

**Risk**: Memory leaks and potential callback invocations after the async wrapper objects have been garbage collected.

### 9. **Execute Method Finally Block with Async**

**Issue**: In the `execute` method's finally block, metrics are recorded asynchronously:

```python
finally:
    if self._metrics:
        await self._metrics.record_query_metrics(...)
```

**Risk**: If the metrics recording fails or hangs, it could prevent proper exception propagation or cause the method to hang even after a timeout.

### 10. **Race Condition in AsyncCloseable**

**Issue**: Although `AsyncCloseable` uses a lock, there's still a TOCTOU (Time-of-Check-Time-of-Use) issue with the `is_closed` property:

```python
if self.is_closed:  # Check
    raise ConnectionError("Session is closed")
# ... other code ...
# Session could be closed here by another coroutine
response_future = self._session.execute_async(...)  # Use
```

## Recommendations

1. **Add thread-safe synchronization** for multi-page result handling
2. **Clear page data on errors** in streaming to prevent memory leaks  
3. **Standardize error handling** across all query methods
4. **Handle NoHostAvailable** explicitly
5. **Don't store event loop references** - use `asyncio.get_running_loop()` when needed
6. **Add configurable timeouts** for all await operations
7. **Make page callbacks async** or run them in an executor
8. **Implement proper cleanup** with weakref callbacks or context managers
9. **Make metrics recording fire-and-forget** or add timeout
10. **Use read-write locks** for better is_closed checking

## Testing Recommendations

1. Add tests for concurrent page fetching scenarios
2. Test memory usage during streaming errors
3. Add tests for all Cassandra exception types
4. Test event loop switching scenarios
5. Add timeout tests for hung futures
6. Test cleanup in error scenarios
7. Add stress tests for race conditions