# FastAPI Example with async-cassandra

This example demonstrates how to use async-cassandra with FastAPI to build a high-performance REST API backed by Cassandra.

## Features

- Async Cassandra operations integrated with FastAPI
- Connection pooling and session management
- CRUD operations for a user management system
- Proper error handling and validation
- Health check endpoint
- Performance comparison endpoints

## Setup

1. Install dependencies:
```bash
pip install fastapi uvicorn async-cassandra
```

2. Start Cassandra (using Docker):
```bash
docker run -d --name cassandra -p 9042:9042 cassandra:5.0
```

3. Run the application:
```bash
uvicorn main:app --reload
```

## API Endpoints

- `GET /health` - Health check
- `POST /users` - Create a new user
- `GET /users/{user_id}` - Get user by ID
- `GET /users` - List all users (with pagination)
- `PUT /users/{user_id}` - Update user
- `DELETE /users/{user_id}` - Delete user
- `GET /performance/sync` - Sync performance test
- `GET /performance/async` - Async performance test

## Testing

Run the integration tests:
```bash
pytest tests/test_fastapi_integration.py
```

## Performance

The async implementation shows significant performance improvements over synchronous operations, especially under high concurrency:

- 3-4x faster response times for concurrent requests
- Better resource utilization
- Lower latency under load