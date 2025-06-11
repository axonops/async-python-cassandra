# SELECT Query Retry Verification

## Summary

After thorough investigation of the async-cassandra codebase, I can confirm that **SELECTs ARE automatically retried** on read timeouts, as documented. Here's the evidence:

## 1. AsyncRetryPolicy Implementation

The `AsyncRetryPolicy` class in `/src/async_cassandra/retry_policy.py` explicitly handles read timeouts:

```python
def on_read_timeout(self, query, consistency, required_responses, 
                    received_responses, data_retrieved, retry_num):
    if retry_num >= self.max_retries:
        return self.RETHROW, None
    
    # If we got some data, retry might succeed
    if data_retrieved:
        return self.RETRY, consistency
    
    # If we got enough responses, retry at same consistency
    if received_responses >= required_responses:
        return self.RETRY, consistency
    
    # Otherwise, rethrow
    return self.RETHROW, None
```

This returns `RETRY` (value 0) in two scenarios:
- When `data_retrieved` is True
- When `received_responses >= required_responses`

## 2. Default Retry Policy Configuration

In `/src/async_cassandra/cluster.py`, the AsyncRetryPolicy is set as the default:

```python
if retry_policy is None:
    retry_policy = AsyncRetryPolicy()

# Later in cluster creation:
cluster_kwargs = {
    # ...
    "default_retry_policy": retry_policy,
    # ...
}
```

This means all queries executed through the cluster will use this retry policy by default.

## 3. How Retries Actually Work

The retry mechanism is handled by the underlying cassandra-driver:

1. When a query is executed via `session.execute_async()`, the driver creates a ResponseFuture
2. If a ReadTimeout occurs, the driver consults the retry policy's `on_read_timeout()` method
3. If the policy returns `RETRY`, the driver automatically retries the query
4. This happens transparently - the async-cassandra wrapper doesn't need to do anything special

## 4. Test Coverage

The retry behavior is tested in:

- `/tests/unit/test_retry_policy.py` - Tests the retry policy logic directly
- `/tests/integration/test_network_failures.py` - Tests retry behavior with actual network failures
- The documentation in `/docs/retry-policies.md` explicitly states SELECTs are automatically retried

## 5. Key Differences from Base Driver

The cassandra-driver's default `RetryPolicy` does NOT retry read timeouts by default (it returns RETHROW). The AsyncRetryPolicy improves on this by:

1. **Automatically retrying SELECTs** when it makes sense
2. **Respecting max_retries limit** to prevent infinite loops
3. **Adding idempotency checks for writes** while keeping reads automatic

## Conclusion

The documentation is correct: SELECT queries ARE automatically retried on read timeouts by the AsyncRetryPolicy. This happens at the driver level when the retry policy returns `RETRY` from its `on_read_timeout()` method. No explicit marking or configuration is needed for SELECT queries - they benefit from automatic retries out of the box.

The retry logic is:
- Retry if data was retrieved (partial success)
- Retry if enough responses were received
- Don't retry if max retries exceeded
- Don't retry if neither condition is met

This provides a good balance between resilience and avoiding unnecessary retries.