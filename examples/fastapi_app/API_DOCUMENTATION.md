# FastAPI + async-cassandra API Documentation

## Base URL
```
http://localhost:8000
```

## Authentication
Currently, no authentication is required. In production, implement appropriate security measures.

## Response Format
All responses are in JSON format with appropriate HTTP status codes.

### Success Response
```json
{
    "data": { ... },
    "status": "success"
}
```

### Error Response
```json
{
    "detail": "Error message",
    "status": "error"
}
```

## Endpoints

### 1. Health Check

Check the health status of the application and database connection.

**Endpoint:** `GET /health`

**Response:**
```json
{
    "status": "healthy",
    "cassandra_connected": true,
    "timestamp": "2024-01-10T12:34:56.789012"
}
```

**Status Codes:**
- `200 OK`: Application is healthy
- `503 Service Unavailable`: Database connection issue

**Example:**
```bash
curl -X GET http://localhost:8000/health
```

### 2. Create User

Create a new user in the system.

**Endpoint:** `POST /users`

**Request Body:**
```json
{
    "name": "John Doe",
    "email": "john.doe@example.com",
    "age": 30
}
```

**Validation Rules:**
- `name`: Required, 1-100 characters
- `email`: Required, valid email format
- `age`: Required, 0-150

**Response:**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "age": 30,
    "created_at": "2024-01-10T12:34:56.789012",
    "updated_at": "2024-01-10T12:34:56.789012"
}
```

**Status Codes:**
- `201 Created`: User created successfully
- `400 Bad Request`: Invalid input data
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Database error

**Example:**
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john.doe@example.com",
    "age": 30
  }'
```

### 3. Get User by ID

Retrieve a specific user by their UUID.

**Endpoint:** `GET /users/{user_id}`

**Path Parameters:**
- `user_id`: UUID of the user (required)

**Response:**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "age": 30,
    "created_at": "2024-01-10T12:34:56.789012",
    "updated_at": "2024-01-10T12:34:56.789012"
}
```

**Status Codes:**
- `200 OK`: User found
- `400 Bad Request`: Invalid UUID format
- `404 Not Found`: User not found
- `500 Internal Server Error`: Database error

**Example:**
```bash
curl -X GET http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

### 4. List Users

Retrieve a paginated list of users.

**Endpoint:** `GET /users`

**Query Parameters:**
- `limit`: Number of results to return (1-100, default: 10)

**Response:**
```json
[
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "age": 30,
        "created_at": "2024-01-10T12:34:56.789012",
        "updated_at": "2024-01-10T12:34:56.789012"
    },
    {
        "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "name": "Jane Smith",
        "email": "jane.smith@example.com",
        "age": 25,
        "created_at": "2024-01-10T13:00:00.000000",
        "updated_at": "2024-01-10T13:00:00.000000"
    }
]
```

**Status Codes:**
- `200 OK`: Success
- `400 Bad Request`: Invalid limit parameter
- `500 Internal Server Error`: Database error

**Example:**
```bash
# Get first 20 users
curl -X GET "http://localhost:8000/users?limit=20"

# Get default 10 users
curl -X GET http://localhost:8000/users
```

### 5. Update User

Update an existing user's information.

**Endpoint:** `PUT /users/{user_id}`

**Path Parameters:**
- `user_id`: UUID of the user (required)

**Request Body:** (all fields optional)
```json
{
    "name": "John Smith",
    "email": "john.smith@example.com",
    "age": 31
}
```

**Response:**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "John Smith",
    "email": "john.smith@example.com",
    "age": 31,
    "created_at": "2024-01-10T12:34:56.789012",
    "updated_at": "2024-01-10T14:00:00.123456"
}
```

**Status Codes:**
- `200 OK`: User updated successfully
- `400 Bad Request`: Invalid UUID format or input data
- `404 Not Found`: User not found
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Database error

**Example:**
```bash
# Update only age
curl -X PUT http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{"age": 31}'

# Update multiple fields
curl -X PUT http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Smith",
    "email": "john.smith@example.com"
  }'
```

### 6. Delete User

Delete a user from the system.

**Endpoint:** `DELETE /users/{user_id}`

**Path Parameters:**
- `user_id`: UUID of the user (required)

**Response:** No content (204)

**Status Codes:**
- `204 No Content`: User deleted successfully
- `400 Bad Request`: Invalid UUID format
- `500 Internal Server Error`: Database error

**Example:**
```bash
curl -X DELETE http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

### 7. Async Performance Test

Test the performance of concurrent async operations.

**Endpoint:** `GET /performance/async`

**Query Parameters:**
- `requests`: Number of concurrent requests (1-1000, default: 100)

**Response:**
```json
{
    "total_time": 0.523,
    "requests": 100,
    "avg_time_per_request": 0.00523,
    "requests_per_second": 191.2
}
```

**Status Codes:**
- `200 OK`: Test completed
- `400 Bad Request`: Invalid requests parameter
- `503 Service Unavailable`: Database not available

**Example:**
```bash
# Test with 500 concurrent requests
curl -X GET "http://localhost:8000/performance/async?requests=500"
```

### 8. Sync Performance Test (Simulated)

Test simulated synchronous operations for comparison.

**Endpoint:** `GET /performance/sync`

**Query Parameters:**
- `requests`: Number of sequential requests (1-1000, default: 100)

**Response:**
```json
{
    "total_time": 1.050,
    "requests": 100,
    "avg_time_per_request": 0.0105,
    "requests_per_second": 95.24
}
```

**Status Codes:**
- `200 OK`: Test completed
- `400 Bad Request`: Invalid requests parameter

**Example:**
```bash
curl -X GET "http://localhost:8000/performance/sync?requests=100"
```

## Error Handling

### Common Error Responses

#### Validation Error (422)
```json
{
    "detail": [
        {
            "loc": ["body", "age"],
            "msg": "ensure this value is greater than or equal to 0",
            "type": "value_error.number.not_ge",
            "ctx": {"limit_value": 0}
        }
    ]
}
```

#### Not Found (404)
```json
{
    "detail": "User not found"
}
```

#### Database Error (500)
```json
{
    "detail": "Failed to create user: Connection error"
}
```

#### Service Unavailable (503)
```json
{
    "detail": "Database not available"
}
```

## Rate Limiting

Currently not implemented. In production, consider implementing rate limiting to prevent abuse.

## Pagination

The `/users` endpoint supports basic pagination through the `limit` parameter. For production use, consider implementing:
- Cursor-based pagination for large datasets
- Offset-based pagination with `page` and `per_page` parameters
- Total count in response headers

## Batch Operations

For bulk operations, consider implementing:
- `POST /users/batch` for creating multiple users
- `DELETE /users/batch` for deleting multiple users
- Transaction support for consistency

## WebSocket Support

For real-time updates, consider adding WebSocket endpoints:
- `/ws/users` for real-time user updates
- Event streaming for data changes

## OpenAPI Schema

The complete OpenAPI schema is available at:
- Interactive documentation: http://localhost:8000/docs
- ReDoc documentation: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Testing the API

### Using HTTPie
```bash
# Install HTTPie
pip install httpie

# Create user
http POST localhost:8000/users name="Test User" email="test@example.com" age=25

# Get user
http GET localhost:8000/users/550e8400-e29b-41d4-a716-446655440000

# Update user
http PUT localhost:8000/users/550e8400-e29b-41d4-a716-446655440000 age=26

# Delete user
http DELETE localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

### Using Python
```python
import httpx
import asyncio

async def test_api():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Create user
        response = await client.post("/users", json={
            "name": "Test User",
            "email": "test@example.com",
            "age": 25
        })
        user = response.json()
        print(f"Created user: {user}")
        
        # Get user
        response = await client.get(f"/users/{user['id']}")
        print(f"Retrieved user: {response.json()}")
        
        # Update user
        response = await client.put(f"/users/{user['id']}", json={"age": 26})
        print(f"Updated user: {response.json()}")
        
        # Delete user
        response = await client.delete(f"/users/{user['id']}")
        print(f"Deleted user: {response.status_code}")

asyncio.run(test_api())
```

### Using Postman

Import the OpenAPI schema from http://localhost:8000/openapi.json into Postman for a complete collection of API endpoints.