# Metrics and Observability

## Overview

The async-cassandra library provides comprehensive metrics and observability features to help you monitor performance, track errors, and maintain the health of your Cassandra applications in production.

## Key Features

- **🔍 Query Performance Tracking**: Latency, throughput, and success rates
- **📊 Connection Health Monitoring**: Real-time connection status
- **🚨 Error Analysis**: Detailed error categorization and tracking
- **📈 Prometheus Integration**: Industry-standard metrics export
- **🎯 Custom Metrics**: Extensible framework for application-specific metrics
- **⚡ Low Overhead**: Minimal performance impact on your application

## Quick Start

### Basic Setup

```python
from async_cassandra import AsyncCluster, create_metrics_system

# Create metrics system
metrics = create_metrics_system(
    backend="memory",           # For development
    prometheus_enabled=True     # For production
)

# Create cluster and session with metrics
cluster = AsyncCluster(contact_points=["localhost"])
session = await cluster.connect()

# Enable metrics collection
session._metrics = metrics

# All queries are now automatically tracked!
await session.execute("SELECT * FROM users")
```

### View Metrics

```python
# Get real-time statistics
for collector in metrics.collectors:
    stats = await collector.get_stats()
    print(f"Average query time: {stats['query_performance']['avg_duration_ms']:.2f}ms")
    print(f"Success rate: {stats['query_performance']['success_rate']:.2%}")
```

## Metrics Types

### Query Performance Metrics

| Metric | Description | Type |
|--------|-------------|------|
| `cassandra_query_duration_seconds` | Query execution time | Histogram |
| `cassandra_queries_total` | Total number of queries | Counter |
| `cassandra_query_result_size` | Number of rows returned | Histogram |

**Labels**: `query_type` (prepared/simple), `success` (success/failure)

### Connection Health Metrics

| Metric | Description | Type |
|--------|-------------|------|
| `cassandra_connection_healthy` | Connection health status | Gauge |
| `cassandra_connection_response_time` | Connection response time | Gauge |

**Labels**: `host`

### Error Metrics

| Metric | Description | Type |
|--------|-------------|------|
| `cassandra_errors_total` | Total number of errors | Counter |

**Labels**: `error_type` (InvalidRequest, Timeout, etc.)

## Configuration Options

### Memory Backend (Development)

```python
metrics = create_metrics_system(backend="memory")
```

- Stores metrics in memory
- Great for development and testing
- Provides detailed statistics via `get_stats()`
- Configurable retention limit

### Prometheus Backend (Production)

```python
metrics = create_metrics_system(
    backend="memory",
    prometheus_enabled=True
)

# Start Prometheus HTTP server
from prometheus_client import start_http_server
start_http_server(8000)
```

- Industry-standard metrics format
- Compatible with Grafana dashboards
- Supports alerting and monitoring
- Metrics available at `/metrics` endpoint

## Integration Examples

### FastAPI Integration

```python
from fastapi import FastAPI
from async_cassandra import AsyncCluster, create_metrics_system

app = FastAPI()
metrics = create_metrics_system(prometheus_enabled=True)

@app.on_event("startup")
async def startup():
    global cluster, session
    cluster = AsyncCluster(contact_points=["localhost"])
    session = await cluster.connect()
    session._metrics = metrics  # Enable metrics

@app.get("/metrics/stats")
async def get_metrics():
    """Endpoint to view current metrics."""
    stats = {}
    for collector in metrics.collectors:
        collector_stats = await collector.get_stats()
        stats.update(collector_stats)
    return stats

# All database queries automatically tracked!
@app.get("/users/{user_id}")
async def get_user(user_id: str):
    # Must use prepared statement for parameterized queries
    stmt = await session.prepare("SELECT * FROM users WHERE id = ?")
    result = await session.execute(stmt, [user_id])
    return {"user": result.one()}
```

### Custom Metrics Collection

```python
from async_cassandra.metrics import MetricsCollector, QueryMetrics

class CustomMetricsCollector(MetricsCollector):
    """Custom collector for application-specific metrics."""
    
    def __init__(self):
        self.slow_queries = []
        
    async def record_query(self, metrics: QueryMetrics):
        # Track slow queries
        if metrics.duration > 0.1:  # 100ms threshold
            self.slow_queries.append(metrics)
            
        # Send to external monitoring system
        await self.send_to_datadog(metrics)
    
    async def send_to_datadog(self, metrics):
        # Implementation for DataDog, New Relic, etc.
        pass
```

## Monitoring and Alerting

### Grafana Dashboard

We provide a pre-built Grafana dashboard with:

- **Query Performance Panel**: Latency trends and throughput
- **Error Rate Panel**: Error categorization and trends  
- **Connection Health Panel**: Real-time connection status
- **Query Volume Panel**: Request patterns and peaks

Import from: `examples/monitoring/grafana_dashboard.json`

### Prometheus Alerts

Example alerting rules:

```yaml
groups:
  - name: cassandra.rules
    rules:
      - alert: HighCassandraQueryLatency
        expr: histogram_quantile(0.95, cassandra_query_duration_seconds_bucket) > 0.1
        for: 2m
        annotations:
          summary: "High Cassandra query latency detected"
          
      - alert: CassandraConnectionUnhealthy
        expr: cassandra_connection_healthy == 0
        for: 30s
        annotations:
          summary: "Cassandra connection unhealthy"
```

## Performance Impact

The metrics system is designed for minimal overhead:

- **< 0.1ms** additional latency per query
- **< 10MB** memory usage for 10,000 queries
- **Asynchronous** recording to avoid blocking queries
- **Configurable** sampling rates for high-traffic applications

## Best Practices

### 1. Use Appropriate Backends

- **Development**: Memory backend for debugging
- **Production**: Prometheus backend for monitoring
- **High Traffic**: Consider sampling to reduce overhead

### 2. Monitor Key Metrics

Focus on these critical metrics:

```python
# Essential health checks
success_rate = stats['query_performance']['success_rate']
avg_latency = stats['query_performance']['avg_duration_ms']
error_rate = len(stats['error_summary'])

# Alert thresholds
assert success_rate > 0.95  # 95% success rate
assert avg_latency < 50     # 50ms average latency
assert error_rate < 10      # < 10 errors/minute
```

### 3. Set Up Alerting

Configure alerts for:
- Query latency > 100ms (95th percentile)
- Success rate < 95%
- Connection failures
- Error rate > 5 errors/minute

### 4. Regular Review

- Weekly performance reviews
- Trend analysis for capacity planning
- Query optimization based on slow query logs
- Connection pool tuning

## Troubleshooting

### Common Issues

**High Latency**:
```python
# Check for slow queries
slow_queries = [q for q in metrics.query_metrics if q.duration > 0.1]
for query in slow_queries:
    print(f"Slow query: {query.query_hash} - {query.duration:.3f}s")
```

**Connection Issues**:
```python
# Check connection health
for host, health in stats['connection_health'].items():
    if not health['healthy']:
        print(f"Unhealthy connection: {host}")
```

**Memory Usage**:
```python
# Monitor metrics memory usage
metrics_count = len(metrics.collectors[0].query_metrics)
if metrics_count > 50000:
    print("Consider increasing retention limits or sampling")
```

## Advanced Configuration

### Custom Query Normalization

```python
def custom_normalize_query(query: str) -> str:
    """Custom query normalization for better grouping."""
    # Remove table names for multi-tenant applications
    import re
    normalized = re.sub(r'FROM \w+_tenant_\d+', 'FROM tenant_table', query)
    return normalized

# Apply custom normalization
metrics.collectors[0]._normalize_query = custom_normalize_query
```

### Selective Monitoring

```python
class SelectiveMetricsCollector(MetricsCollector):
    """Only collect metrics for specific query types."""
    
    async def record_query(self, metrics: QueryMetrics):
        # Only monitor SELECT queries
        if 'SELECT' in metrics.query_hash.upper():
            await super().record_query(metrics)
```

## Next Steps

1. **Set up basic monitoring** with memory backend
2. **Enable Prometheus** for production environments  
3. **Import Grafana dashboard** for visualization
4. **Configure alerting** rules for your thresholds
5. **Review metrics regularly** for optimization opportunities

For more examples, see:
- `examples/metrics_example.py` - Complete working example
- `examples/monitoring/` - Dashboard and alerting configurations
- Integration examples in the `examples/fastapi_app/` directory