# Getting Started with async-cassandra

This guide walks you through the basics of using async-cassandra. For complete API documentation, see the [API Reference](api.md).

## Installation

```bash
pip install async-cassandra
```

## Quick Start

### Your First async-cassandra Program

This example shows the minimum code needed to connect to Cassandra and run a query:

```python
import asyncio
from async_cassandra import AsyncCluster

async def main():
    # 1. Create a cluster object (doesn't connect yet)
    cluster = AsyncCluster(['localhost'])
    
    # 2. Connect and get a session (this is where connection happens)
    session = await cluster.connect('my_keyspace')
    
    # 3. Execute a query (waits for results without blocking)
    result = await session.execute("SELECT * FROM users LIMIT 10")
    
    # 4. Process results (rows are like dictionaries)
    for row in result:
        print(f"User: {row.name}, Email: {row.email}")
    
    # 5. Clean up (IMPORTANT: always close connections)
    await cluster.shutdown()

# Run the async function
asyncio.run(main())
```

### What's Different from Regular Cassandra Driver?

1. **Import AsyncCluster instead of Cluster**
2. **Use `await` for all database operations**
3. **Wrap your code in an async function**
4. **No blocking** - your app stays responsive

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

#### Why Use Prepared Statements?

Prepared statements are **required** for parameterized queries in async-cassandra. They provide:

1. **Security** - Prevents CQL injection attacks (like SQL injection)
2. **Performance** - Query is parsed once, executed many times
3. **Type Safety** - Cassandra validates parameter types

#### How They Work

```python
# ❌ This will NOT work - direct parameters not supported
await session.execute("SELECT * FROM users WHERE id = ?", [user_id])

# ✅ This works - prepare first, then execute
prepared = await session.prepare("SELECT * FROM users WHERE id = ?")
result = await session.execute(prepared, [user_id])
```

#### Example Usage

```python
# Prepare once (usually at startup)
user_query = await session.prepare("SELECT * FROM users WHERE id = ?")
insert_stmt = await session.prepare(
    "INSERT INTO users (id, name, email) VALUES (?, ?, ?)"
)

# Execute many times with different parameters
for user_id in user_ids:
    result = await session.execute(user_query, [user_id])
    user = result.one()
    print(user)

# Insert new users
await session.execute(insert_stmt, [uuid.uuid4(), "Alice", "alice@example.com"])
```

### Error Handling

#### Why Proper Error Handling Matters

In distributed systems like Cassandra, failures are normal, not exceptions. Network issues, node failures, and timeouts happen regularly. Your application needs to handle these gracefully.

#### Common Error Types

```python
from async_cassandra import ConnectionError, QueryError

try:
    result = await session.execute("SELECT * FROM users")
except ConnectionError as e:
    # Happens when: Can't reach Cassandra, node is down, network issues
    print(f"Connection failed: {e}")
    # What to do: Retry, use a different node, alert ops team
    
except QueryError as e:
    # Happens when: Bad CQL syntax, table doesn't exist, permissions issue
    print(f"Query failed: {e}")
    # What to do: Fix the query, check schema, verify permissions
```

#### Real-World Error Handling

```python
import asyncio
from async_cassandra import ConnectionError, QueryError

async def get_user_with_retry(session, user_id, max_retries=3):
    """Get user with automatic retry on connection errors."""
    for attempt in range(max_retries):
        try:
            prepared = await session.prepare("SELECT * FROM users WHERE id = ?")
            result = await session.execute(prepared, [user_id])
            return result.one()
            
        except ConnectionError as e:
            if attempt == max_retries - 1:
                # Final attempt failed, re-raise
                raise
            # Wait before retry (exponential backoff)
            wait_time = 2 ** attempt
            print(f"Connection failed, retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            
        except QueryError as e:
            # Don't retry query errors - they won't fix themselves
            print(f"Query error (not retrying): {e}")
            raise
```

### Streaming Large Result Sets

#### The Memory Problem with Large Queries

When you query millions of rows, loading them all into memory will crash your application:

```python
# ❌ BAD: This loads ALL rows into memory at once
result = await session.execute("SELECT * FROM billion_row_table")
for row in result:  # 💥 OutOfMemoryError
    process(row)
```

#### The Streaming Solution

Streaming fetches rows in small batches (pages) as you need them:

```python
from async_cassandra.streaming import StreamConfig

# Configure streaming with page size
config = StreamConfig(
    fetch_size=1000  # Fetch 1000 rows at a time
)

# Execute with streaming
result = await session.execute_stream(
    "SELECT * FROM billion_row_table",
    stream_config=config
)

# Process rows one at a time - only 1000 in memory at once
async for row in result:
    await process_row(row)
    # Previous rows are garbage collected
```

#### When to Use Streaming

- ✅ Exporting data
- ✅ ETL processes
- ✅ Generating reports from large datasets
- ✅ Any query returning thousands+ of rows
- ❌ Don't use for small queries (adds overhead)

## Integration with Web Frameworks

### Why async-cassandra with FastAPI?

FastAPI is an async web framework. If you use the regular Cassandra driver, it will **block your entire web server** during database queries. This means your API can't handle other requests while waiting for Cassandra to respond.

### FastAPI Example

#### The Setup

```python
from fastapi import FastAPI, HTTPException
from async_cassandra import AsyncCluster
import uuid

app = FastAPI()

# Global variables for cluster and session
cluster = None
session = None
prepared_statements = {}

@app.on_event("startup")
async def startup():
    """Initialize Cassandra connection when server starts."""
    global cluster, session, prepared_statements
    
    # Create cluster connection
    cluster = AsyncCluster(['localhost'])
    session = await cluster.connect('my_keyspace')
    
    # Prepare statements once at startup (more efficient)
    prepared_statements['get_user'] = await session.prepare(
        "SELECT * FROM users WHERE id = ?"
    )
    prepared_statements['create_user'] = await session.prepare(
        "INSERT INTO users (id, name, email) VALUES (?, ?, ?)"
    )

@app.on_event("shutdown")
async def shutdown():
    """Clean up when server stops."""
    if cluster:
        await cluster.shutdown()
```

#### API Endpoints

```python
@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get a user by ID."""
    try:
        # Convert string to UUID
        user_uuid = uuid.UUID(user_id)
        
        # Execute prepared statement
        result = await session.execute(
            prepared_statements['get_user'], 
            [user_uuid]
        )
        
        user = result.one()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users")
async def create_user(name: str, email: str):
    """Create a new user."""
    user_id = uuid.uuid4()
    
    await session.execute(
        prepared_statements['create_user'],
        [user_id, name, email]
    )
    
    return {"id": str(user_id), "name": name, "email": email}
```

#### Why This Pattern?

1. **Global session**: Creating connections is expensive - do it once at startup
2. **Prepared statements at startup**: Better performance, prepare once, use many times
3. **Proper error handling**: Convert Cassandra errors to HTTP errors
4. **UUID handling**: Cassandra uses UUIDs, web uses strings - convert properly

## Next Steps

- [API Reference](api.md) - Complete API documentation
- [Connection Pooling](connection-pooling.md) - Understanding connection behavior
- [Streaming](streaming.md) - Handling large result sets
- [Performance](performance.md) - Optimization tips
- [FastAPI Example](../examples/fastapi_app/) - Full production example