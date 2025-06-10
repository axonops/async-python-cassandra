# Architecture Overview

This document provides a detailed overview of the async-cassandra library architecture and how it integrates with the DataStax Cassandra driver.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution Architecture](#solution-architecture)
- [Component Overview](#component-overview)
- [Execution Flow](#execution-flow)
- [Performance Considerations](#performance-considerations)

## Problem Statement

The DataStax Cassandra Python driver uses a thread pool for I/O operations, which can create bottlenecks in async applications:

```mermaid
sequenceDiagram
    participant App as Async Application
    participant Driver as Cassandra Driver
    participant ThreadPool as Thread Pool
    participant Cassandra as Cassandra DB
    
    App->>Driver: execute(query)
    Driver->>ThreadPool: Submit to thread
    Note over ThreadPool: Thread blocked
    ThreadPool->>Cassandra: Send query
    Cassandra-->>ThreadPool: Response
    ThreadPool-->>Driver: Result
    Driver-->>App: Return result
    Note over App,ThreadPool: Thread pool can become bottleneck<br/>under high concurrency
```

## Solution Architecture

async-cassandra wraps the driver's async operations to provide true async/await support:

```mermaid
sequenceDiagram
    participant App as Async Application
    participant AsyncWrapper as async-cassandra
    participant Driver as Cassandra Driver
    participant EventLoop as Event Loop
    participant Cassandra as Cassandra DB
    
    App->>AsyncWrapper: await execute(query)
    AsyncWrapper->>Driver: execute_async(query)
    Note over AsyncWrapper: Create Future
    Driver->>Cassandra: Send query (non-blocking)
    AsyncWrapper-->>EventLoop: Register callback
    EventLoop-->>App: Control returned
    Note over App: Can handle other requests
    Cassandra-->>Driver: Response
    Driver-->>AsyncWrapper: Callback triggered
    AsyncWrapper-->>EventLoop: Set Future result
    EventLoop-->>App: Resume coroutine
```

## Component Overview

### 1. AsyncCluster

Manages cluster configuration and lifecycle:

```mermaid
classDiagram
    class AsyncCluster {
        -Cluster _cluster
        -bool _closed
        +create_with_auth(contact_points, username, password)
        +connect(keyspace) AsyncCassandraSession
        +shutdown()
    }
    
    class Cluster {
        <<DataStax Driver>>
        +connect()
        +shutdown()
        +metadata
    }
    
    AsyncCluster --> Cluster : wraps
```

### 2. AsyncCassandraSession

Provides async interface for query execution:

```mermaid
classDiagram
    class AsyncCassandraSession {
        -Session _session
        -bool _closed
        +execute(query, parameters) AsyncResultSet
        +execute_batch(batch_statement) AsyncResultSet
        +prepare(query) PreparedStatement
        +close()
    }
    
    class Session {
        <<DataStax Driver>>
        +execute_async()
        +prepare()
        +shutdown()
    }
    
    AsyncCassandraSession --> Session : wraps
```

### 3. AsyncResultHandler

Converts callbacks to async/await:

```mermaid
stateDiagram-v2
    [*] --> Created: ResponseFuture received
    Created --> WaitingForData: Callbacks registered
    WaitingForData --> FetchingPages: Data received
    FetchingPages --> FetchingPages: More pages available
    FetchingPages --> Complete: All pages fetched
    WaitingForData --> Error: Exception occurred
    Complete --> [*]: Future resolved
    Error --> [*]: Future rejected
```

## Execution Flow

### Query Execution

```mermaid
sequenceDiagram
    participant User as User Code
    participant Session as AsyncCassandraSession
    participant Handler as AsyncResultHandler
    participant Driver as Cassandra Driver
    participant DB as Cassandra
    
    User->>Session: await execute(query)
    Session->>Driver: execute_async(query)
    Driver-->>Session: ResponseFuture
    Session->>Handler: new AsyncResultHandler(ResponseFuture)
    Handler->>Handler: Register callbacks
    Session-->>User: Return Future
    
    Note over User,DB: Async execution in progress
    
    DB-->>Driver: Query result
    Driver-->>Handler: Trigger callback
    Handler->>Handler: Process result/pages
    Handler-->>User: Resolve Future with AsyncResultSet
```

### Batch Operations

```mermaid
sequenceDiagram
    participant App as Application
    participant Session as AsyncCassandraSession
    participant Batch as BatchStatement
    participant DB as Cassandra
    
    App->>Batch: Create BatchStatement
    App->>Batch: Add multiple statements
    App->>Session: await execute_batch(batch)
    Session->>DB: Execute batch atomically
    DB-->>Session: Batch result
    Session-->>App: Return AsyncResultSet
```

### Connection Pooling

**Important Note**: When using protocol v3+ (Cassandra 2.1+), the Python driver maintains exactly **one TCP connection per host** due to Python's Global Interpreter Lock (GIL). This is different from drivers in other languages (Java, C++) that can maintain multiple connections per host.

```mermaid
graph TB
    subgraph "AsyncCluster"
        CP[Connection Manager]
        LB[Load Balancer]
        RP[Retry Policy]
    end
    
    subgraph "Cassandra Nodes"
        N1[Node 1<br/>1 connection]
        N2[Node 2<br/>1 connection]
        N3[Node 3<br/>1 connection]
    end
    
    App[Application] --> CP
    CP --> LB
    LB -->|"1 TCP connection"| N1
    LB -->|"1 TCP connection"| N2
    LB -->|"1 TCP connection"| N3
    
    RP -.->|Retry Logic| LB
    
    Note[Each connection supports up to<br/>32,768 concurrent requests<br/>with protocol v3+]
```

For detailed information about connection pooling behavior and best practices, see our [Connection Pooling Documentation](connection-pooling.md).

## Performance Considerations

### 1. Connection Pool Efficiency

The async wrapper maintains the driver's connection pooling:

```mermaid
graph LR
    subgraph "Traditional Sync"
        S1[Request 1] --> T1[Thread 1]
        S2[Request 2] --> T2[Thread 2]
        S3[Request 3] --> T3[Thread 3]
        T1 --> DB1[(Cassandra)]
        T2 --> DB1
        T3 --> DB1
        Note1[Threads blocked during I/O]
    end
    
    subgraph "Async Wrapper"
        A1[Request 1] --> EL[Event Loop]
        A2[Request 2] --> EL
        A3[Request 3] --> EL
        EL --> CP[Connection Pool]
        CP --> DB2[(Cassandra)]
        Note2[Single thread, non-blocking]
    end
```

### 2. Concurrency Model

```mermaid
graph TB
    subgraph "Async Concurrency"
        EL[Event Loop]
        C1[Coroutine 1]
        C2[Coroutine 2]
        C3[Coroutine 3]
        
        EL --> C1
        EL --> C2
        EL --> C3
        
        C1 -.->|await| IO1[I/O Operation]
        C2 -.->|await| IO2[I/O Operation]
        C3 -.->|await| IO3[I/O Operation]
    end
    
    Note[All coroutines share same thread,<br/>switching context during I/O waits]
```

### 3. Resource Usage Comparison

```mermaid
graph LR
    subgraph "Sync Driver"
        direction TB
        ST[Threads: 100]
        SM[Memory: High]
        SC[Context Switches: Many]
    end
    
    subgraph "Async Wrapper"
        direction TB
        AT[Threads: 1-4]
        AM[Memory: Low]
        AC[Context Switches: Few]
    end
    
    ST --> |"Under Load"| SP[Performance Degradation]
    AT --> |"Under Load"| AP[Stable Performance]
```

## Best Practices

1. **Connection Management**: Create cluster and session at application startup
2. **Prepared Statements**: Use prepared statements for repeated queries
3. **Batch Operations**: Group related writes for better performance
4. **Error Handling**: Implement proper retry logic for transient failures
5. **Resource Cleanup**: Always close sessions and clusters properly

## Integration with FastAPI

```mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant FastAPI as FastAPI
    participant Deps as Dependencies
    participant Session as AsyncCassandraSession
    participant DB as Cassandra
    
    Client->>FastAPI: HTTP Request
    FastAPI->>Deps: Get session dependency
    Deps-->>FastAPI: Inject session
    FastAPI->>Session: await execute(query)
    Session->>DB: Async query
    DB-->>Session: Result
    Session-->>FastAPI: AsyncResultSet
    FastAPI-->>Client: HTTP Response
```

This architecture enables efficient, scalable applications that can handle thousands of concurrent requests without the thread pool bottlenecks of traditional synchronous drivers.