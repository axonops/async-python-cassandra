# Configuring the Cassandra Driver Thread Pool

## Overview

The DataStax Cassandra Python driver uses a thread pool for executing I/O operations. This document explains how to configure the thread pool size and the implications of different configurations.

## Default Configuration

By default, the cassandra-driver creates an executor with 2-4 threads (depending on the number of CPU cores):

```python
# Default behavior in cassandra-driver
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

# The driver calculates threads as:
num_threads = min(4, multiprocessing.cpu_count() * 2)
```

On most systems:
- 1 CPU core: 2 threads
- 2+ CPU cores: 4 threads

## How to Configure Thread Pool Size

### Method 1: Configure the Cluster Executor

```python
from concurrent.futures import ThreadPoolExecutor
from async_cassandra import AsyncCluster

# Create a custom executor with more threads
custom_executor = ThreadPoolExecutor(max_workers=16)

# Pass it to the cluster
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=16,  # This sets the executor thread count
    # OR use a custom executor directly:
    # executor=custom_executor
)
```

### Method 2: Set Global Default

```python
from cassandra.cluster import Cluster

# Set default for all clusters
Cluster.executor_threads = 16

# Now all clusters will use 16 threads
cluster = AsyncCluster(['localhost'])
```

## Thread Pool Size Considerations

### When to Increase Thread Pool Size

**Increase threads when:**
- You have high query concurrency (100s of concurrent queries)
- Your queries have high latency (e.g., cross-region queries)
- You're seeing queries queuing up waiting for threads
- You have sufficient CPU and memory resources

**Example calculation:**
```python
# If average query takes 50ms and you need 1000 queries/second:
# Required threads = (queries_per_second * avg_query_time_seconds)
# Required threads = 1000 * 0.05 = 50 threads

cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=50
)
```

### When NOT to Increase Thread Pool Size

**Keep default size when:**
- You have low query concurrency (<50 concurrent queries)
- Your application is memory-constrained
- You're running on systems with limited CPU cores
- Your queries are already fast (<10ms)

## Performance Impact

### Memory Usage

Each thread consumes memory for:
- Thread stack: ~1MB (configurable via `ulimit -s`)
- Thread-local storage: ~512KB-1MB
- Total per thread: ~1.5-2MB

**Example memory calculation:**
```python
# 16 threads = ~32MB additional memory
# 50 threads = ~100MB additional memory
# 100 threads = ~200MB additional memory
```

### CPU Overhead

More threads mean:
- More context switching
- Higher GIL contention
- Increased scheduler overhead

**Benchmarking example:**
```python
import time
import asyncio
from async_cassandra import AsyncCluster

async def benchmark_thread_pool(thread_count):
    cluster = AsyncCluster(
        contact_points=['localhost'],
        executor_threads=thread_count
    )
    session = await cluster.connect()
    
    # Run 1000 concurrent queries
    start = time.time()
    tasks = []
    for _ in range(1000):
        tasks.append(session.execute("SELECT * FROM system.local"))
    
    await asyncio.gather(*tasks)
    duration = time.time() - start
    
    await session.close()
    await cluster.shutdown()
    
    return duration

# Test different thread pool sizes
for threads in [4, 8, 16, 32, 64]:
    duration = await benchmark_thread_pool(threads)
    print(f"{threads} threads: {duration:.2f}s")
```

## Monitoring Thread Pool Usage

### Check Current Configuration

```python
from async_cassandra import AsyncCluster

cluster = AsyncCluster(['localhost'])
print(f"Executor threads: {cluster.executor_threads}")
print(f"Executor type: {type(cluster.executor)}")
```

### Monitor Thread Pool Saturation

```python
import asyncio
from async_cassandra import AsyncCluster

async def monitor_executor(cluster):
    """Monitor executor queue depth"""
    executor = cluster.executor
    
    while True:
        # Check pending tasks in executor
        pending = executor._work_queue.qsize()
        active = executor._threads
        
        print(f"Pending tasks: {pending}, Active threads: {len(active)}")
        
        if pending > 10:
            print("WARNING: Thread pool may be saturated!")
        
        await asyncio.sleep(1)
```

## Best Practices

### 1. Start Conservative
```python
# Start with default and increase if needed
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=8  # 2x default
)
```

### 2. Monitor and Adjust
```python
# Use metrics to guide configuration
from async_cassandra import AsyncCluster, MetricsCollector

metrics = MetricsCollector()
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=16,
    metrics_collector=metrics
)

# Monitor query latencies and queue depths
# Adjust threads based on actual usage
```

### 3. Consider Connection Pool Size
```python
# Thread pool should be >= connection pool
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=32,
    protocol_version=4,
    # Each host can have up to core_connections_per_host
    core_connections_per_host=8,
)
```

### 4. Use Connection Pooling Wisely
```python
# Don't create too many connections per thread
# Rough formula: executor_threads >= total_connections / 4

num_hosts = 3
connections_per_host = 8
total_connections = num_hosts * connections_per_host  # 24

# Need at least 6-8 executor threads
cluster = AsyncCluster(
    contact_points=['host1', 'host2', 'host3'],
    executor_threads=8,
    core_connections_per_host=8
)
```

## Common Pitfalls

### 1. Too Many Threads
```python
# DON'T: Create hundreds of threads
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=500  # Too many!
)

# Problems:
# - High memory usage (1GB+)
# - Excessive context switching
# - GIL contention
# - Diminishing returns
```

### 2. Thread Starvation
```python
# DON'T: Too few threads for workload
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=2  # Default might be too low
)

# If running 100 concurrent queries:
# - Only 2 can execute at once
# - Others queue up
# - Latency increases dramatically
```

### 3. Mismatched Configuration
```python
# DON'T: More connections than threads
cluster = AsyncCluster(
    contact_points=['localhost'] * 10,  # 10 hosts
    executor_threads=4,  # Only 4 threads
    core_connections_per_host=8  # 80 total connections!
)

# Connections will be underutilized
```

## Recommendations by Use Case

### Web Application (FastAPI/Flask)
```python
# Moderate concurrency, latency-sensitive
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=16,  # 4x default
    request_timeout=5.0
)
```

### Batch Processing
```python
# High throughput, less latency-sensitive
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=32,  # Handle many concurrent batches
    request_timeout=30.0
)
```

### Microservice
```python
# Limited resources, predictable load
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=8,  # Conservative
    request_timeout=2.0
)
```

### Data Analytics
```python
# Large queries, high memory usage
cluster = AsyncCluster(
    contact_points=['localhost'],
    executor_threads=8,  # Keep low to save memory
    request_timeout=60.0
)
```

## Conclusion

The thread pool size is a critical tuning parameter that affects:
- **Concurrency**: How many queries can execute simultaneously
- **Memory usage**: Each thread costs ~2MB
- **CPU overhead**: More threads = more context switching
- **Latency**: Too few threads = queries queue up

**General guidelines:**
- Start with 2-4x the default (8-16 threads)
- Monitor queue depth and latency
- Increase gradually based on metrics
- Consider memory and CPU constraints
- Match to your connection pool configuration

Remember: The async-cassandra wrapper doesn't eliminate the thread pool - it makes it work better with async Python applications. Understanding and configuring the thread pool properly is essential for optimal performance.