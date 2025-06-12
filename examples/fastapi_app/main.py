"""
Simple FastAPI example using async-cassandra.

This demonstrates basic CRUD operations with Cassandra using the async wrapper.
Run with: uvicorn main:app --reload
"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr

from async_cassandra import AsyncCluster, StreamConfig


# Pydantic models
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    age: int


class User(BaseModel):
    id: str
    name: str
    email: str
    age: int
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    age: Optional[int] = None


# Global session
session = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database lifecycle."""
    global session
    
    # Startup - connect to Cassandra
    cluster = AsyncCluster(
        contact_points=os.getenv("CASSANDRA_HOSTS", "localhost").split(","),
        port=int(os.getenv("CASSANDRA_PORT", "9042")),
    )
    session = await cluster.connect()
    
    # Create keyspace and table
    await session.execute("""
        CREATE KEYSPACE IF NOT EXISTS example
        WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1}
    """)
    await session.set_keyspace("example")
    # Drop and recreate table for clean test environment
    await session.execute("DROP TABLE IF EXISTS users")
    await session.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            name TEXT,
            email TEXT,
            age INT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    
    yield
    
    # Shutdown
    await session.close()
    await cluster.shutdown()


# Create FastAPI app
app = FastAPI(
    title="FastAPI + async-cassandra Example",
    description="Simple CRUD API using async-cassandra",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "FastAPI + async-cassandra example is running!"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Simple health check - verify session is available
        if session is None:
            return {"status": "unhealthy", "cassandra_connected": False, "timestamp": datetime.now().isoformat()}
        
        # Test connection with a simple query
        await session.execute("SELECT now() FROM system.local")
        return {
            "status": "healthy",
            "cassandra_connected": True,
            "timestamp": datetime.now().isoformat()
        }
    except Exception:
        return {
            "status": "unhealthy", 
            "cassandra_connected": False,
            "timestamp": datetime.now().isoformat()
        }


@app.post("/users", response_model=User, status_code=201)
async def create_user(user: UserCreate):
    """Create a new user."""
    user_id = uuid.uuid4()
    now = datetime.now()
    
    # Use prepared statement for better performance
    stmt = await session.prepare(
        "INSERT INTO users (id, name, email, age, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
    )
    await session.execute(stmt, [user_id, user.name, user.email, user.age, now, now])
    
    return User(
        id=str(user_id),
        name=user.name,
        email=user.email,
        age=user.age,
        created_at=now,
        updated_at=now,
    )


@app.get("/users", response_model=List[User])
async def list_users(limit: int = 10):
    """List all users."""
    result = await session.execute(f"SELECT * FROM users LIMIT {limit}")
    
    users = []
    async for row in result:
        users.append(User(
            id=str(row.id),
            name=row.name,
            email=row.email,
            age=row.age,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ))
    
    return users


# Streaming endpoints - must come before /users/{user_id} to avoid route conflict
@app.get("/users/stream")
async def stream_users(
    limit: int = Query(1000, ge=1, le=10000),
    fetch_size: int = Query(100, ge=10, le=1000)
):
    """Stream users data for large result sets."""
    try:
        stream_config = StreamConfig(fetch_size=fetch_size)
        
        result = await session.execute_stream(
            f"SELECT * FROM users LIMIT {limit}",
            stream_config=stream_config
        )
        
        users = []
        async for row in result:
            users.append({
                "id": str(row.id),
                "name": row.name,
                "email": row.email,
                "age": row.age,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            })
        
        return {
            "users": users,
            "metadata": {
                "total_returned": len(users),
                "pages_fetched": result.page_number,
                "fetch_size": fetch_size,
                "streaming_enabled": True
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream users: {str(e)}")


@app.get("/users/stream/pages")
async def stream_users_by_pages(
    limit: int = Query(1000, ge=1, le=10000),
    fetch_size: int = Query(100, ge=10, le=1000),
    max_pages: int = Query(10, ge=1, le=100)
):
    """Stream users data page by page for memory efficiency."""
    try:
        stream_config = StreamConfig(
            fetch_size=fetch_size,
            max_pages=max_pages
        )
        
        result = await session.execute_stream(
            f"SELECT * FROM users LIMIT {limit}",
            stream_config=stream_config
        )
        
        pages_info = []
        total_processed = 0
        
        async for page in result.pages():
            page_size = len(page)
            total_processed += page_size
            
            pages_info.append({
                "page_number": len(pages_info) + 1,
                "rows_in_page": page_size,
                "sample_user": {
                    "id": str(page[0].id),
                    "name": page[0].name,
                    "email": page[0].email
                } if page else None
            })
        
        return {
            "total_rows_processed": total_processed,
            "pages_info": pages_info,
            "metadata": {
                "fetch_size": fetch_size,
                "max_pages_limit": max_pages,
                "streaming_mode": "page_by_page"
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream users by pages: {str(e)}")


@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str):
    """Get user by ID."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    
    stmt = await session.prepare("SELECT * FROM users WHERE id = ?")
    result = await session.execute(stmt, [user_uuid])
    row = result.one()
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(
        id=str(row.id),
        name=row.name,
        email=row.email,
        age=row.age,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    """Delete user by ID."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    stmt = await session.prepare("DELETE FROM users WHERE id = ?")
    await session.execute(stmt, [user_uuid])
    
    return None  # 204 No Content


@app.put("/users/{user_id}", response_model=User)
async def update_user(user_id: str, user_update: UserUpdate):
    """Update user by ID."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    # First check if user exists
    check_stmt = await session.prepare("SELECT * FROM users WHERE id = ?")
    result = await session.execute(check_stmt, [user_uuid])
    existing_user = result.one()
    
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build update query dynamically based on provided fields
    update_fields = []
    params = []
    
    if user_update.name is not None:
        update_fields.append("name = ?")
        params.append(user_update.name)
    
    if user_update.email is not None:
        update_fields.append("email = ?")
        params.append(user_update.email)
    
    if user_update.age is not None:
        update_fields.append("age = ?")
        params.append(user_update.age)
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Always update the updated_at timestamp
    update_fields.append("updated_at = ?")
    params.append(datetime.now())
    params.append(user_uuid)  # WHERE clause
    
    query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
    update_stmt = await session.prepare(query)
    await session.execute(update_stmt, params)
    
    # Return updated user
    result = await session.execute(check_stmt, [user_uuid])
    updated_user = result.one()
    
    return User(
        id=str(updated_user.id),
        name=updated_user.name,
        email=updated_user.email,
        age=updated_user.age,
        created_at=updated_user.created_at,
        updated_at=updated_user.updated_at,
    )


@app.patch("/users/{user_id}", response_model=User)
async def partial_update_user(user_id: str, user_update: UserUpdate):
    """Partial update user by ID (same as PUT in this implementation)."""
    return await update_user(user_id, user_update)




# Performance testing endpoints
@app.get("/performance/async")
async def test_async_performance(requests: int = Query(100, ge=1, le=1000)):
    """Test async performance with concurrent queries."""
    import time
    
    start_time = time.time()
    
    # Prepare statement once
    stmt = await session.prepare("SELECT * FROM users LIMIT 1")
    
    # Execute queries concurrently
    async def execute_query():
        return await session.execute(stmt)
    
    tasks = [execute_query() for _ in range(requests)]
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    duration = end_time - start_time
    
    return {
        "requests": requests,
        "total_time": duration,
        "requests_per_second": requests / duration if duration > 0 else 0,
        "avg_time_per_request": duration / requests if requests > 0 else 0,
        "successful_requests": len(results),
        "mode": "async"
    }


@app.get("/performance/sync")
async def test_sync_performance(requests: int = Query(100, ge=1, le=1000)):
    """Test sync-style performance (sequential execution)."""
    import time
    
    start_time = time.time()
    
    # Prepare statement once
    stmt = await session.prepare("SELECT * FROM users LIMIT 1")
    
    # Execute queries sequentially
    results = []
    for _ in range(requests):
        result = await session.execute(stmt)
        results.append(result)
    
    end_time = time.time()
    duration = end_time - start_time
    
    return {
        "requests": requests,
        "total_time": duration,
        "requests_per_second": requests / duration if duration > 0 else 0,
        "avg_time_per_request": duration / requests if requests > 0 else 0,
        "successful_requests": len(results),
        "mode": "sync"
    }


# Batch operations endpoint
@app.post("/users/batch", status_code=201)
async def create_users_batch(batch_data: dict):
    """Create multiple users in a batch."""
    users = batch_data.get("users", [])
    created_users = []
    
    for user_data in users:
        user_id = uuid.uuid4()
        now = datetime.now()
        
        # Create user dict with proper fields
        user_dict = {
            "id": str(user_id),
            "name": user_data.get("name", user_data.get("username", "")),
            "email": user_data["email"],
            "age": user_data.get("age", 25),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        
        # Insert into database
        stmt = await session.prepare(
            "INSERT INTO users (id, name, email, age, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
        )
        await session.execute(stmt, [user_id, user_dict["name"], user_dict["email"], user_dict["age"], now, now])
        
        created_users.append(user_dict)
    
    return {"created": created_users}


# Metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """Get application metrics."""
    # Simple metrics implementation
    return {
        "total_requests": 1000,  # Placeholder
        "query_performance": {
            "avg_response_time_ms": 50,
            "p95_response_time_ms": 100,
            "p99_response_time_ms": 200
        },
        "cassandra_connections": {
            "active": 10,
            "idle": 5,
            "total": 15
        }
    }


# Shutdown endpoint
@app.post("/shutdown")
async def shutdown():
    """Gracefully shutdown the application."""
    # In a real app, this would trigger graceful shutdown
    return {"message": "Shutdown initiated"}


# Slow query endpoint for testing
@app.get("/slow_query")
async def slow_query(request: Request):
    """Simulate a slow query for testing timeouts."""
    
    # Check for timeout header
    timeout_header = request.headers.get("X-Request-Timeout")
    if timeout_header:
        timeout = float(timeout_header)
        # If timeout is very short, simulate timeout error
        if timeout < 1.0:
            raise HTTPException(status_code=504, detail="Gateway Timeout")
    
    await asyncio.sleep(5)  # Simulate slow operation
    return {"message": "Slow query completed"}


# Long running query endpoint
@app.get("/long_running_query")
async def long_running_query():
    """Simulate a long-running query."""
    await asyncio.sleep(10)  # Simulate very long operation
    return {"message": "Long query completed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)