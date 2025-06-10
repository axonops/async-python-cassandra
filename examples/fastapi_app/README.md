# FastAPI + async-cassandra Example Application

This example demonstrates how to build a high-performance REST API using FastAPI with the async-cassandra driver. It showcases the performance benefits of using async operations with Apache Cassandra® compared to traditional synchronous approaches.

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Sequence Diagrams](#sequence-diagrams)
- [Performance Testing](#performance-testing)
- [Docker Deployment](#docker-deployment)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

This example application implements a simple user management system with CRUD operations, demonstrating:
- Async connection management with Apache Cassandra®
- Prepared statement usage for optimal performance
- Batch operations for efficient data processing
- Performance comparison endpoints (async vs sync)
- Proper error handling and validation
- Health check endpoints
- Integration testing setup

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│                 │     │                  │     │                 │
│  FastAPI App    │────▶│ async-cassandra  │────▶│ Apache Cassandra│
│                 │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                                                  │
        │                                                  │
        └──────────── Async Operations ────────────────────┘
```

### Key Components

1. **FastAPI Application** (`main.py`)
   - Handles HTTP requests/responses
   - Manages application lifecycle
   - Validates input data using Pydantic

2. **async-cassandra Driver**
   - Provides async interface to Cassandra
   - Manages connection pooling
   - Handles query execution asynchronously

3. **Apache Cassandra®**
   - Stores user data
   - Provides distributed, scalable database

## Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose (for running Cassandra)
- pip package manager

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/async-python-cassandra.git
cd async-python-cassandra/examples/fastapi_app
```

2. **Create a virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

Or install the async-cassandra package with FastAPI extras:
```bash
pip install "async-cassandra[fastapi]"
```

## Running the Application

### Option 1: Using Docker Compose (Recommended)

1. **Start Cassandra and the application:**
```bash
docker-compose up -d
```

2. **Check the logs:**
```bash
docker-compose logs -f app
```

3. **Access the application:**
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Option 2: Local Development

1. **Start Cassandra using Docker:**
```bash
docker run -d \
  --name cassandra \
  -p 9042:9042 \
  -e CASSANDRA_CLUSTER_NAME=TestCluster \
  cassandra:5.0
```

2. **Wait for Cassandra to be ready:**
```bash
docker logs -f cassandra
# Wait for "Starting listening for CQL clients" message
```

3. **Run the FastAPI application:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Option 3: Using Environment Variables

Configure the connection using environment variables:
```bash
export CASSANDRA_HOSTS=localhost,192.168.1.10
export CASSANDRA_PORT=9042
uvicorn main:app --reload
```

## API Endpoints

### Health Check

```bash
GET /health
```

Check application and database health:
```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "cassandra_connected": true,
  "timestamp": "2024-01-10T12:00:00"
}
```

### User Management

#### Create User
```bash
POST /users
Content-Type: application/json

{
  "name": "John Doe",
  "email": "john@example.com",
  "age": 30
}
```

Example:
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30
  }'
```

#### Get User by ID
```bash
GET /users/{user_id}
```

Example:
```bash
curl http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

#### List Users
```bash
GET /users?limit=10
```

Example:
```bash
curl "http://localhost:8000/users?limit=20"
```

#### Update User
```bash
PUT /users/{user_id}
Content-Type: application/json

{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "age": 31
}
```

Example:
```bash
curl -X PUT http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Doe",
    "age": 31
  }'
```

#### Delete User
```bash
DELETE /users/{user_id}
```

Example:
```bash
curl -X DELETE http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

### Performance Testing Endpoints

#### Async Performance Test
```bash
GET /performance/async?requests=100
```

Tests concurrent async query execution:
```bash
curl "http://localhost:8000/performance/async?requests=100"
```

Response:
```json
{
  "total_time": 0.523,
  "requests": 100,
  "avg_time_per_request": 0.00523,
  "requests_per_second": 191.2
}
```

#### Sync Performance Test (Simulated)
```bash
GET /performance/sync?requests=100
```

Simulates synchronous query execution for comparison:
```bash
curl "http://localhost:8000/performance/sync?requests=100"
```

## Sequence Diagrams

Detailed sequence diagrams showing the flow of each API endpoint are available in [SEQUENCE_DIAGRAMS.md](SEQUENCE_DIAGRAMS.md). These diagrams illustrate:

- Request/response flow for each endpoint
- Async execution patterns
- Error handling scenarios
- Database interaction details
- Performance comparison between async and sync operations

## Performance Testing

### Running Integration Tests

```bash
# Run all tests
pytest test_fastapi_integration.py -v

# Run specific test class
pytest test_fastapi_integration.py::TestUserCRUD -v

# Run with coverage
pytest test_fastapi_integration.py --cov=main --cov-report=html
```

### Load Testing with Apache Bench

```bash
# Test concurrent user creation
ab -n 1000 -c 50 -p user.json -T application/json \
  http://localhost:8000/users

# Test concurrent reads
ab -n 10000 -c 100 http://localhost:8000/users
```

### Performance Comparison Script

Create a script to compare async vs sync performance:

```python
import asyncio
import httpx
import time

async def test_performance():
    async with httpx.AsyncClient() as client:
        # Test async performance
        async_start = time.time()
        async_resp = await client.get(
            "http://localhost:8000/performance/async?requests=500"
        )
        async_time = time.time() - async_start
        
        # Test sync performance
        sync_start = time.time()
        sync_resp = await client.get(
            "http://localhost:8000/performance/sync?requests=500"
        )
        sync_time = time.time() - sync_start
        
        print(f"Async Performance: {async_resp.json()}")
        print(f"Sync Performance: {sync_resp.json()}")
        print(f"\nAsync is {sync_time/async_time:.2f}x faster!")

asyncio.run(test_performance())
```

## Docker Deployment

### Production Docker Compose

Create `docker-compose.prod.yml`:
```yaml
version: '3.8'

services:
  cassandra:
    image: cassandra:5.0
    container_name: prod-cassandra
    ports:
      - "9042:9042"
    environment:
      - CASSANDRA_CLUSTER_NAME=ProdCluster
      - CASSANDRA_DC=datacenter1
      - CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch
    volumes:
      - cassandra_data:/var/lib/cassandra
    healthcheck:
      test: ["CMD", "cqlsh", "-e", "describe keyspaces"]
      interval: 30s
      timeout: 10s
      retries: 5

  app:
    build: .
    container_name: fastapi-app
    ports:
      - "8000:8000"
    environment:
      - CASSANDRA_HOSTS=cassandra
      - CASSANDRA_PORT=9042
    depends_on:
      cassandra:
        condition: service_healthy
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

volumes:
  cassandra_data:
```

### Building and Running

```bash
# Build the application
docker build -t async-cassandra-fastapi .

# Run in production
docker-compose -f docker-compose.prod.yml up -d

# Scale the application
docker-compose -f docker-compose.prod.yml up -d --scale app=3
```

## Best Practices

### 1. Connection Management
- Use connection pooling (handled by async-cassandra)
- Implement proper cleanup in shutdown hooks
- Use health checks to monitor connection status

### 2. Query Optimization
- Always use prepared statements for repeated queries
- Batch related operations when possible
- Use appropriate consistency levels

### 3. Error Handling
```python
try:
    result = await session.execute(query)
except Unavailable as e:
    # Handle node unavailability
    logger.error(f"Cassandra node unavailable: {e}")
    raise HTTPException(status_code=503, detail="Database temporarily unavailable")
except ReadTimeout as e:
    # Handle read timeout
    logger.error(f"Read timeout: {e}")
    raise HTTPException(status_code=504, detail="Database read timeout")
```

### 4. Data Modeling
- Design tables based on query patterns
- Use appropriate partition keys
- Avoid large partitions (> 100MB)

### 5. Monitoring
- Track query latencies
- Monitor connection pool usage
- Set up alerts for failures

## Troubleshooting

### Common Issues

1. **Connection Refused**
   ```
   Solution: Ensure Cassandra is running and accessible
   docker ps  # Check if Cassandra container is running
   docker logs cassandra  # Check Cassandra logs
   ```

2. **Keyspace Does Not Exist**
   ```
   Solution: The app creates the keyspace on startup. 
   Check application logs for errors during initialization.
   ```

3. **Timeout Errors**
   ```
   Solution: Increase timeout values or check Cassandra performance
   - Check cluster health: nodetool status
   - Monitor system resources
   ```

4. **Import Errors**
   ```
   Solution: Ensure all dependencies are installed
   pip install -r requirements.txt
   ```

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or set environment variable:
```bash
export LOG_LEVEL=DEBUG
uvicorn main:app --log-level debug
```

## Advanced Usage

### Custom Retry Policies

```python
from async_cassandra import AsyncRetryPolicy

custom_retry = AsyncRetryPolicy(max_retries=5)
cluster = AsyncCluster(retry_policy=custom_retry)
```

### Batch Operations

```python
from cassandra.query import BatchStatement

batch = BatchStatement()
for user in users:
    batch.add(insert_stmt, (user.id, user.name, user.email))
await session.execute(batch)
```

### Async Context Manager

```python
async with AsyncCluster() as cluster:
    async with await cluster.connect() as session:
        result = await session.execute("SELECT * FROM users")
        async for row in result:
            print(row)
```

## Contributing

See the main project's [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

## License

This example is part of the async-cassandra project and is licensed under the Apache License 2.0.

## Acknowledgments

Apache Cassandra® is a registered trademark of the Apache Software Foundation.