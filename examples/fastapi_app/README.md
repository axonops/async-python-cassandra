# FastAPI Example Application

This example demonstrates how to use async-cassandra with FastAPI to build a high-performance REST API backed by Cassandra.

## 🎯 Purpose

**This example serves a dual purpose:**
1. **Production Template**: A real-world example of how to integrate async-cassandra with FastAPI
2. **CI Integration Test**: This application is used in our CI/CD pipeline to validate that async-cassandra works correctly in a real async web framework environment

## Overview

The example showcases all the key features of async-cassandra:
- **Thread Safety**: Handles concurrent requests without data corruption
- **Memory Efficiency**: Streaming endpoints for large datasets
- **Error Handling**: Consistent error responses across all operations
- **Performance**: Async operations preventing event loop blocking
- **Monitoring**: Health checks and metrics endpoints
- **Production Patterns**: Proper lifecycle management, prepared statements, and error handling

## API Endpoints

### 1. Basic CRUD Operations
- `POST /users` - Create a new user
- `GET /users/{user_id}` - Get user by ID
- `PUT /users/{user_id}` - Full update of user
- `PATCH /users/{user_id}` - Partial update of user
- `DELETE /users/{user_id}` - Delete user
- `GET /users` - List users with pagination

### 2. Streaming Operations
- `GET /users/stream` - Stream large datasets efficiently
  - Query params: `limit`, `fetch_size`, `age_filter`
- `GET /users/stream/pages` - Page-by-page streaming
  - Query params: `limit`, `fetch_size`, `age_filter`

### 3. Batch Operations
- `POST /users/batch` - Create multiple users in a single batch

### 4. Performance Testing
- `GET /performance/async` - Test async performance with concurrent queries
- `GET /performance/sync` - Compare with sequential execution

### 5. Monitoring & Operations
- `GET /` - Welcome message
- `GET /health` - Health check with Cassandra connectivity test
- `GET /metrics` - Application metrics (queries, connections, etc.)
- `POST /shutdown` - Graceful shutdown
- `GET /slow_query` - Test timeout handling (5s timeout)
- `GET /long_running_query` - Test long operations (10s)

## Running the Example

### Prerequisites

1. **Cassandra** running on localhost:9042 (or use Docker):
   ```bash
   docker run -d --name cassandra-test -p 9042:9042 cassandra:4.1
   ```

2. **Python 3.12+** with dependencies:
   ```bash
   cd examples/fastapi_app
   pip install -r requirements.txt
   ```

### Start the Application

```bash
# Development mode with auto-reload
uvicorn main:app --reload

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

**Note**: Use only 1 worker to ensure proper connection management. For scaling, run multiple instances behind a load balancer.

### Environment Variables

- `CASSANDRA_HOSTS` - Comma-separated list of Cassandra hosts (default: localhost)
- `CASSANDRA_PORT` - Cassandra port (default: 9042)
- `CASSANDRA_KEYSPACE` - Keyspace name (default: test_keyspace)

Example:
```bash
export CASSANDRA_HOSTS=node1,node2,node3
export CASSANDRA_PORT=9042
export CASSANDRA_KEYSPACE=production
```

## Testing the Application

### Automated Test Suite

The test suite validates all functionality and serves as integration tests in CI:

```bash
# Run all tests
python test_fastapi_app.py

# Or with pytest
pytest test_fastapi_app.py -v
```

Tests cover:
- ✅ Thread safety under high concurrency
- ✅ Memory efficiency with streaming
- ✅ Error handling consistency
- ✅ Performance characteristics
- ✅ All endpoint functionality
- ✅ Timeout handling
- ✅ Connection lifecycle

### Manual Testing Examples

#### Create a user:
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "age": 30}'
```

#### Get a user:
```bash
# Replace with actual UUID from create response
curl http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

#### List users with pagination:
```bash
curl "http://localhost:8000/users?limit=10"
```

#### Stream large dataset:
```bash
# Stream users with age > 25, 100 rows per page
curl "http://localhost:8000/users/stream?age_filter=25&fetch_size=100&limit=10000"
```

#### Test performance:
```bash
# Run 500 concurrent queries
curl "http://localhost:8000/performance/async?requests=500"
```

#### Check health:
```bash
curl http://localhost:8000/health
```

#### View metrics:
```bash
curl http://localhost:8000/metrics
```

## Key Implementation Patterns

### Application Lifecycle Management

Uses FastAPI's lifespan context manager for proper setup/teardown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create cluster and session
    cluster = AsyncCluster([...])
    session = await cluster.connect()
    yield
    # Shutdown: Clean up connections
    await cluster.shutdown()
```

### Prepared Statements

All parameterized queries use prepared statements for security and performance:

```python
# Prepared at startup for reuse
prepared_insert = await session.prepare(
    "INSERT INTO users (id, name, email, age, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

# Used many times
await session.execute(prepared_insert, [id, name, email, age, now, now])
```

### Streaming for Large Results

Memory-efficient processing of large datasets:

```python
config = StreamConfig(fetch_size=fetch_size)
result = await session.execute_stream(query, stream_config=config)

async for row in result:
    # Process one row at a time
    # Previous rows are garbage collected
```

### Error Handling

Consistent error responses with proper HTTP status codes:

```python
try:
    user_uuid = uuid.UUID(user_id)
except ValueError:
    raise HTTPException(status_code=400, detail="Invalid UUID format")

try:
    result = await session.execute(prepared_stmt, [user_uuid])
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

### Concurrent Request Handling

Demonstrates that async-cassandra handles concurrent requests safely:

```python
# Execute many queries concurrently
tasks = [session.execute(prepared_stmt, params) for _ in range(100)]
results = await asyncio.gather(*tasks)
```

## Production Considerations

### Connection Management
- Single global session shared across all requests
- Connections established at startup, closed at shutdown
- Thread pool size configurable via `executor_threads`

### Error Recovery
- All Cassandra errors converted to appropriate HTTP errors
- Timeout handling with configurable limits
- Graceful degradation when Cassandra is unavailable

### Performance Optimization
- Prepared statements reduce parsing overhead
- Streaming prevents memory exhaustion
- Async operations prevent blocking the event loop

### Monitoring
- `/health` endpoint for load balancer health checks
- `/metrics` endpoint for application monitoring
- Structured logging throughout

### Security
- Input validation with Pydantic models
- Prepared statements prevent CQL injection
- UUID validation for all IDs

## CI/CD Integration

This example is automatically tested in our CI pipeline to ensure:
- async-cassandra integrates correctly with FastAPI
- All async operations work as expected
- No event loop blocking occurs
- Memory usage remains bounded with streaming
- Error handling works correctly

## Extending the Example

To add new features:

1. **New Endpoints**: Follow existing patterns for consistency
2. **Authentication**: Add FastAPI middleware for auth
3. **Rate Limiting**: Use FastAPI middleware or Redis
4. **Caching**: Add Redis for frequently accessed data
5. **API Versioning**: Use FastAPI's APIRouter for versioning

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure Cassandra is running: `docker ps`
   - Check connection settings in environment variables

2. **Keyspace Not Found**
   - The app creates the keyspace automatically
   - Check Cassandra logs if creation fails

3. **Timeout Errors**
   - Increase timeout values for slow networks
   - Check Cassandra performance

4. **High Memory Usage**
   - Use streaming endpoints for large datasets
   - Reduce `fetch_size` for better memory control

This example serves as both a learning resource and a production-ready template for building FastAPI applications with Cassandra using async-cassandra.