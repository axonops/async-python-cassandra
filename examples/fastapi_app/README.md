# FastAPI + async-cassandra Example

Simple FastAPI application demonstrating async Cassandra operations with streaming support.

## Quick Start

1. **Start Cassandra**:
   ```bash
   docker run -d --name cassandra -p 9042:9042 cassandra:latest
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**:
   ```bash
   uvicorn main:app --reload
   ```

## API Endpoints

### Basic CRUD Operations
- `GET /` - Health check
- `POST /users` - Create user
- `GET /users/{user_id}` - Get user by ID
- `GET /users` - List users (with limit)
- `DELETE /users/{user_id}` - Delete user

### Streaming Endpoints
- `GET /users/stream` - Stream users data for large result sets
- `GET /users/stream/pages` - Stream users page by page for memory efficiency

## Example Usage

```bash
# Create a user
curl -X POST "http://localhost:8000/users" \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "age": 30}'

# Get user by ID
curl "http://localhost:8000/users/{user_id}"

# List users
curl "http://localhost:8000/users?limit=5"

# Stream users for large datasets
curl "http://localhost:8000/users/stream?limit=1000&fetch_size=100"

# Stream users page by page
curl "http://localhost:8000/users/stream/pages?limit=1000&fetch_size=100&max_pages=10"
```

## Configuration

Set environment variables:
- `CASSANDRA_HOSTS` - Comma-separated host list (default: localhost)
- `CASSANDRA_PORT` - Port number (default: 9042)

## Testing

```bash
pytest test_fastapi_integration.py
```

## Features Demonstrated

- Async database connections with lifespan management
- Prepared statements for better performance
- Streaming functionality for large datasets
- Proper error handling and validation
- Type-safe Pydantic models
- Basic CRUD operations