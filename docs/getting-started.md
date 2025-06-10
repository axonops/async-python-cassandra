# Getting Started with async-cassandra

This guide will help you get up and running with async-cassandra quickly.

## Table of Contents

- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [Connection Management](#connection-management)
- [Executing Queries](#executing-queries)
- [Prepared Statements](#prepared-statements)
- [Error Handling](#error-handling)
- [Next Steps](#next-steps)

## Installation

### Prerequisites

- Python 3.8 or higher
- Apache Cassandra 2.1+ (recommended: 5.0+)
- An async framework (FastAPI, aiohttp, etc.) - optional but recommended

### Install from PyPI

```bash
pip install async-cassandra
```

### Install from Source

```bash
git clone https://github.com/axonops/async-python-cassandra.git
cd async-python-cassandra
pip install -e .
```

## Basic Usage

Here's a minimal example to get you started:

```python
import asyncio
from async_cassandra import AsyncCluster

async def main():
    # Create a cluster connection
    cluster = AsyncCluster(['localhost'])
    
    # Connect to a keyspace (or None for no keyspace)
    session = await cluster.connect()
    
    # Execute a simple query
    result = await session.execute("SELECT release_version FROM system.local")
    row = result.one()
    print(f"Cassandra version: {row.release_version}")
    
    # Clean up
    await session.close()
    await cluster.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

## Connection Management

### Basic Connection

```python
from async_cassandra import AsyncCluster

# Connect to a single node
cluster = AsyncCluster(['localhost'])

# Connect to multiple nodes
cluster = AsyncCluster(['node1', 'node2', 'node3'])

# With custom port
cluster = AsyncCluster(['localhost'], port=9043)
```

### Authentication

```python
from async_cassandra import AsyncCluster

cluster = AsyncCluster.create_with_auth(
    contact_points=['localhost'],
    username='cassandra',
    password='cassandra'
)
```

### Using Context Managers

The recommended way to manage connections is with async context managers:

```python
from async_cassandra import AsyncCluster

async def main():
    async with AsyncCluster(['localhost']) as cluster:
        async with await cluster.connect('my_keyspace') as session:
            # Your queries here
            result = await session.execute("SELECT * FROM users")
            # Session and cluster are automatically closed
```

## Executing Queries

### Simple Queries

```python
# Execute a simple SELECT
result = await session.execute("SELECT * FROM users")

# Iterate through results
async for row in result:
    print(f"User: {row.name}, Email: {row.email}")

# Get all rows at once
all_rows = result.all()

# Get first row only
first_row = result.one()
```

### Parameterized Queries

**Important**: The Cassandra Python driver requires prepared statements for parameterized queries. Direct parameterized queries with placeholders will fail.

```python
# WRONG - This will fail!
# result = await session.execute(
#     "SELECT * FROM users WHERE id = ?",
#     [user_id]
# )

# CORRECT - Use prepared statements
prepared = await session.prepare("SELECT * FROM users WHERE id = ?")
result = await session.execute(prepared, [user_id])

# For one-time queries, you can prepare and execute in sequence
prepared = await session.prepare("SELECT * FROM users WHERE email = ?")
result = await session.execute(prepared, ["user@example.com"])
```

### Insert, Update, Delete

```python
# Insert - must use prepared statement
insert_stmt = await session.prepare(
    "INSERT INTO users (id, name, email) VALUES (?, ?, ?)"
)
await session.execute(insert_stmt, [user_id, name, email])

# Update - must use prepared statement
update_stmt = await session.prepare(
    "UPDATE users SET email = ? WHERE id = ?"
)
await session.execute(update_stmt, [new_email, user_id])

# Delete - must use prepared statement
delete_stmt = await session.prepare(
    "DELETE FROM users WHERE id = ?"
)
await session.execute(delete_stmt, [user_id])

# For non-parameterized queries, you can execute directly
await session.execute("TRUNCATE users")  # No parameters, works directly
```

## Prepared Statements

Prepared statements improve performance for frequently executed queries:

```python
# Prepare the statement once
prepared = await session.prepare(
    "SELECT * FROM users WHERE id = ?"
)

# Execute it multiple times
for user_id in user_ids:
    result = await session.execute(prepared, [user_id])
    user = result.one()
    if user:
        print(f"Found user: {user.name}")
```

### Batch Operations

```python
from cassandra.query import BatchStatement, BatchType

# Prepare the statement first
insert_stmt = await session.prepare(
    "INSERT INTO users (id, name, email) VALUES (?, ?, ?)"
)

# Create a batch
batch = BatchStatement(batch_type=BatchType.UNLOGGED)

# Add multiple prepared statements to the batch
for user in users_to_insert:
    batch.add(insert_stmt, [user['id'], user['name'], user['email']])

# Execute the batch
await session.execute(batch)  # Note: execute, not execute_batch
```

## Idempotency and Retries

When using async-cassandra, it's important to understand idempotency for safe retries:

```python
from cassandra.query import SimpleStatement

# Mark queries as idempotent when they can be safely retried
# SELECT queries are always safe to retry
select_stmt = SimpleStatement(
    "SELECT * FROM users WHERE id = ?",
    is_idempotent=True  # Safe to retry
)

# INSERT with IF NOT EXISTS is idempotent
insert_stmt = SimpleStatement(
    "INSERT INTO users (id, name) VALUES (?, ?) IF NOT EXISTS",
    is_idempotent=True  # Safe to retry
)

# Regular INSERT without IF NOT EXISTS - NOT idempotent
insert_stmt = SimpleStatement(
    "INSERT INTO users (id, name) VALUES (?, ?)",
    is_idempotent=False  # Could create duplicates if retried
)

# UPDATE with increment - NOT idempotent
update_stmt = SimpleStatement(
    "UPDATE counters SET count = count + 1 WHERE id = ?",
    is_idempotent=False  # Would increment multiple times if retried
)

# DELETE is usually idempotent
delete_stmt = SimpleStatement(
    "DELETE FROM users WHERE id = ?",
    is_idempotent=True  # Safe to retry
)
```

**Important**: The retry policy will only retry write operations that are marked as idempotent to prevent data corruption.

## Error Handling

async-cassandra provides specific exception types for different error scenarios:

```python
from async_cassandra import (
    ConnectionError,
    QueryError,
    AsyncCassandraError
)

try:
    result = await session.execute("SELECT * FROM users")
except ConnectionError as e:
    # Handle connection issues
    print(f"Connection failed: {e}")
except QueryError as e:
    # Handle query execution errors
    print(f"Query failed: {e}")
except AsyncCassandraError as e:
    # Handle any async-cassandra error
    print(f"Operation failed: {e}")
```

### Handling Timeouts

```python
from cassandra.cluster import OperationTimedOut

try:
    result = await session.execute(
        "SELECT * FROM large_table",
        timeout=30.0  # 30 second timeout
    )
except OperationTimedOut:
    print("Query timed out")
```

## Next Steps

Now that you understand the basics:

1. **Learn about performance optimization**: Read our [Performance Guide](performance.md)
2. **Understand connection pooling**: Check the [Connection Pooling Guide](connection-pooling.md)
3. **Explore advanced features**: See the [API Reference](api.md)
4. **Build a real application**: Look at our [FastAPI Example](../examples/fastapi_app/README.md)

## Need Help?

- **Issues**: Report bugs on [GitHub](https://github.com/axonops/async-python-cassandra/issues)
- **Questions**: Contact us at community@axonops.com
- **Learn more**: Visit [AxonOps](https://axonops.com)