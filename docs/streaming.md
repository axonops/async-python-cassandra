# Streaming Large Result Sets

When working with large datasets in Cassandra, loading all results into memory at once can cause performance issues or even out-of-memory errors. async-cassandra provides powerful streaming capabilities to efficiently process large result sets without overwhelming your application's memory.

## Table of Contents

- [Overview](#overview)
- [Basic Streaming](#basic-streaming)
- [Page-Based Processing](#page-based-processing)
- [Configuration Options](#configuration-options)
- [Progress Tracking](#progress-tracking)
- [Advanced Usage](#advanced-usage)
- [Performance Considerations](#performance-considerations)
- [Comparison with Regular Execution](#comparison-with-regular-execution)

## Overview

The streaming API allows you to:
- Process millions of rows without loading them all into memory
- Control fetch size to optimize network and memory usage
- Track progress with callbacks
- Cancel long-running operations
- Process data page-by-page for batch operations

## Basic Streaming

The simplest way to stream results is using `execute_stream()`:

```python
from async_cassandra import AsyncCluster, StreamConfig

async def process_large_table():
    cluster = AsyncCluster(['localhost'])
    session = await cluster.connect('my_keyspace')
    
    # Stream through a large result set
    result = await session.execute_stream(
        "SELECT * FROM large_table",
        stream_config=StreamConfig(fetch_size=5000)
    )
    
    # Process rows one at a time
    async for row in result:
        # Each row is fetched on-demand
        await process_row(row)
    
    await cluster.shutdown()
```

### With Prepared Statements

Streaming works seamlessly with prepared statements:

```python
# Prepare the statement
stmt = await session.prepare("SELECT * FROM users WHERE created_at > ?")

# Stream results with parameters
result = await session.execute_stream(
    stmt,
    parameters=[datetime(2024, 1, 1)],
    stream_config=StreamConfig(fetch_size=1000)
)

async for user in result:
    print(f"Processing user: {user.email}")
```

## Page-Based Processing

Sometimes you need to process data in batches rather than row-by-row:

```python
async def batch_process():
    result = await session.execute_stream(
        "SELECT * FROM events",
        stream_config=StreamConfig(fetch_size=1000)
    )
    
    # Process data page by page
    async for page in result.pages():
        print(f"Processing page {result.page_number} with {len(page)} rows")
        
        # Process entire page at once
        await bulk_process(page)
        
        # Access metadata
        print(f"Total rows fetched so far: {result.total_rows_fetched}")
```

## Configuration Options

The `StreamConfig` class provides fine-grained control:

```python
from async_cassandra import StreamConfig

config = StreamConfig(
    # Number of rows to fetch per page (default: 1000)
    fetch_size=5000,
    
    # Maximum number of pages to fetch (None = no limit)
    max_pages=10,
    
    # Progress callback function
    page_callback=lambda page_num, total_rows: 
        print(f"Fetched page {page_num}, total: {total_rows} rows")
)

result = await session.execute_stream(
    "SELECT * FROM large_table",
    stream_config=config
)
```

## Progress Tracking

For long-running queries, track progress with callbacks:

```python
import asyncio
from datetime import datetime

# Progress tracking
processed_rows = 0
start_time = datetime.now()

def progress_callback(page_number: int, total_rows: int):
    elapsed = (datetime.now() - start_time).total_seconds()
    rate = total_rows / elapsed if elapsed > 0 else 0
    print(f"Page {page_number}: {total_rows:,} rows fetched "
          f"({rate:.1f} rows/sec)")

# Configure streaming with progress tracking
config = StreamConfig(
    fetch_size=10000,
    page_callback=progress_callback
)

result = await session.execute_stream(
    "SELECT * FROM sensor_data",
    stream_config=config
)

async for row in result:
    processed_rows += 1
    await process_sensor_reading(row)

print(f"Processed {processed_rows:,} total rows")
```

## Advanced Usage

### Cancelling Long-Running Streams

```python
import asyncio

async def interruptible_stream():
    result = await session.execute_stream(
        "SELECT * FROM huge_table",
        stream_config=StreamConfig(fetch_size=5000)
    )
    
    try:
        async for row in result:
            if should_stop():  # Your condition
                result.cancel()
                break
            await process_row(row)
    except asyncio.CancelledError:
        print("Stream cancelled")
        result.cancel()
        raise
```

### Creating Streaming Statements

For more control, create streaming-optimized statements:

```python
from async_cassandra import create_streaming_statement
from cassandra import ConsistencyLevel

# Create a statement optimized for streaming
stmt = create_streaming_statement(
    "SELECT * FROM time_series_data WHERE date = ?",
    fetch_size=10000,
    consistency_level=ConsistencyLevel.LOCAL_ONE
)

# Use with execute_stream
result = await session.execute_stream(
    stmt,
    parameters=[date.today()]
)
```

### Memory-Efficient Export

Export large tables without memory issues:

```python
import csv
import aiofiles

async def export_to_csv(table_name: str, output_file: str):
    # Count total rows for progress
    count_result = await session.execute(f"SELECT COUNT(*) FROM {table_name}")
    total_rows = count_result.one()[0]
    
    # Stream all data
    result = await session.execute_stream(
        f"SELECT * FROM {table_name}",
        stream_config=StreamConfig(
            fetch_size=5000,
            page_callback=lambda p, t: print(
                f"Export progress: {t}/{total_rows} "
                f"({100*t/total_rows:.1f}%)"
            )
        )
    )
    
    # Write to CSV asynchronously
    async with aiofiles.open(output_file, 'w', newline='') as f:
        writer = None
        
        async for row in result:
            if writer is None:
                # Write header on first row
                fieldnames = row._fields
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                await f.write(','.join(fieldnames) + '\n')
            
            # Write row data
            row_dict = {field: getattr(row, field) for field in row._fields}
            await f.write(','.join(str(row_dict[f]) for f in row._fields) + '\n')
    
    print(f"Exported {result.total_rows_fetched} rows to {output_file}")
```

## Performance Considerations

### Choosing the Right Fetch Size

The fetch size affects both memory usage and performance:

```python
# Small fetch size: Less memory, more network round trips
small_config = StreamConfig(fetch_size=100)

# Large fetch size: More memory, fewer network round trips  
large_config = StreamConfig(fetch_size=10000)

# Adaptive fetch size based on row size
estimated_row_size = 1024  # bytes
available_memory = 100 * 1024 * 1024  # 100MB
optimal_fetch_size = available_memory // estimated_row_size

config = StreamConfig(fetch_size=min(optimal_fetch_size, 5000))
```

### Concurrent Stream Processing

Process multiple streams concurrently:

```python
async def process_partition(partition_key):
    stmt = await session.prepare(
        "SELECT * FROM events WHERE partition_key = ?"
    )
    
    result = await session.execute_stream(
        stmt,
        parameters=[partition_key],
        stream_config=StreamConfig(fetch_size=1000)
    )
    
    count = 0
    async for event in result:
        await process_event(event)
        count += 1
    
    return partition_key, count

# Process multiple partitions concurrently
partition_keys = ['A', 'B', 'C', 'D', 'E']
results = await asyncio.gather(*[
    process_partition(pk) for pk in partition_keys
])

for partition, count in results:
    print(f"Processed {count} events from partition {partition}")
```

## Comparison with Regular Execution

### When to Use Streaming

Use `execute_stream()` when:
- Result set is large (thousands or millions of rows)
- You want to process results incrementally
- Memory usage is a concern
- You need progress tracking
- Results might be cancelled mid-operation

### When to Use Regular Execute

Use regular `execute()` when:
- Result set is small (< 5000 rows)
- You need all results in memory at once
- You're doing random access on results
- Query has LIMIT clause

### Performance Comparison

```python
import time
import psutil
import os

async def compare_methods():
    process = psutil.Process(os.getpid())
    
    # Regular execution - loads all into memory
    start_memory = process.memory_info().rss / 1024 / 1024  # MB
    start_time = time.time()
    
    result = await session.execute("SELECT * FROM large_table LIMIT 100000")
    all_rows = result.all()
    
    regular_time = time.time() - start_time
    regular_memory = process.memory_info().rss / 1024 / 1024 - start_memory
    
    print(f"Regular execution: {regular_time:.2f}s, {regular_memory:.1f}MB")
    
    # Streaming - processes incrementally
    start_memory = process.memory_info().rss / 1024 / 1024
    start_time = time.time()
    row_count = 0
    
    result = await session.execute_stream(
        "SELECT * FROM large_table LIMIT 100000",
        stream_config=StreamConfig(fetch_size=1000)
    )
    
    async for row in result:
        row_count += 1
    
    stream_time = time.time() - start_time
    stream_memory = process.memory_info().rss / 1024 / 1024 - start_memory
    
    print(f"Streaming execution: {stream_time:.2f}s, {stream_memory:.1f}MB")
```

## Best Practices

1. **Always use streaming for unbounded queries** - Queries without LIMIT can return millions of rows

2. **Set appropriate fetch sizes** - Balance between memory usage and network efficiency

3. **Handle errors gracefully** - Network issues can interrupt streams:
   ```python
   try:
       async for row in result:
           await process_row(row)
   except Exception as e:
       logger.error(f"Stream interrupted at row {result.total_rows_fetched}: {e}")
       # Optionally resume from last position
   ```

4. **Monitor progress for long operations** - Keep users informed with callbacks

5. **Consider timeout settings** - Long-running streams might need increased timeouts:
   ```python
   result = await session.execute_stream(
       "SELECT * FROM huge_table",
       timeout=300.0,  # 5 minutes
       stream_config=StreamConfig(fetch_size=5000)
   )
   ```

6. **Use prepared statements** - Even more important with streaming for performance

## Examples

For complete working examples, see:
- [Basic streaming example](../examples/streaming_basic.py)
- [Export large table example](../examples/export_large_table.py)
- [Real-time data processing](../examples/realtime_processing.py)