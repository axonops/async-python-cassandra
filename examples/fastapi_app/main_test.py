"""
FastAPI example application with mock support for testing.
This version can run without a real Cassandra instance.
"""

import os
import uuid
import time
import asyncio
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel, EmailStr, Field

# Check if we're in test mode
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

if TEST_MODE:
    print("Running in TEST MODE - using mocked Cassandra")
    # Create mock objects
    from unittest.mock import AsyncMock
    
    class MockAsyncResultSet:
        def __init__(self, rows):
            self._rows = rows
            self._index = 0
            
        def __aiter__(self):
            self._index = 0
            return self
            
        async def __anext__(self):
            if self._index >= len(self._rows):
                raise StopAsyncIteration
            row = self._rows[self._index]
            self._index += 1
            return row
            
        def one(self):
            return self._rows[0] if self._rows else None
            
        def __len__(self):
            return len(self._rows)
    
    class MockAsyncSession:
        def __init__(self):
            self.keyspace = "fastapi_example"
            self._users = {}  # In-memory storage
            
        async def execute(self, query, params=None):
            # Simple query parsing for mocking
            if "SELECT release_version" in str(query):
                return MockAsyncResultSet([{"release_version": "5.0.0"}])
            elif "SELECT * FROM users WHERE id" in str(query):
                user_id = params[0] if params else None
                user = self._users.get(str(user_id))
                return MockAsyncResultSet([user] if user else [])
            elif "SELECT * FROM users LIMIT" in str(query):
                # Extract limit from query
                limit = 10
                if "LIMIT" in str(query):
                    try:
                        limit = int(str(query).split("LIMIT")[1].strip())
                    except:
                        pass
                users = list(self._users.values())[:limit]
                return MockAsyncResultSet(users)
            elif "DELETE FROM users" in str(query):
                user_id = params[0] if params else None
                if str(user_id) in self._users:
                    del self._users[str(user_id)]
                return MockAsyncResultSet([])
            else:
                # For INSERT and UPDATE, just return empty result
                return MockAsyncResultSet([])
                
        async def prepare(self, query, custom_payload=None):
            return Mock()  # Return mock prepared statement
            
        async def close(self):
            pass
            
        async def set_keyspace(self, keyspace):
            self.keyspace = keyspace
    
    class MockAsyncCluster:
        def __init__(self, **kwargs):
            self._session = MockAsyncSession()
            
        async def connect(self, keyspace=None):
            if keyspace:
                await self._session.set_keyspace(keyspace)
            return self._session
            
        async def shutdown(self):
            pass
            
        async def __aenter__(self):
            return self
            
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.shutdown()
    
    # Use mocks
    AsyncCluster = MockAsyncCluster
    AsyncCassandraSession = MockAsyncSession
    from async_cassandra.exceptions import ConnectionError, QueryError
else:
    # Use real async-cassandra
    from async_cassandra import AsyncCluster, AsyncCassandraSession
    from async_cassandra.exceptions import ConnectionError, QueryError


# Pydantic models
class UserBase(BaseModel):
    """Base user model."""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(..., ge=0, le=150)


class UserCreate(UserBase):
    """User creation model."""
    pass


class UserUpdate(BaseModel):
    """User update model."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    age: Optional[int] = Field(None, ge=0, le=150)


class User(UserBase):
    """User response model."""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HealthCheck(BaseModel):
    """Health check response."""
    status: str
    cassandra_connected: bool
    timestamp: datetime


class PerformanceResult(BaseModel):
    """Performance test result."""
    total_time: float
    requests: int
    avg_time_per_request: float
    requests_per_second: float


# Global cluster and session
cluster: Optional[AsyncCluster] = None
session: Optional[AsyncCassandraSession] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global cluster, session

    # Startup
    cluster = AsyncCluster(
        contact_points=os.getenv("CASSANDRA_HOSTS", "localhost").split(","),
        port=int(os.getenv("CASSANDRA_PORT", "9042")),
    )

    session = await cluster.connect()

    if not TEST_MODE:
        # Create keyspace and table only in non-test mode
        await session.execute(
            """
            CREATE KEYSPACE IF NOT EXISTS fastapi_example
            WITH REPLICATION = {
                'class': 'SimpleStrategy',
                'replication_factor': 1
            }
        """
        )

        await session.set_keyspace("fastapi_example")

        await session.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                name TEXT,
                email TEXT,
                age INT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """
        )

        # Prepare statements
        app.state.insert_stmt = await session.prepare(
            """
            INSERT INTO users (id, name, email, age, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        )

        app.state.select_stmt = await session.prepare(
            """
            SELECT * FROM users WHERE id = ?
        """
        )

        app.state.update_stmt = await session.prepare(
            """
            UPDATE users
            SET name = ?, email = ?, age = ?, updated_at = ?
            WHERE id = ?
        """
        )

        app.state.delete_stmt = await session.prepare(
            """
            DELETE FROM users WHERE id = ?
        """
        )
    else:
        # In test mode, create mock prepared statements
        app.state.insert_stmt = Mock()
        app.state.select_stmt = Mock()
        app.state.update_stmt = Mock()
        app.state.delete_stmt = Mock()

    yield

    # Shutdown
    if session:
        await session.close()
    if cluster:
        await cluster.shutdown()


# Create FastAPI app
app = FastAPI(
    title="async-cassandra FastAPI Example",
    description="Example API using async-cassandra with FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)


# Dependency to get session
async def get_session() -> AsyncCassandraSession:
    """Get Cassandra session dependency."""
    if not session:
        raise HTTPException(status_code=503, detail="Database not available")
    return session


# Health check endpoint
@app.get("/health", response_model=HealthCheck)
async def health_check(session: AsyncCassandraSession = Depends(get_session)):
    """Check application health."""
    try:
        # Test database connection
        await session.execute("SELECT release_version FROM system.local")
        cassandra_connected = True
    except Exception:
        cassandra_connected = False

    return HealthCheck(
        status="healthy" if cassandra_connected else "unhealthy",
        cassandra_connected=cassandra_connected,
        timestamp=datetime.utcnow(),
    )


# Create user
@app.post("/users", response_model=User, status_code=201)
async def create_user(user: UserCreate, session: AsyncCassandraSession = Depends(get_session)):
    """Create a new user."""
    user_id = uuid.uuid4()
    now = datetime.utcnow()

    try:
        if TEST_MODE:
            # In test mode, store in memory
            session._users[str(user_id)] = {
                "id": user_id,
                "name": user.name,
                "email": user.email,
                "age": user.age,
                "created_at": now,
                "updated_at": now,
            }
        else:
            await session.execute(
                app.state.insert_stmt, (user_id, user.name, user.email, user.age, now, now)
            )

        return User(
            id=str(user_id),
            name=user.name,
            email=user.email,
            age=user.age,
            created_at=now,
            updated_at=now,
        )

    except QueryError as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")


# Get user by ID
@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str, session: AsyncCassandraSession = Depends(get_session)):
    """Get user by ID."""
    try:
        # Validate UUID
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    try:
        result = await session.execute(app.state.select_stmt if not TEST_MODE else f"SELECT * FROM users WHERE id = ?", [user_uuid])
        row = result.one()

        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        return User(
            id=str(row["id"]),
            name=row["name"],
            email=row["email"],
            age=row["age"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    except QueryError as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


# List users
@app.get("/users", response_model=List[User])
async def list_users(
    limit: int = Query(10, ge=1, le=100), session: AsyncCassandraSession = Depends(get_session)
):
    """List all users with pagination."""
    try:
        result = await session.execute(f"SELECT * FROM users LIMIT {limit}")

        users = []
        async for row in result:
            users.append(
                User(
                    id=str(row["id"]),
                    name=row["name"],
                    email=row["email"],
                    age=row["age"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return users

    except QueryError as e:
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


# Update user
@app.put("/users/{user_id}", response_model=User)
async def update_user(
    user_id: str, user_update: UserUpdate, session: AsyncCassandraSession = Depends(get_session)
):
    """Update user by ID."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    # Get existing user
    result = await session.execute(app.state.select_stmt if not TEST_MODE else f"SELECT * FROM users WHERE id = ?", [user_uuid])
    existing = result.one()

    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    # Update fields
    updated_name = user_update.name if user_update.name is not None else existing["name"]
    updated_email = user_update.email if user_update.email is not None else existing["email"]
    updated_age = user_update.age if user_update.age is not None else existing["age"]
    updated_at = datetime.utcnow()

    try:
        if TEST_MODE:
            # Update in memory
            session._users[str(user_uuid)] = {
                "id": user_uuid,
                "name": updated_name,
                "email": updated_email,
                "age": updated_age,
                "created_at": existing["created_at"],
                "updated_at": updated_at,
            }
        else:
            await session.execute(
                app.state.update_stmt, (updated_name, updated_email, updated_age, updated_at, user_uuid)
            )

        return User(
            id=str(user_uuid),
            name=updated_name,
            email=updated_email,
            age=updated_age,
            created_at=existing["created_at"],
            updated_at=updated_at,
        )

    except QueryError as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")


# Delete user
@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, session: AsyncCassandraSession = Depends(get_session)):
    """Delete user by ID."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    try:
        await session.execute(app.state.delete_stmt if not TEST_MODE else f"DELETE FROM users WHERE id = ?", [user_uuid])
    except QueryError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


# Performance test endpoints
@app.get("/performance/async", response_model=PerformanceResult)
async def async_performance_test(
    requests: int = Query(100, ge=1, le=1000), session: AsyncCassandraSession = Depends(get_session)
):
    """Test async performance with concurrent queries."""
    start_time = time.time()

    async def execute_query():
        result = await session.execute("SELECT * FROM users LIMIT 1")
        return result.one()

    # Execute queries concurrently
    await asyncio.gather(*[execute_query() for _ in range(requests)])

    total_time = time.time() - start_time

    return PerformanceResult(
        total_time=total_time,
        requests=requests,
        avg_time_per_request=total_time / requests,
        requests_per_second=requests / total_time,
    )


@app.get("/performance/sync", response_model=PerformanceResult)
async def sync_performance_test(requests: int = Query(100, ge=1, le=1000)):
    """Test sync performance (simulated) for comparison."""
    start_time = time.time()

    # Simulate sync queries with sleep
    for _ in range(requests):
        await asyncio.sleep(0.01)  # Simulate 10ms query time

    total_time = time.time() - start_time

    return PerformanceResult(
        total_time=total_time,
        requests=requests,
        avg_time_per_request=total_time / requests,
        requests_per_second=requests / total_time,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)