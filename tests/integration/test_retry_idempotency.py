"""
Integration tests for retry policy idempotency behavior.
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from cassandra import WriteTimeout
from cassandra.query import BatchStatement, BatchType, SimpleStatement


class TestRetryIdempotencyIntegration:
    """Test retry policy idempotency in real scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_non_idempotent_insert_not_retried(self, cassandra_session):
        """Test that non-idempotent INSERT is not retried on timeout."""
        # Clean up table
        await cassandra_session.execute("TRUNCATE users")

        user_id = uuid.uuid4()

        # Create a non-idempotent INSERT (default is_idempotent=False)
        insert_stmt = SimpleStatement(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)"
        )
        # Verify default is False (not idempotent)
        assert insert_stmt.is_idempotent is False

        # Mock execute_async to simulate a write timeout
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with WriteTimeout
                future = Mock()
                future.result.side_effect = WriteTimeout(
                    "Write timeout",
                    consistency=1,
                    received_responses=0,
                    required_responses=1,
                    write_type="SIMPLE",
                )
                return future
            # Should not reach here if retry policy works correctly
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should raise WriteTimeout without retry
            with pytest.raises(WriteTimeout):
                await cassandra_session.execute(
                    insert_stmt, [user_id, "Test User", "test@example.com", 25]
                )

        # Verify only one attempt was made (no retry)
        assert call_count == 1

        # Verify no data was inserted
        result = await cassandra_session.execute("SELECT * FROM users WHERE id = ?", [user_id])
        assert result.one() is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_idempotent_insert_is_retried(self, cassandra_session):
        """Test that idempotent INSERT is retried on timeout."""
        # Clean up table
        await cassandra_session.execute("TRUNCATE users")

        user_id = uuid.uuid4()

        # Create an idempotent INSERT with IF NOT EXISTS
        insert_stmt = SimpleStatement(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?) IF NOT EXISTS",
            is_idempotent=True,  # Explicitly mark as idempotent
        )

        # Mock execute_async to simulate a write timeout on first attempt
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with WriteTimeout
                future = Mock()
                future.result.side_effect = WriteTimeout(
                    "Write timeout",
                    consistency=1,
                    received_responses=0,
                    required_responses=1,
                    write_type="SIMPLE",
                )
                return future
            # Second call succeeds
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should succeed after retry
            result = await cassandra_session.execute(
                insert_stmt, [user_id, "Test User", "test@example.com", 25]
            )
            # IF NOT EXISTS returns [applied] column
            assert result.one().applied is True

        # Verify retry happened
        assert call_count == 2

        # Verify data was inserted
        result = await cassandra_session.execute("SELECT * FROM users WHERE id = ?", [user_id])
        row = result.one()
        assert row is not None
        assert row.name == "Test User"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_batch_without_idempotent_not_retried(self, cassandra_session):
        """Test that batch statements without is_idempotent are not retried."""
        # Clean up table
        await cassandra_session.execute("TRUNCATE users")

        # Prepare insert statement
        insert_stmt = await cassandra_session.prepare(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)"
        )

        # Create batch without setting is_idempotent
        batch = BatchStatement(batch_type=BatchType.LOGGED)
        # Default is_idempotent should be None
        assert getattr(batch, "is_idempotent", None) is None

        user_ids = [uuid.uuid4() for _ in range(3)]
        for i, user_id in enumerate(user_ids):
            batch.add(insert_stmt, (user_id, f"User{i}", f"user{i}@example.com", 20 + i))

        # Mock to simulate timeout
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and isinstance(statement, BatchStatement):
                future = Mock()
                future.result.side_effect = WriteTimeout(
                    "Write timeout",
                    consistency=1,
                    received_responses=0,
                    required_responses=1,
                    write_type="BATCH",
                )
                return future
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            with pytest.raises(WriteTimeout):
                await cassandra_session.execute_batch(batch)

        # Verify only one attempt (no retry)
        assert call_count == 1

        # Verify no data was inserted
        for user_id in user_ids:
            result = await cassandra_session.execute("SELECT * FROM users WHERE id = ?", [user_id])
            assert result.one() is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_counter_update_never_retried(self, cassandra_session):
        """Test that counter updates are never retried even if marked idempotent."""
        # Create counter table
        await cassandra_session.execute(
            """
            CREATE TABLE IF NOT EXISTS counters (
                id UUID PRIMARY KEY,
                count counter
            )
        """
        )

        counter_id = uuid.uuid4()

        # Counter update - even if someone incorrectly marks it idempotent
        update_stmt = SimpleStatement(
            "UPDATE counters SET count = count + 1 WHERE id = ?",
            is_idempotent=True,  # Wrong! But should still not retry
        )

        # Mock to simulate timeout
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                future = Mock()
                future.result.side_effect = WriteTimeout(
                    "Write timeout",
                    consistency=1,
                    received_responses=0,
                    required_responses=1,
                    write_type="COUNTER",  # Counter write type
                )
                return future
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            with pytest.raises(WriteTimeout):
                await cassandra_session.execute(update_stmt, [counter_id])

        # Verify only one attempt (no retry for COUNTER write type)
        assert call_count == 1

        # Cleanup
        await cassandra_session.execute("DROP TABLE counters")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_prepared_statement_idempotency(self, cassandra_session):
        """Test that prepared statements respect idempotency settings."""
        # Clean up table
        await cassandra_session.execute("TRUNCATE users")

        # Prepare statement
        prepared = await cassandra_session.prepare(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)"
        )

        # Prepared statements also default to is_idempotent=False
        assert prepared.is_idempotent is False

        user_id = uuid.uuid4()

        # Mock to simulate timeout
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                future = Mock()
                future.result.side_effect = WriteTimeout(
                    "Write timeout",
                    consistency=1,
                    received_responses=0,
                    required_responses=1,
                    write_type="SIMPLE",
                )
                return future
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should not retry
            with pytest.raises(WriteTimeout):
                await cassandra_session.execute(
                    prepared, [user_id, "Test User", "test@example.com", 25]
                )

        # Verify only one attempt
        assert call_count == 1

        # Now mark the prepared statement as idempotent
        prepared.is_idempotent = True
        call_count = 0

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should retry and succeed
            await cassandra_session.execute(
                prepared, [user_id, "Test User", "test@example.com", 25]
            )

        # Verify retry happened
        assert call_count == 2
