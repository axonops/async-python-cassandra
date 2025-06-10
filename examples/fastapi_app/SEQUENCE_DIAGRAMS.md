# FastAPI + async-cassandra Sequence Diagrams

This document contains Mermaid sequence diagrams showing the flow of each API endpoint in the FastAPI example application.

## Table of Contents
- [Health Check Endpoint](#health-check-endpoint)
- [Create User Endpoint](#create-user-endpoint)
- [Get User by ID Endpoint](#get-user-by-id-endpoint)
- [List Users Endpoint](#list-users-endpoint)
- [Update User Endpoint](#update-user-endpoint)
- [Delete User Endpoint](#delete-user-endpoint)
- [Async Performance Test Endpoint](#async-performance-test-endpoint)
- [Sync Performance Test Endpoint](#sync-performance-test-endpoint)

## Health Check Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: GET /health
    FastAPI->>AsyncCassandra: session.execute("SELECT release_version FROM system.local")
    AsyncCassandra->>Cassandra: Execute query (async)
    Cassandra-->>AsyncCassandra: Query result
    AsyncCassandra-->>FastAPI: AsyncResultSet
    
    alt Success
        FastAPI-->>Client: 200 OK<br/>{"status": "healthy",<br/>"cassandra_connected": true,<br/>"timestamp": "2024-01-10T12:00:00"}
    else Database Error
        FastAPI-->>Client: 200 OK<br/>{"status": "unhealthy",<br/>"cassandra_connected": false,<br/>"timestamp": "2024-01-10T12:00:00"}
    end
```

### Example Request:
```bash
curl -X GET http://localhost:8000/health
```

### Example Response:
```json
{
    "status": "healthy",
    "cassandra_connected": true,
    "timestamp": "2024-01-10T12:34:56.789012"
}
```

## Create User Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant Pydantic
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: POST /users<br/>{"name": "John Doe",<br/>"email": "john@example.com",<br/>"age": 30}
    FastAPI->>Pydantic: Validate UserCreate model
    
    alt Validation Success
        Pydantic-->>FastAPI: Valid data
        FastAPI->>FastAPI: Generate UUID<br/>user_id = uuid.uuid4()
        FastAPI->>AsyncCassandra: session.execute(insert_stmt,<br/>(user_id, name, email, age, now, now))
        AsyncCassandra->>Cassandra: INSERT INTO users<br/>(prepared statement)
        Cassandra-->>AsyncCassandra: Success
        AsyncCassandra-->>FastAPI: AsyncResultSet
        FastAPI-->>Client: 201 Created<br/>{"id": "550e8400-...",<br/>"name": "John Doe",<br/>"email": "john@example.com",<br/>"age": 30,<br/>"created_at": "2024-01-10T12:00:00",<br/>"updated_at": "2024-01-10T12:00:00"}
    else Validation Error
        Pydantic-->>FastAPI: ValidationError
        FastAPI-->>Client: 422 Unprocessable Entity<br/>{"detail": [{"loc": ["body", "email"],<br/>"msg": "invalid email format",<br/>"type": "value_error.email"}]}
    else Database Error
        AsyncCassandra-->>FastAPI: QueryError
        FastAPI-->>Client: 500 Internal Server Error<br/>{"detail": "Failed to create user: Connection error"}
    end
```

### Example Request:
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30
  }'
```

### Example Response:
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30,
    "created_at": "2024-01-10T12:34:56.789012",
    "updated_at": "2024-01-10T12:34:56.789012"
}
```

## Get User by ID Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: GET /users/550e8400-e29b-41d4-a716-446655440000
    FastAPI->>FastAPI: Validate UUID format
    
    alt Valid UUID
        FastAPI->>AsyncCassandra: session.execute(select_stmt, [user_uuid])
        AsyncCassandra->>Cassandra: SELECT * FROM users WHERE id = ?<br/>(prepared statement)
        Cassandra-->>AsyncCassandra: Row data or empty
        AsyncCassandra-->>FastAPI: AsyncResultSet
        FastAPI->>FastAPI: result.one()
        
        alt User Found
            FastAPI-->>Client: 200 OK<br/>{"id": "550e8400-...",<br/>"name": "John Doe",<br/>"email": "john@example.com",<br/>"age": 30,<br/>"created_at": "2024-01-10T12:00:00",<br/>"updated_at": "2024-01-10T12:00:00"}
        else User Not Found
            FastAPI-->>Client: 404 Not Found<br/>{"detail": "User not found"}
        end
    else Invalid UUID
        FastAPI-->>Client: 400 Bad Request<br/>{"detail": "Invalid user ID format"}
    else Database Error
        AsyncCassandra-->>FastAPI: QueryError
        FastAPI-->>Client: 500 Internal Server Error<br/>{"detail": "Failed to get user: Connection error"}
    end
```

### Example Request:
```bash
curl -X GET http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

### Example Response:
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30,
    "created_at": "2024-01-10T12:34:56.789012",
    "updated_at": "2024-01-10T12:34:56.789012"
}
```

## List Users Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: GET /users?limit=20
    FastAPI->>FastAPI: Validate limit (1-100)
    
    alt Valid Limit
        FastAPI->>AsyncCassandra: session.execute("SELECT * FROM users LIMIT 20")
        AsyncCassandra->>Cassandra: Execute query (async)
        Cassandra-->>AsyncCassandra: Multiple rows
        AsyncCassandra-->>FastAPI: AsyncResultSet
        
        FastAPI->>FastAPI: Iterate async for row in result
        loop For each row
            FastAPI->>FastAPI: Create User object
        end
        
        FastAPI-->>Client: 200 OK<br/>[{"id": "550e8400-...", "name": "John Doe", ...},<br/>{"id": "6ba7b810-...", "name": "Jane Smith", ...}]
    else Invalid Limit
        FastAPI-->>Client: 422 Unprocessable Entity<br/>{"detail": [{"loc": ["query", "limit"],<br/>"msg": "ensure this value is less than or equal to 100"}]}
    else Database Error
        AsyncCassandra-->>FastAPI: QueryError
        FastAPI-->>Client: 500 Internal Server Error<br/>{"detail": "Failed to list users: Connection error"}
    end
```

### Example Request:
```bash
curl -X GET "http://localhost:8000/users?limit=10"
```

### Example Response:
```json
[
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "John Doe",
        "email": "john@example.com",
        "age": 30,
        "created_at": "2024-01-10T12:34:56.789012",
        "updated_at": "2024-01-10T12:34:56.789012"
    },
    {
        "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "name": "Jane Smith",
        "email": "jane@example.com",
        "age": 25,
        "created_at": "2024-01-10T13:00:00.000000",
        "updated_at": "2024-01-10T13:00:00.000000"
    }
]
```

## Update User Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant Pydantic
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: PUT /users/550e8400-...<br/>{"name": "John Smith", "age": 31}
    FastAPI->>FastAPI: Validate UUID format
    FastAPI->>Pydantic: Validate UserUpdate model
    
    alt Validation Success
        FastAPI->>AsyncCassandra: session.execute(select_stmt, [user_uuid])
        AsyncCassandra->>Cassandra: SELECT * FROM users WHERE id = ?
        Cassandra-->>AsyncCassandra: Existing user data
        AsyncCassandra-->>FastAPI: AsyncResultSet
        
        alt User Exists
            FastAPI->>FastAPI: Merge updates with existing data
            FastAPI->>AsyncCassandra: session.execute(update_stmt,<br/>(name, email, age, updated_at, user_uuid))
            AsyncCassandra->>Cassandra: UPDATE users SET ... WHERE id = ?<br/>(prepared statement)
            Cassandra-->>AsyncCassandra: Success
            AsyncCassandra-->>FastAPI: AsyncResultSet
            FastAPI-->>Client: 200 OK<br/>{"id": "550e8400-...",<br/>"name": "John Smith",<br/>"email": "john@example.com",<br/>"age": 31,<br/>"created_at": "2024-01-10T12:00:00",<br/>"updated_at": "2024-01-10T14:00:00"}
        else User Not Found
            FastAPI-->>Client: 404 Not Found<br/>{"detail": "User not found"}
        end
    else Validation Error
        FastAPI-->>Client: 422 Unprocessable Entity<br/>{"detail": [validation errors]}
    else Database Error
        AsyncCassandra-->>FastAPI: QueryError
        FastAPI-->>Client: 500 Internal Server Error<br/>{"detail": "Failed to update user: Connection error"}
    end
```

### Example Request:
```bash
curl -X PUT http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Smith",
    "age": 31
  }'
```

### Example Response:
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "John Smith",
    "email": "john@example.com",
    "age": 31,
    "created_at": "2024-01-10T12:34:56.789012",
    "updated_at": "2024-01-10T14:00:00.123456"
}
```

## Delete User Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: DELETE /users/550e8400-e29b-41d4-a716-446655440000
    FastAPI->>FastAPI: Validate UUID format
    
    alt Valid UUID
        FastAPI->>AsyncCassandra: session.execute(delete_stmt, [user_uuid])
        AsyncCassandra->>Cassandra: DELETE FROM users WHERE id = ?<br/>(prepared statement)
        Cassandra-->>AsyncCassandra: Success (regardless of existence)
        AsyncCassandra-->>FastAPI: AsyncResultSet
        FastAPI-->>Client: 204 No Content
    else Invalid UUID
        FastAPI-->>Client: 400 Bad Request<br/>{"detail": "Invalid user ID format"}
    else Database Error
        AsyncCassandra-->>FastAPI: QueryError
        FastAPI-->>Client: 500 Internal Server Error<br/>{"detail": "Failed to delete user: Connection error"}
    end
```

### Example Request:
```bash
curl -X DELETE http://localhost:8000/users/550e8400-e29b-41d4-a716-446655440000
```

### Example Response:
```
HTTP/1.1 204 No Content
```

## Async Performance Test Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: GET /performance/async?requests=100
    FastAPI->>FastAPI: Validate requests (1-1000)
    FastAPI->>FastAPI: Start timer
    
    par Concurrent Execution
        loop 100 times
            FastAPI->>AsyncCassandra: session.execute("SELECT * FROM users LIMIT 1")
        end
        
        Note over AsyncCassandra,Cassandra: All 100 queries execute<br/>concurrently using asyncio.gather()
        
        AsyncCassandra->>Cassandra: Multiple concurrent queries
        Cassandra-->>AsyncCassandra: Query results
        AsyncCassandra-->>FastAPI: AsyncResultSets
    end
    
    FastAPI->>FastAPI: Stop timer<br/>Calculate metrics
    FastAPI-->>Client: 200 OK<br/>{"total_time": 0.523,<br/>"requests": 100,<br/>"avg_time_per_request": 0.00523,<br/>"requests_per_second": 191.2}
```

### Example Request:
```bash
curl -X GET "http://localhost:8000/performance/async?requests=500"
```

### Example Response:
```json
{
    "total_time": 2.615,
    "requests": 500,
    "avg_time_per_request": 0.00523,
    "requests_per_second": 191.2
}
```

## Sync Performance Test Endpoint

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant AsyncCassandra
    
    Client->>FastAPI: GET /performance/sync?requests=100
    FastAPI->>FastAPI: Validate requests (1-1000)
    FastAPI->>FastAPI: Start timer
    
    loop 100 times (Sequential)
        FastAPI->>FastAPI: await asyncio.sleep(0.01)<br/>(Simulate 10ms query time)
        Note right of FastAPI: Each request waits for<br/>the previous to complete
    end
    
    FastAPI->>FastAPI: Stop timer<br/>Calculate metrics
    FastAPI-->>Client: 200 OK<br/>{"total_time": 1.050,<br/>"requests": 100,<br/>"avg_time_per_request": 0.0105,<br/>"requests_per_second": 95.24}
```

### Example Request:
```bash
curl -X GET "http://localhost:8000/performance/sync?requests=100"
```

### Example Response:
```json
{
    "total_time": 1.050,
    "requests": 100,
    "avg_time_per_request": 0.0105,
    "requests_per_second": 95.24
}
```

## Application Lifecycle

```mermaid
sequenceDiagram
    participant System
    participant FastAPI
    participant AsyncCluster
    participant AsyncCassandraSession
    participant Cassandra
    
    System->>FastAPI: Application startup
    FastAPI->>FastAPI: Enter lifespan context
    FastAPI->>AsyncCluster: Create cluster with config
    FastAPI->>AsyncCluster: cluster.connect()
    AsyncCluster->>Cassandra: Establish connection
    Cassandra-->>AsyncCluster: Connection established
    AsyncCluster-->>FastAPI: AsyncCassandraSession
    
    FastAPI->>AsyncCassandraSession: Create keyspace if not exists
    AsyncCassandraSession->>Cassandra: CREATE KEYSPACE IF NOT EXISTS
    Cassandra-->>AsyncCassandraSession: Success
    
    FastAPI->>AsyncCassandraSession: session.set_keyspace("fastapi_example")
    AsyncCassandraSession->>Cassandra: USE fastapi_example
    Cassandra-->>AsyncCassandraSession: Success
    
    FastAPI->>AsyncCassandraSession: Create users table if not exists
    AsyncCassandraSession->>Cassandra: CREATE TABLE IF NOT EXISTS users
    Cassandra-->>AsyncCassandraSession: Success
    
    FastAPI->>AsyncCassandraSession: Prepare statements
    loop For each statement
        AsyncCassandraSession->>Cassandra: PREPARE statement
        Cassandra-->>AsyncCassandraSession: PreparedStatement
    end
    
    FastAPI-->>System: Application ready
    
    Note over System,Cassandra: Application serves requests...
    
    System->>FastAPI: Application shutdown
    FastAPI->>AsyncCassandraSession: session.close()
    AsyncCassandraSession->>Cassandra: Close connection
    FastAPI->>AsyncCluster: cluster.shutdown()
    AsyncCluster->>Cassandra: Shutdown cluster
    FastAPI-->>System: Cleanup complete
```

## Error Handling Flow

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant AsyncCassandra
    participant Cassandra
    
    Client->>FastAPI: API Request
    FastAPI->>AsyncCassandra: Execute query
    
    alt Success
        AsyncCassandra->>Cassandra: Query
        Cassandra-->>AsyncCassandra: Result
        AsyncCassandra-->>FastAPI: AsyncResultSet
        FastAPI-->>Client: Success Response
    else InvalidRequest
        AsyncCassandra-->>FastAPI: InvalidRequest exception
        FastAPI-->>Client: 400 Bad Request
    else Unavailable
        AsyncCassandra-->>FastAPI: Unavailable exception
        FastAPI-->>Client: 503 Service Unavailable
    else ReadTimeout
        AsyncCassandra-->>FastAPI: ReadTimeout exception
        FastAPI-->>Client: 504 Gateway Timeout
    else WriteTimeout
        AsyncCassandra-->>FastAPI: WriteTimeout exception
        FastAPI-->>Client: 504 Gateway Timeout
    else OperationTimedOut
        AsyncCassandra-->>FastAPI: OperationTimedOut exception
        FastAPI-->>Client: 504 Gateway Timeout
    else Generic Exception
        AsyncCassandra-->>FastAPI: Exception wrapped in QueryError
        FastAPI-->>Client: 500 Internal Server Error
    end
```

## Performance Comparison

The key difference between async and sync operations:

```mermaid
gantt
    title Query Execution Timeline
    dateFormat X
    axisFormat %L
    
    section Async (100 queries)
    Query 1     :a1, 0, 10
    Query 2     :a2, 0, 10
    Query 3     :a3, 0, 10
    ...         :a4, 0, 10
    Query 100   :a100, 0, 10
    Total Time  :milestone, 10, 0
    
    section Sync (100 queries)
    Query 1     :s1, 0, 10
    Query 2     :s2, 10, 10
    Query 3     :s3, 20, 10
    ...         :s4, 30, 10
    Query 100   :s100, 990, 10
    Total Time  :milestone, 1000, 0
```

In the async model, all 100 queries execute concurrently, completing in approximately the time of a single query. In the sync model, each query must wait for the previous one to complete, resulting in 100x the execution time.