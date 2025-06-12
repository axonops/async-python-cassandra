# FastAPI Example Application

This example demonstrates how to use async-cassandra with FastAPI to build a high-performance REST API backed by Cassandra.

## Overview

The example showcases all the key improvements and features of async-cassandra:
- **Thread Safety**: Handles concurrent requests without data corruption
- **Memory Efficiency**: Streaming endpoints for large datasets
- **Error Handling**: Consistent error responses across all operations
- **Performance**: Async operations providing significant speedup
- **Monitoring**: Health checks and metrics endpoints
- **Production Ready**: Proper lifecycle management and error handling

## Features Demonstrated

### 1. Basic CRUD Operations
- `POST /users` - Create user with validation
- `GET /users/{id}` - Retrieve user by ID
- `PUT /users/{id}` - Update user
- `DELETE /users/{id}` - Delete user
- `GET /users` - List users with pagination

### 2. Streaming Operations
- `GET /users/stream` - Stream large datasets efficiently
- `GET /users/stream/pages` - Page-by-page streaming for memory efficiency

### 3. Batch Operations
- `POST /users/batch` - Create multiple users in batch

### 4. Performance Testing
- `GET /performance/async` - Test async performance
- `GET /performance/sync` - Compare with sequential execution

### 5. Monitoring & Operations
- `GET /health` - Health check with Cassandra connectivity
- `GET /metrics` - Application metrics
- `POST /shutdown` - Graceful shutdown
- `GET /slow_query` - Test timeout handling
- `GET /long_running_query` - Test long operations

## Running the Example

### Prerequisites
1. Cassandra running on localhost:9042
2. Python 3.12+ with async-cassandra installed

### Start the Application
```bash
cd examples/fastapi_app
uvicorn main:app --reload
```

### Environment Variables
- `CASSANDRA_HOSTS` - Comma-separated list of Cassandra hosts (default: localhost)
- `CASSANDRA_PORT` - Cassandra port (default: 9042)

## Testing the Application

### Run the Test Suite
```bash
python test_fastapi_app.py
```

This runs comprehensive tests validating:
- Thread safety under high concurrency
- Memory efficiency with streaming
- Error handling consistency
- Performance improvements
- All endpoints functionality

### Manual Testing with curl

Create a user:
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "age": 30}'
```

List users:
```bash
curl http://localhost:8000/users?limit=10
```

Stream users:
```bash
curl "http://localhost:8000/users/stream?limit=1000&fetch_size=100"
```

Check health:
```bash
curl http://localhost:8000/health
```

## Key Implementation Details

### Thread Safety
The application handles concurrent requests safely using async-cassandra's thread-safe operations:
```python
# Multiple concurrent requests are handled safely
tasks = [session.execute(stmt, params) for _ in range(100)]
results = await asyncio.gather(*tasks)
```

### Memory-Efficient Streaming
Large datasets are streamed without loading everything into memory:
```python
stream_config = StreamConfig(fetch_size=100)
result = await session.execute_stream(query, stream_config=stream_config)
async for row in result:
    # Process row without loading entire result set
```

### Error Handling
Consistent error responses across all operations:
```python
try:
    user_uuid = uuid.UUID(user_id)
except ValueError:
    raise HTTPException(status_code=400, detail="Invalid UUID")
```

### Performance Benefits
Async operations provide significant performance improvements:
```python
# Concurrent execution - much faster than sequential
tasks = [execute_query() for _ in range(requests)]
results = await asyncio.gather(*tasks)
```

## Production Considerations

### Connection Management
The application properly manages Cassandra connections:
- Connections are established during app startup
- Cleanup happens during shutdown
- Connection pooling is handled by async-cassandra

### Error Recovery
- Invalid requests return appropriate HTTP status codes
- Database errors are caught and converted to HTTP errors
- Timeouts are handled gracefully

### Monitoring
- Health endpoint for load balancer checks
- Metrics endpoint for monitoring systems
- Structured logging for debugging

### Scaling
- Stateless design allows horizontal scaling
- Connection pool size can be tuned via `executor_threads`
- Streaming prevents memory issues with large datasets

## Extending the Example

To add new features:

1. **Add New Endpoints**: Follow the existing pattern for CRUD operations
2. **Custom Queries**: Use prepared statements for performance
3. **Add Middleware**: For authentication, rate limiting, etc.
4. **Enhanced Monitoring**: Integrate with Prometheus or other systems
5. **Caching**: Add Redis for frequently accessed data

This example serves as a production-ready template for building FastAPI applications with Cassandra using async-cassandra.