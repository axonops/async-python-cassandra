# API Reference

## Table of Contents

- [AsyncCluster](#asynccluster)
- [AsyncCassandraSession](#asynccassandrasession)
- [AsyncResultSet](#asyncresultset)
- [AsyncRetryPolicy](#asyncretrypolicy)
- [Exceptions](#exceptions)

## AsyncCluster

Manages cluster configuration and connection lifecycle.

### Constructor

```python
AsyncCluster(
    contact_points: Optional[List[str]] = None,
    port: int = 9042,
    auth_provider: Optional[AuthProvider] = None,
    load_balancing_policy: Optional[LoadBalancingPolicy] = None,
    reconnection_policy: Optional[ReconnectionPolicy] = None,
    retry_policy: Optional[RetryPolicy] = None,
    ssl_context: Optional[SSLContext] = None,
    protocol_version: Optional[int] = None,
    **kwargs
)
```

**Parameters:**
- `contact_points`: List of contact points (default: ["127.0.0.1"])
- `port`: Port to connect to (default: 9042)
- `auth_provider`: Authentication provider
- `load_balancing_policy`: Load balancing policy
- `reconnection_policy`: Reconnection policy
- `retry_policy`: Retry policy (default: AsyncRetryPolicy)
- `ssl_context`: SSL context for secure connections
- `protocol_version`: CQL protocol version
- `**kwargs`: Additional cluster options

### Class Methods

#### `create_with_auth`

```python
@classmethod
def create_with_auth(
    cls,
    contact_points: List[str],
    username: str,
    password: str,
    **kwargs
) -> AsyncCluster
```

Create cluster with username/password authentication.

### Methods

#### `connect`

```python
async def connect(keyspace: Optional[str] = None) -> AsyncCassandraSession
```

Connect to the cluster and create a session.

**Example:**
```python
cluster = AsyncCluster(['localhost'])
session = await cluster.connect('my_keyspace')
```

#### `shutdown`

```python
async def shutdown() -> None
```

Shutdown the cluster and release all resources.

### Properties

- `is_closed`: Check if cluster is closed
- `metadata`: Get cluster metadata

### Context Manager

```python
async with AsyncCluster(['localhost']) as cluster:
    session = await cluster.connect()
    # Use session
```

## AsyncCassandraSession

Provides async interface for executing CQL queries.

### Methods

#### `execute`

```python
async def execute(
    query: Union[str, SimpleStatement, PreparedStatement],
    parameters: Optional[Union[List, Dict]] = None,
    trace: bool = False,
    custom_payload: Optional[Dict[str, bytes]] = None,
    timeout: Any = _NOT_SET,
    execution_profile: Any = EXEC_PROFILE_DEFAULT,
    paging_state: Optional[bytes] = None,
    host: Optional[Any] = None,
    execute_as: Optional[str] = None
) -> AsyncResultSet
```

Execute a CQL query asynchronously.

**Example:**
```python
# Simple query
result = await session.execute("SELECT * FROM users")

# Query with parameters
result = await session.execute(
    "SELECT * FROM users WHERE id = ?",
    [user_id]
)

# Query with named parameters
result = await session.execute(
    "SELECT * FROM users WHERE name = :name",
    {"name": "John"}
)
```

#### `execute_batch`

```python
async def execute_batch(
    batch_statement: BatchStatement,
    trace: bool = False,
    custom_payload: Optional[Dict[str, bytes]] = None,
    timeout: Any = _NOT_SET,
    execution_profile: Any = EXEC_PROFILE_DEFAULT
) -> AsyncResultSet
```

Execute a batch statement asynchronously.

**Example:**
```python
from cassandra.query import BatchStatement

batch = BatchStatement()
batch.add("INSERT INTO users (id, name) VALUES (?, ?)", [id1, "Alice"])
batch.add("INSERT INTO users (id, name) VALUES (?, ?)", [id2, "Bob"])

await session.execute_batch(batch)
```

#### `prepare`

```python
async def prepare(
    query: str,
    custom_payload: Optional[Dict[str, bytes]] = None
) -> PreparedStatement
```

Prepare a CQL statement asynchronously.

**Example:**
```python
prepared = await session.prepare(
    "INSERT INTO users (id, name, email) VALUES (?, ?, ?)"
)

# Use prepared statement multiple times
await session.execute(prepared, [id1, "Alice", "alice@example.com"])
await session.execute(prepared, [id2, "Bob", "bob@example.com"])
```

#### `set_keyspace`

```python
async def set_keyspace(keyspace: str) -> None
```

Set the current keyspace.

#### `close`

```python
async def close() -> None
```

Close the session and release resources.

### Properties

- `is_closed`: Check if session is closed
- `keyspace`: Get current keyspace

### Context Manager

```python
async with await cluster.connect() as session:
    result = await session.execute("SELECT * FROM users")
```

## AsyncResultSet

Represents the result of a query execution.

### Methods

#### `one`

```python
def one() -> Optional[Any]
```

Get the first row or None if empty.

**Example:**
```python
# Must prepare the statement first
stmt = await session.prepare("SELECT * FROM users WHERE id = ?")
result = await session.execute(stmt, [user_id])
user = result.one()
if user:
    print(f"Found user: {user.name}")  # Access as attribute, not dict
```

#### `all`

```python
def all() -> List[Any]
```

Get all rows as a list.

**Example:**
```python
result = await session.execute("SELECT * FROM users")
users = result.all()
for user in users:
    print(user['name'])
```

### Properties

- `rows`: Get all rows as a list

### Async Iteration

```python
result = await session.execute("SELECT * FROM users")
async for row in result:
    print(row['name'])
```

### Length

```python
result = await session.execute("SELECT * FROM users")
print(f"Found {len(result)} users")
```

## AsyncRetryPolicy

Retry policy for async operations with idempotency safety checks.

### Constructor

```python
AsyncRetryPolicy(max_retries: int = 3)
```

### Retry Behavior

- **Read Timeout**: Retries if data was retrieved or enough responses received
- **Write Timeout**: Retries for SIMPLE and BATCH writes only if marked as idempotent
- **Unavailable**: Tries next host on first attempt, then retries
- **Request Error**: Always tries next host

### Idempotency Safety

The retry policy includes critical safety checks for write operations:

```python
# Safe to retry - marked as idempotent
stmt = SimpleStatement(
    "INSERT INTO users (id, name) VALUES (?, ?) IF NOT EXISTS",
    is_idempotent=True
)

# NOT safe to retry - will not be retried
stmt = SimpleStatement(
    "INSERT INTO users (id, name) VALUES (?, ?)"
    # is_idempotent defaults to None - treated as non-idempotent
)

# Prepared statements also need explicit marking
prepared = await session.prepare(
    "DELETE FROM users WHERE id = ?"
)
prepared.is_idempotent = True  # Mark as safe to retry

# Batch statements can be marked idempotent if all operations are safe
batch = BatchStatement()
batch.is_idempotent = True  # Only if all statements in batch are idempotent
```

**Important**: Write operations (INSERT, UPDATE, DELETE) are ONLY retried if the statement is explicitly marked with `is_idempotent=True`. Statements without this attribute or with `is_idempotent=False/None` will NOT be retried. This strict policy prevents:
- Duplicate data insertions
- Multiple increments/decrements
- Unintended side effects from retrying non-idempotent operations

Note: By default, Cassandra driver statements have `is_idempotent=None`, which is treated as non-idempotent for safety.

## Exceptions

### AsyncCassandraError

Base exception for all async-cassandra errors.

```python
class AsyncCassandraError(Exception):
    cause: Optional[Exception]  # Original exception if any
```

### ConnectionError

Raised when connection to Cassandra fails.

```python
try:
    session = await cluster.connect()
except ConnectionError as e:
    print(f"Failed to connect: {e}")
```

### QueryError

Raised when a query execution fails.

```python
try:
    result = await session.execute("SELECT * FROM invalid_table")
except QueryError as e:
    print(f"Query failed: {e}")
    if e.cause:
        print(f"Caused by: {e.cause}")
```

### TimeoutError

Raised when an operation times out.

### AuthenticationError

Raised when authentication fails.

### ConfigurationError

Raised when configuration is invalid.

## Complete Example

```python
import asyncio
import uuid
from async_cassandra import AsyncCluster, AsyncCassandraSession
from async_cassandra.exceptions import QueryError, ConnectionError

async def main():
    # Create cluster with authentication
    cluster = AsyncCluster.create_with_auth(
        contact_points=['localhost'],
        username='cassandra',
        password='cassandra'
    )
    
    try:
        # Connect to cluster
        session = await cluster.connect()
        
        # Create keyspace
        await session.execute("""
            CREATE KEYSPACE IF NOT EXISTS example
            WITH REPLICATION = {
                'class': 'SimpleStrategy',
                'replication_factor': 1
            }
        """)
        
        # Use keyspace
        await session.set_keyspace('example')
        
        # Create table
        await session.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                name TEXT,
                email TEXT
            )
        """)
        
        # Prepare statement
        insert_stmt = await session.prepare(
            "INSERT INTO users (id, name, email) VALUES (?, ?, ?)"
        )
        
        # Insert data
        user_id = uuid.uuid4()
        await session.execute(
            insert_stmt,
            [user_id, "John Doe", "john@example.com"]
        )
        
        # Query data
        result = await session.execute(
            "SELECT * FROM users WHERE id = ?",
            [user_id]
        )
        
        user = result.one()
        print(f"User: {user['name']} ({user['email']})")
        
    except ConnectionError as e:
        print(f"Connection failed: {e}")
    except QueryError as e:
        print(f"Query failed: {e}")
    finally:
        await cluster.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```