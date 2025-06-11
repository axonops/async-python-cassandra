# async-python-cassandra: What It Does and Doesn't Do

## What This Wrapper Actually Does

### 1. Future Bridging
The wrapper's primary function is to bridge between cassandra-driver's `ResponseFuture` and asyncio's `Future`:

```python
# In AsyncResultHandler
def __init__(self, response_future: ResponseFuture):
    self._loop = asyncio.get_running_loop()
    self._future = self._loop.create_future()  # Create asyncio.Future
    
    # Bridge callbacks from ResponseFuture to asyncio.Future
    self.response_future.add_callbacks(
        callback=self._handle_page, 
        errback=self._handle_error
    )

def _handle_page(self, rows):
    # Called in thread pool, need thread-safe call
    self._loop.call_soon_threadsafe(
        self._future.set_result, 
        AsyncResultSet(self.rows)
    )
```

### 2. Thread-Safe Event Loop Integration
Uses `call_soon_threadsafe` because callbacks run in driver's thread pool:

```python
def _handle_error(self, exc: Exception) -> None:
    """Handle query execution error."""
    # This runs in driver's thread, not event loop thread
    self._loop.call_soon_threadsafe(self._future.set_exception, exc)
```

### 3. Async/Await Syntax Sugar
Provides clean async/await interface:

```python
# Instead of:
future = session.execute_async(query)
future.add_callbacks(on_success, on_error)

# You can write:
result = await session.execute(query)
```

## What Actually Happens Under the Hood

When you call `await session.execute(query)`:

```
1. async def execute(query):
    │
    ├─▶ response_future = session.execute_async(query)
    │   │
    │   └─▶ Driver creates ResponseFuture
    │       └─▶ Submits work to ThreadPoolExecutor
    │           └─▶ Thread sends query (blocking I/O)
    │
    ├─▶ handler = AsyncResultHandler(response_future)
    │   │
    │   ├─▶ Creates asyncio.Future
    │   └─▶ Registers callbacks on ResponseFuture
    │
    └─▶ return await handler.get_result()
        │
        └─▶ Waits on asyncio.Future (non-blocking to event loop)
            │
            └─▶ When driver thread completes:
                └─▶ Callback uses call_soon_threadsafe
                    └─▶ Sets asyncio.Future result
                        └─▶ Coroutine resumes
```

## Critical Limitations

### 1. Still Thread-Based I/O
```python
# This is what happens in the driver:
def _send_query_in_thread():
    connection = pool.borrow_connection()  # May block thread
    connection.send(query_bytes)           # Blocks thread
    response = connection.recv()           # Blocks thread
    return response

# The wrapper cannot change this!
```

### 2. Thread Pool Bottleneck
- Default: 2-4 executor threads
- Each blocking I/O operation ties up a thread
- Under load, queries queue up waiting for threads

### 3. Double Future Overhead
```python
# You're managing two futures:
ResponseFuture (threading-based) ─bridge─> asyncio.Future
     │                                          │
     └─ Uses threading.Event                    └─ Uses event loop
```

### 4. No Connection-Level Async
- Cannot have truly async connection pooling
- Cannot multiplex queries on single connection
- Each query still needs dedicated thread time

## Performance Implications

### Memory Overhead
```
Per Connection:
- Read thread: ~1MB
- Write thread: ~1MB
- Socket buffers: ~64KB

Per Query:
- ResponseFuture object
- asyncio.Future object
- Bridge callback overhead
```

### CPU Overhead
```
1. Context switch: event loop → thread pool
2. Execute blocking I/O in thread
3. Context switch: thread pool → event loop
4. Plus GIL contention between threads
```

### Concurrency Limits
```python
# True async (e.g., aiohttp):
# Can handle 10,000+ concurrent requests with single thread

# cassandra-driver + wrapper:
# Limited by thread pool size (default 2-4 threads)
# Each thread handles 1 query at a time
# Max real concurrency = thread pool size
```

## What the Wrapper Cannot Fix

### 1. Cannot Make I/O Non-Blocking
```python
# Driver does this (blocking):
socket.send(data)  # Blocks until all data sent
socket.recv(size)  # Blocks until data arrives

# Cannot be changed to this without rewriting driver:
await socket.send(data)  # Would yield to event loop
await socket.recv(size)  # Would yield to event loop
```

### 2. Cannot Eliminate Threads
The driver's architecture requires threads for:
- Connection read loops
- Connection write loops
- Request execution
- Heartbeat monitoring
- Event processing

### 3. Cannot Improve Protocol Efficiency
- Still one thread per active query
- No query pipelining
- No multiplexing multiple queries per connection

## When the Wrapper Helps

### ✅ Good Use Cases
1. **Existing Async Codebase**: Integrating with async web frameworks
2. **Simplified Error Handling**: Async context managers and exception handling
3. **Cleaner Code**: Avoiding callback hell
4. **Streaming Large Results**: Memory-efficient async iteration

### ❌ Poor Use Cases
1. **High Concurrency Requirements**: Need 1000s of concurrent queries
2. **Low Latency Requirements**: Every microsecond counts
3. **Resource Constrained**: Limited CPU/memory
4. **True Async Performance**: Expecting asyncio-level efficiency

## Real-World Example

```python
# This looks async:
async def handle_request():
    result = await session.execute("SELECT * FROM users WHERE id = ?", [user_id])
    return result.one()

# But actually does this:
# 1. Event loop schedules coroutine
# 2. Coroutine submits to thread pool
# 3. Thread blocks on I/O
# 4. Thread completes, signals event loop
# 5. Event loop resumes coroutine

# Compare to true async (hypothetical):
# 1. Event loop schedules coroutine
# 2. Starts non-blocking I/O
# 3. Yields to other coroutines
# 4. I/O completes, event loop resumes
# (No threads, no blocking, no context switches)
```

## Conclusion

The async-python-cassandra wrapper provides **developer convenience** and **code compatibility** with async Python applications, but it **cannot overcome the fundamental thread-based architecture** of the underlying driver. 

Users should understand that they're getting:
- ✅ Async/await syntax
- ✅ Integration with async frameworks
- ✅ Cleaner error handling
- ❌ NOT true async I/O performance
- ❌ NOT unlimited concurrency
- ❌ NOT single-threaded efficiency

For applications requiring true async Cassandra access with maximum performance, a ground-up async driver implementation would be needed.