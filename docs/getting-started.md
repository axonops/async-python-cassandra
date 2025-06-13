# Getting Started with async-cassandra

This guide walks you through the basics of using async-cassandra. For complete API documentation, see the [API Reference](api.md).

## Installation

```bash
pip install async-cassandra
```

## Quick Start

```python
import asyncio
from async_cassandra import AsyncCluster

async def main():
    # Connect to Cassandra
    cluster = AsyncCluster(['localhost'])
    session = await cluster.connect('my_keyspace')
    
    # Execute a query
    result = await session.execute("SELECT * FROM users LIMIT 10")
    for row in result:
        print(row)
    
    # Clean up
    await cluster.shutdown()

asyncio.run(main())
```

## Basic Usage Patterns

### Using Context Managers (Recommended)

#### What are Context Managers?

Context managers are Python's way of ensuring that resources are properly cleaned up after use. When you use `async with`, Python guarantees that cleanup code runs even if an error occurs. Think of it like a try/finally block but cleaner.

**Without context manager (manual cleanup):**
```python
cluster = AsyncCluster(['localhost'])
session = await cluster.connect('my_keyspace')
try:
    result = await session.execute("SELECT * FROM users")
finally:
    await session.close()      # You must remember this
    await cluster.shutdown()   # And this!
```

**With context manager (automatic cleanup):**
```python
async with AsyncCluster(['localhost']) as cluster:
    async with await cluster.connect('my_keyspace') as session:
        result = await session.execute("SELECT * FROM users")
        # Python automatically calls close() and shutdown() for you
```

Benefits:
- No forgotten cleanup (prevents connection leaks)
- Cleaner code
- Exception safe (cleanup happens even if query fails)

### Authentication

If your Cassandra cluster requires authentication (most production clusters do), use the `create_with_auth` helper:

```python
cluster = AsyncCluster.create_with_auth(
    contact_points=['localhost'],
    username='cassandra',
    password='cassandra'
)

# Then connect as usual
session = await cluster.connect('my_keyspace')
```

**Note:** Never hardcode credentials in your code. Use environment variables or a secrets manager:

```python
import os

cluster = AsyncCluster.create_with_auth(
    contact_points=['localhost'],
    username=os.environ['CASSANDRA_USER'],
    password=os.environ['CASSANDRA_PASS']
)
```

### Prepared Statements

For queries with parameters, always use prepared statements:

```python
# Prepare once
prepared = await session.prepare("SELECT * FROM users WHERE id = ?")

# Execute many times
for user_id in user_ids:
    result = await session.execute(prepared, [user_id])
    user = result.one()
    print(user)
```

### Error Handling

```python
from async_cassandra import ConnectionError, QueryError

try:
    await session.execute("SELECT * FROM users")
except ConnectionError as e:
    print(f"Connection failed: {e}")
except QueryError as e:
    print(f"Query failed: {e}")
```

### Streaming Large Result Sets

For memory-efficient processing of large datasets:

```python
from async_cassandra.streaming import StreamConfig

config = StreamConfig(fetch_size=1000)
result = await session.execute_stream(
    "SELECT * FROM large_table",
    stream_config=config
)

async for row in result:
    await process_row(row)
```

## Integration with Web Frameworks

### FastAPI Example

```python
from fastapi import FastAPI
from async_cassandra import AsyncCluster

app = FastAPI()
cluster = None
session = None

@app.on_event("startup")
async def startup():
    global cluster, session
    cluster = AsyncCluster(['localhost'])
    session = await cluster.connect('my_keyspace')

@app.on_event("shutdown")
async def shutdown():
    await cluster.shutdown()

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    prepared = await session.prepare("SELECT * FROM users WHERE id = ?")
    result = await session.execute(prepared, [user_id])
    return result.one()
```

## Next Steps

- [API Reference](api.md) - Complete API documentation
- [Connection Pooling](connection-pooling.md) - Understanding connection behavior
- [Streaming](streaming.md) - Handling large result sets
- [Performance](performance.md) - Optimization tips
- [FastAPI Example](../examples/fastapi_app/) - Full production example