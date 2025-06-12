# Acceptance Tests

This directory contains BDD (Behavior-Driven Development) acceptance tests that validate complete user workflows and scenarios for the async-cassandra library.

## Overview

These tests follow the Given-When-Then format to ensure the library meets user needs and provides a great developer experience. They test the library through the lens of real-world usage, primarily using the FastAPI example application.

## Test Categories

### 1. User Workflows (`test_user_workflows.py`)
- Creating and managing user profiles
- CRUD operations from a user perspective
- Data validation and error handling

### 2. Streaming Workflows (`test_streaming_workflows.py`)
- Handling large datasets efficiently
- Page-by-page data processing
- Memory-efficient operations
- Streaming performance characteristics

### 3. Performance Workflows (`test_performance_workflows.py`)
- High-concurrency scenarios
- Async vs sync performance comparison
- Batch operations efficiency
- Handling slow operations and timeouts

### 4. Monitoring Workflows (`test_monitoring_workflows.py`)
- Application health monitoring
- Performance metrics collection
- Operational visibility
- Graceful shutdown procedures

### 5. Error Handling Workflows (`test_error_handling_workflows.py`)
- Validation error messages
- Resource not found scenarios
- Concurrent modification handling
- Edge cases and boundary conditions

## Running Acceptance Tests

```bash
# Run all acceptance tests
pytest tests/acceptance/ -m acceptance

# Run with verbose output to see Given-When-Then scenarios
pytest tests/acceptance/ -m acceptance -v

# Run a specific workflow category
pytest tests/acceptance/test_user_workflows.py -v

# Run acceptance tests along with other tests
pytest tests/ -m "acceptance or integration"
```

## Writing New Acceptance Tests

When adding new acceptance tests, follow these guidelines:

1. **Use Given-When-Then format** in test names and docstrings
2. **Focus on user perspective** - what would a developer using this library want to achieve?
3. **Test complete workflows** rather than individual functions
4. **Use natural language** that stakeholders can understand
5. **Validate business value** - ensure tests verify that user goals are met

Example structure:
```python
@pytest.mark.asyncio
async def test_user_achieves_specific_goal(self, test_client):
    """
    GIVEN initial context or preconditions
    WHEN user performs specific action
    THEN expected outcome should occur
    """
    # Given: Set up initial state
    
    # When: Perform user action
    
    # Then: Verify expected outcome
```

## Integration with CI/CD

These acceptance tests should be run as part of the continuous integration pipeline to ensure that changes don't break user workflows. They complement unit and integration tests by validating the complete user experience.