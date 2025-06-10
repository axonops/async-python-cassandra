"""
Test retry policy idempotency checks.
"""

import pytest
from unittest.mock import Mock
from cassandra.query import SimpleStatement, ConsistencyLevel
from async_cassandra.retry_policy import AsyncRetryPolicy


class TestRetryPolicyIdempotency:
    """Test that retry policy properly checks idempotency."""

    def test_write_timeout_idempotent_query(self):
        """Test that idempotent queries are retried on write timeout."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        # Create a mock query marked as idempotent
        query = Mock()
        query.is_idempotent = True
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="SIMPLE",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        assert decision == policy.RETRY
        assert consistency == ConsistencyLevel.ONE

    def test_write_timeout_non_idempotent_query(self):
        """Test that non-idempotent queries are NOT retried on write timeout."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        # Create a mock query marked as non-idempotent
        query = Mock()
        query.is_idempotent = False
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="SIMPLE",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        # Should NOT retry non-idempotent writes
        assert decision == policy.RETHROW
        assert consistency is None

    def test_write_timeout_no_idempotent_attribute(self):
        """Test behavior when query has no is_idempotent attribute."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        # Create a mock query without is_idempotent attribute
        query = Mock(spec=[])  # Empty spec means no attributes
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="SIMPLE",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        # Should retry if no is_idempotent attribute (backward compatibility)
        assert decision == policy.RETRY
        assert consistency == ConsistencyLevel.ONE

    def test_write_timeout_batch_idempotent(self):
        """Test that idempotent batch queries are retried."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        query = Mock()
        query.is_idempotent = True
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="BATCH",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        assert decision == policy.RETRY
        assert consistency == ConsistencyLevel.ONE

    def test_write_timeout_batch_non_idempotent(self):
        """Test that non-idempotent batch queries are NOT retried."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        query = Mock()
        query.is_idempotent = False
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="BATCH",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        assert decision == policy.RETHROW
        assert consistency is None

    def test_write_timeout_counter_update(self):
        """Test that counter updates are not retried."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        # Counter updates have write_type "COUNTER"
        query = Mock()
        query.is_idempotent = True  # Even if marked idempotent
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="COUNTER",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        # Counter updates should not be retried
        assert decision == policy.RETHROW
        assert consistency is None

    def test_real_simple_statement_idempotent(self):
        """Test with real SimpleStatement marked as idempotent."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        # Create real SimpleStatement
        query = SimpleStatement(
            "INSERT INTO users (id, name) VALUES (?, ?) IF NOT EXISTS",
            is_idempotent=True
        )
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="SIMPLE",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        assert decision == policy.RETRY
        assert consistency == ConsistencyLevel.ONE

    def test_real_simple_statement_non_idempotent(self):
        """Test with real SimpleStatement marked as non-idempotent."""
        policy = AsyncRetryPolicy(max_retries=3)
        
        # Create real SimpleStatement
        query = SimpleStatement(
            "UPDATE counters SET value = value + 1 WHERE id = ?",
            is_idempotent=False
        )
        
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="SIMPLE",
            required_responses=1,
            received_responses=0,
            retry_num=0
        )
        
        assert decision == policy.RETHROW
        assert consistency is None

    def test_max_retries_still_applies(self):
        """Test that max retries limit is still enforced for idempotent queries."""
        policy = AsyncRetryPolicy(max_retries=2)
        
        query = Mock()
        query.is_idempotent = True
        
        # Third retry should fail even for idempotent queries
        decision, consistency = policy.on_write_timeout(
            query=query,
            consistency=ConsistencyLevel.ONE,
            write_type="SIMPLE",
            required_responses=1,
            received_responses=0,
            retry_num=2  # Already retried twice
        )
        
        assert decision == policy.RETHROW
        assert consistency is None