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

Always use parameterized queries to prevent CQL injection:

```python
# Using positional parameters
result = await session.execute(
    "SELECT * FROM users WHERE id = ?",
    [user_id]
)

# Using named parameters
result = await session.execute(
    "SELECT * FROM users WHERE id = :user_id",
    {'user_id': user_id}
)
```

### Insert, Update, Delete

```python
# Insert
await session.execute(
    "INSERT INTO users (id, name, email) VALUES (?, ?, ?)",
    [user_id, name, email]
)

# Update
await session.execute(
    "UPDATE users SET email = ? WHERE id = ?",
    [new_email, user_id]
)

# Delete
await session.execute(
    "DELETE FROM users WHERE id = ?",
    [user_id]
)
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

# Create a batch
batch = BatchStatement(batch_type=BatchType.UNLOGGED)

# Add multiple statements
for user in users_to_insert:
    batch.add(
        "INSERT INTO users (id, name, email) VALUES (?, ?, ?)",
        [user['id'], user['name'], user['email']]
    )

# Execute the batch
await session.execute_batch(batch)
```

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