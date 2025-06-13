# Threading Design in async-cassandra

## Overview

The async-cassandra library bridges the thread-based cassandra-driver with Python's asyncio framework. This requires careful handling of thread safety and synchronization.

## Threading Model

### 1. Driver Threads
- The cassandra-driver uses background threads for network I/O
- Callbacks (success/error) are executed in driver threads
- These threads do NOT have an asyncio event loop

### 2. Asyncio Event Loop
- User code runs in the asyncio event loop
- Futures and coroutines must be accessed from the event loop thread
- Cross-thread communication requires `call_soon_threadsafe()`

## Key Components

### AsyncResultHandler
```python
class AsyncResultHandler:
    def __init__(self, response_future):
        self._lock = threading.Lock()  # Protects shared state
        self._loop = None  # Set when get_result() is called
        
    def _handle_page(self, rows):
        # Called from driver thread
        with self._lock:
            # Update shared state
            if self._loop:
                self._loop.call_soon_threadsafe(...)
```

**Thread Safety Measures:**
- `threading.Lock()` protects shared state
- Event loop reference stored for `call_soon_threadsafe()`
- Handles early callbacks (before `get_result()` is called)

### AsyncStreamingResultSet
Similar pattern for streaming results with page-by-page fetching.

### AsyncCloseable (Base Class)
```python
class AsyncCloseable:
    def __init__(self):
        self._operation_lock = asyncio.Lock()
        self._active_operations = 0
```

**Prevents TOCTOU Race Conditions:**
- Atomic check-and-execute pattern
- Tracks active operations
- Ensures clean shutdown

## Why This Complexity?

1. **Cassandra Driver Design**: The driver is inherently thread-based
2. **Asyncio Integration**: Requires careful thread synchronization
3. **Race Condition Prevention**: Proper handling of concurrent operations
4. **Memory Safety**: Prevents leaks and ensures cleanup

## Performance Considerations

- Locks are held for minimal duration
- Operations run concurrently after state checks
- Fire-and-forget pattern for metrics
- Streaming avoids loading large datasets into memory

## Alternative Approaches Considered

1. **Queue-Based**: Could use queues for thread communication, but adds latency
2. **Thread Pool**: Could run all operations in thread pool, but loses async benefits
3. **Pure Async Driver**: Would require complete rewrite of cassandra-driver

## Conclusion

The threading complexity is a necessary trade-off for:
- Compatibility with the official cassandra-driver
- True async/await support
- Thread safety and race condition prevention
- Performance optimization

The complexity is mostly hidden from library users, who just see clean async/await APIs.