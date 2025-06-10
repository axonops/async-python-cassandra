"""
Async-aware retry policies for Cassandra operations.
"""

from typing import Optional, Tuple, Union

from cassandra.policies import RetryPolicy
from cassandra.query import ConsistencyLevel, SimpleStatement, PreparedStatement, BatchStatement


class AsyncRetryPolicy(RetryPolicy):
    """
    Retry policy for async Cassandra operations.

    This extends the base RetryPolicy with async-aware retry logic
    and configurable retry limits.
    """

    def __init__(self, max_retries: int = 3):
        """
        Initialize the retry policy.

        Args:
            max_retries: Maximum number of retry attempts.
        """
        super().__init__()
        self.max_retries = max_retries

    def on_read_timeout(
        self,
        query: Union[SimpleStatement, PreparedStatement, BatchStatement],
        consistency: ConsistencyLevel,
        required_responses: int,
        received_responses: int,
        data_retrieved: bool,
        retry_num: int,
    ) -> Tuple[int, Optional[ConsistencyLevel]]:
        """
        Handle read timeout.

        Args:
            query: The query statement that timed out.
            consistency: The consistency level of the query.
            required_responses: Number of responses required by consistency level.
            received_responses: Number of responses received before timeout.
            data_retrieved: Whether any data was retrieved.
            retry_num: Current retry attempt number.

        Returns:
            Tuple of (retry decision, consistency level to use).
        """
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

    def on_write_timeout(
        self,
        query: Union[SimpleStatement, PreparedStatement, BatchStatement],
        consistency: ConsistencyLevel,
        write_type: str,
        required_responses: int,
        received_responses: int,
        retry_num: int,
    ) -> Tuple[int, Optional[ConsistencyLevel]]:
        """
        Handle write timeout.

        Args:
            query: The query statement that timed out.
            consistency: The consistency level of the query.
            write_type: Type of write operation.
            required_responses: Number of responses required by consistency level.
            received_responses: Number of responses received before timeout.
            retry_num: Current retry attempt number.

        Returns:
            Tuple of (retry decision, consistency level to use).
        """
        if retry_num >= self.max_retries:
            return self.RETHROW, None

        # Only retry simple and batch writes
        if write_type in ("SIMPLE", "BATCH"):
            return self.RETRY, consistency

        return self.RETHROW, None

    def on_unavailable(
        self,
        query: Union[SimpleStatement, PreparedStatement, BatchStatement],
        consistency: ConsistencyLevel,
        required_replicas: int,
        alive_replicas: int,
        retry_num: int,
    ) -> Tuple[int, Optional[ConsistencyLevel]]:
        """
        Handle unavailable exception.

        Args:
            query: The query that failed.
            consistency: The consistency level of the query.
            required_replicas: Number of replicas required by consistency level.
            alive_replicas: Number of replicas that are alive.
            retry_num: Current retry attempt number.

        Returns:
            Tuple of (retry decision, consistency level to use).
        """
        if retry_num >= self.max_retries:
            return self.RETHROW, None

        # Try next host on first retry
        if retry_num == 0:
            return self.RETRY_NEXT_HOST, consistency

        # Retry with same consistency
        return self.RETRY, consistency

    def on_request_error(
        self, query: Union[SimpleStatement, PreparedStatement, BatchStatement], consistency: ConsistencyLevel, error: Exception, retry_num: int
    ) -> Tuple[int, Optional[ConsistencyLevel]]:
        """
        Handle request error.

        Args:
            query: The query that failed.
            consistency: The consistency level of the query.
            error: The error that occurred.
            retry_num: Current retry attempt number.

        Returns:
            Tuple of (retry decision, consistency level to use).
        """
        if retry_num >= self.max_retries:
            return self.RETHROW, None

        # Try next host for connection errors
        return self.RETRY_NEXT_HOST, consistency
