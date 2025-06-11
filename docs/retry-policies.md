# Retry Policies in async-cassandra

## Why Do We Have Our Own Retry Policy?

You might wonder why async-cassandra implements its own retry policy when the cassandra-driver already provides several. The answer is **safety and correctness** - our retry policy adds critical idempotency checking that prevents data corruption.

## The Problem with Default Retry Policies

The cassandra-driver provides these retry policies:
- `RetryPolicy` - The default, but it has limitations
- `FallthroughRetryPolicy` - Never retries anything
- `DowngradingConsistencyRetryPolicy` - Deprecated, downgrades consistency

**None of these check whether a query is idempotent before retrying writes!**

### What's the Risk?

Without idempotency checking, retrying write operations can cause:

1. **Duplicate Inserts**
   ```python
   # If this times out and gets retried...
   INSERT INTO users (id, email) VALUES (123, 'user@example.com')
   # You could end up with duplicate records!
   ```

2. **Multiple Counter Updates**
   ```python
   # If this times out and gets retried...
   UPDATE stats SET views = views + 1 WHERE page_id = 456
   # The counter could be incremented multiple times!
   ```

3. **Data Corruption**
   ```python
   # If this times out and gets retried...
   UPDATE accounts SET balance = balance - 100 WHERE id = 789
   # The account could be debited multiple times!
   ```

## How async-cassandra's Retry Policy Solves This

Our `AsyncRetryPolicy` adds a critical safety check:

```python
# From async_cassandra/retry_policy.py
def on_write_timeout(self, query, ...):
    # CRITICAL: Only retry if query is explicitly marked as idempotent
    if getattr(query, "is_idempotent", None) is not True:
        # Query is not idempotent - do not retry
        return self.RETHROW, None
```

This means:
- **Safe writes are retried** - If you mark a query as idempotent, it will be retried on timeout
- **Unsafe writes are not retried** - Non-idempotent writes fail fast to prevent corruption
- **Explicit opt-in** - You must explicitly mark queries as idempotent

## How to Use It

### Marking Queries as Idempotent

```python
from cassandra.query import SimpleStatement

# Safe to retry - using IF NOT EXISTS makes it idempotent
stmt = SimpleStatement(
    "INSERT INTO users (id, email) VALUES (?, ?) IF NOT EXISTS",
    is_idempotent=True
)
result = await session.execute(stmt, [123, 'user@example.com'])

# Safe to retry - setting a value is idempotent
stmt = SimpleStatement(
    "UPDATE users SET last_login = ? WHERE id = ?",
    is_idempotent=True
)
result = await session.execute(stmt, [datetime.now(), 123])

# NOT safe to retry - incrementing is not idempotent
stmt = SimpleStatement(
    "UPDATE counters SET views = views + 1 WHERE page_id = ?"
    # Note: is_idempotent is NOT set (defaults to False)
)
result = await session.execute(stmt, [456])
```

### Using the Retry Policy

The `AsyncRetryPolicy` is automatically used by default:

```python
from async_cassandra import AsyncCluster

# Uses AsyncRetryPolicy automatically
cluster = AsyncCluster(['localhost'])
session = await cluster.connect()

# Or specify explicitly with custom settings
from async_cassandra.retry_policy import AsyncRetryPolicy

cluster = AsyncCluster(
    ['localhost'],
    retry_policy=AsyncRetryPolicy(max_retries=5)
)
```

## Comparison with Driver's Default Behavior

| Scenario | Driver's RetryPolicy | async-cassandra's AsyncRetryPolicy |
|----------|---------------------|-----------------------------------|
| Read timeout | Retries if data retrieved | Same, with max retry limit |
| Write timeout (BATCH_LOG) | Always retries | Only if marked idempotent |
| Write timeout (SIMPLE/BATCH) | Never retries | Only if marked idempotent |
| Unavailable | Retries with next host | Same, with max retry limit |

## Best Practices

1. **Always consider idempotency** - Think about whether your write can be safely retried
2. **Use IF NOT EXISTS/IF EXISTS** - These make INSERTs and DELETEs idempotent
3. **Set absolute values, not increments** - `SET count = 5` is idempotent, `SET count = count + 1` is not
4. **Use prepared statements** - They can be marked as idempotent once and reused

## Example: Idempotent vs Non-Idempotent

```python
# ✅ IDEMPOTENT - Safe to retry
async def create_user_idempotent(user_id, email):
    stmt = SimpleStatement(
        "INSERT INTO users (id, email) VALUES (?, ?) IF NOT EXISTS",
        is_idempotent=True
    )
    return await session.execute(stmt, [user_id, email])

# ❌ NOT IDEMPOTENT - Could create duplicates if retried
async def create_user_unsafe(user_id, email):
    # Without IF NOT EXISTS, retrying could insert multiple times
    return await session.execute(
        "INSERT INTO users (id, email) VALUES (?, ?)",
        [user_id, email]
    )

# ✅ IDEMPOTENT - Setting to absolute value
async def update_user_status_idempotent(user_id, status):
    stmt = SimpleStatement(
        "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
        is_idempotent=True
    )
    return await session.execute(stmt, [status, datetime.now(), user_id])

# ❌ NOT IDEMPOTENT - Incrementing counter
async def increment_login_count(user_id):
    # This MUST NOT be retried - could increment multiple times
    return await session.execute(
        "UPDATE users SET login_count = login_count + 1 WHERE id = ?",
        [user_id]
    )
```

## Summary

async-cassandra's retry policy is not just a wrapper - it's a safety feature that:
- Prevents data corruption from retry-related issues
- Requires explicit marking of idempotent queries
- Maintains the benefits of automatic retries for safe operations
- Protects against the most common Cassandra anti-patterns

This is why we "reinvented" the retry policy - to provide a safer default that prevents common but serious data integrity issues.