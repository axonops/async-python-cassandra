"""
Integration tests specifically for SELECT query retry behavior.
This is critical functionality that must be thoroughly tested.
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from cassandra import ReadTimeout, Unavailable
from cassandra.query import SimpleStatement


class TestSelectRetryBehavior:
    """Test SELECT query retry behavior in various scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_select_retried_on_read_timeout(self, cassandra_session):
        """Test that SELECT queries are automatically retried on read timeout."""
        # Insert test data
        user_id = uuid.uuid4()
        await cassandra_session.execute(
            "INSERT INTO users (id, name, email, age) VALUES (%s, %s, %s, %s)",
            [user_id, "Test User", "test@example.com", 25]
        )

        # Mock execute_async to simulate a read timeout on first attempt
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with ReadTimeout
                future = Mock()
                future.result.side_effect = ReadTimeout(
                    "Read timeout",
                    consistency=1,
                    received_responses=1,
                    required_responses=2,
                    data_retrieved=True,  # Some data was retrieved
                )
                return future
            # Second call succeeds
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should succeed after retry
            result = await cassandra_session.execute(
                "SELECT * FROM users WHERE id = %s", [user_id]
            )
            row = result.one()
            assert row is not None
            assert row.name == "Test User"

        # Verify retry happened
        assert call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_select_retried_with_simple_statement(self, cassandra_session):
        """Test that SELECT with SimpleStatement is retried."""
        # Insert test data
        user_id = uuid.uuid4()
        await cassandra_session.execute(
            "INSERT INTO users (id, name, email, age) VALUES (%s, %s, %s, %s)",
            [user_id, "Test User", "test@example.com", 25]
        )

        # Create SimpleStatement - should NOT need is_idempotent for SELECT
        select_stmt = SimpleStatement(
            "SELECT * FROM users WHERE id = %s"
        )
        # Verify is_idempotent is not set (defaults to False)
        assert select_stmt.is_idempotent is False

        # Mock to simulate timeout
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                future = Mock()
                future.result.side_effect = ReadTimeout(
                    "Read timeout",
                    consistency=1,
                    received_responses=0,
                    required_responses=1,
                    data_retrieved=False,
                )
                return future
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should succeed after retry even without is_idempotent=True
            result = await cassandra_session.execute(select_stmt, [user_id])
            row = result.one()
            assert row is not None
            assert row.name == "Test User"

        # Verify retry happened
        assert call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_select_max_retries_respected(self, cassandra_session):
        """Test that SELECT queries respect max_retries limit."""
        user_id = uuid.uuid4()

        # Mock to always fail
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Always fail with ReadTimeout
            future = Mock()
            future.result.side_effect = ReadTimeout(
                "Read timeout",
                consistency=1,
                received_responses=0,
                required_responses=1,
                data_retrieved=False,
            )
            return future

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should eventually fail after max retries (default is 3)
            with pytest.raises(ReadTimeout):
                await cassandra_session.execute(
                    "SELECT * FROM users WHERE id = %s", [user_id]
                )

        # Verify it tried max_retries + 1 times (initial + 3 retries)
        assert call_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_select_retried_on_unavailable(self, cassandra_session):
        """Test that SELECT queries are retried on Unavailable exception."""
        user_id = uuid.uuid4()

        # Mock to simulate Unavailable on first attempt
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with Unavailable
                future = Mock()
                future.result.side_effect = Unavailable(
                    "Not enough replicas",
                    consistency=1,
                    required_replicas=3,
                    alive_replicas=1,
                )
                return future
            # Second call succeeds
            return original_execute_async(statement, parameters, *args, **kwargs)

        # Insert data first (before mocking)
        await cassandra_session.execute(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)",
            [user_id, "Test User", "test@example.com", 25]
        )

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should succeed after retry
            result = await cassandra_session.execute(
                "SELECT * FROM users WHERE id = %s", [user_id]
            )
            row = result.one()
            assert row is not None
            assert row.name == "Test User"

        # Verify retry happened
        assert call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_prepared_select_retried(self, cassandra_session):
        """Test that prepared SELECT statements are retried."""
        # Insert test data
        user_id = uuid.uuid4()
        await cassandra_session.execute(
            "INSERT INTO users (id, name, email, age) VALUES (%s, %s, %s, %s)",
            [user_id, "Test User", "test@example.com", 25]
        )

        # Prepare SELECT statement
        prepared = await cassandra_session.prepare(
            "SELECT * FROM users WHERE id = %s"
        )
        # Should not need is_idempotent for SELECT
        assert prepared.is_idempotent is False

        # Mock to simulate timeout
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                future = Mock()
                future.result.side_effect = ReadTimeout(
                    "Read timeout",
                    consistency=1,
                    received_responses=1,
                    required_responses=2,
                    data_retrieved=True,
                )
                return future
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should succeed after retry
            result = await cassandra_session.execute(prepared, [user_id])
            row = result.one()
            assert row is not None
            assert row.name == "Test User"

        # Verify retry happened
        assert call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_select_with_allow_filtering_retried(self, cassandra_session):
        """Test that SELECT with ALLOW FILTERING is retried."""
        # Insert test data
        for i in range(5):
            await cassandra_session.execute(
                "INSERT INTO users (id, name, email, age) VALUES (%s, %s, %s, %s)",
                [uuid.uuid4(), f"User{i}", f"user{i}@example.com", 20 + i]
            )

        # Mock to simulate timeout
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                future = Mock()
                future.result.side_effect = ReadTimeout(
                    "Read timeout",
                    consistency=1,
                    received_responses=0,
                    required_responses=1,
                    data_retrieved=False,
                )
                return future
            return original_execute_async(statement, parameters, *args, **kwargs)

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should succeed after retry
            result = await cassandra_session.execute(
                "SELECT * FROM users WHERE age > 21 ALLOW FILTERING"
            )
            rows = result.all()
            assert len(rows) >= 3  # Users with age > 21

        # Verify retry happened
        assert call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_select_not_retried_when_data_not_retrieved(self, cassandra_session):
        """Test that SELECT is not retried when no data retrieved and insufficient responses."""
        user_id = uuid.uuid4()

        # Mock to simulate timeout with no data retrieved
        original_execute_async = cassandra_session._session.execute_async
        call_count = 0

        def mock_execute_async(statement, parameters=None, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Always fail with no data retrieved and insufficient responses
            future = Mock()
            future.result.side_effect = ReadTimeout(
                "Read timeout",
                consistency=1,
                received_responses=0,
                required_responses=3,  # Required > received
                data_retrieved=False,  # No data retrieved
            )
            return future

        with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
            # Should fail immediately without retry
            with pytest.raises(ReadTimeout):
                await cassandra_session.execute(
                    "SELECT * FROM users WHERE id = %s", [user_id]
                )

        # Verify no retry happened (only initial attempt)
        assert call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complex_select_queries_retried(self, cassandra_session):
        """Test various complex SELECT queries are retried."""
        # Test data
        user_id = uuid.uuid4()
        await cassandra_session.execute(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)",
            [user_id, "Test User", "test@example.com", 25]
        )

        queries = [
            # Simple SELECT
            ("SELECT * FROM users WHERE id = %s", [user_id]),
            # SELECT with specific columns
            ("SELECT name, email FROM users WHERE id = ?", [user_id]),
            # SELECT with LIMIT
            ("SELECT * FROM users LIMIT 10", None),
            # SELECT with ORDER BY (requires ALLOW FILTERING or proper key)
            ("SELECT * FROM users WHERE id = %s ORDER BY id", [user_id]),
            # COUNT query
            ("SELECT COUNT(*) FROM users", None),
        ]

        for query, params in queries:
            # Mock to simulate timeout
            original_execute_async = cassandra_session._session.execute_async
            call_count = 0

            def mock_execute_async(statement, parameters=None, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1 and query in str(statement):
                    future = Mock()
                    future.result.side_effect = ReadTimeout(
                        "Read timeout",
                        consistency=1,
                        received_responses=1,
                        required_responses=2,
                        data_retrieved=True,
                    )
                    return future
                return original_execute_async(statement, parameters, *args, **kwargs)

            with patch.object(cassandra_session._session, "execute_async", mock_execute_async):
                # All should succeed after retry
                if params:
                    result = await cassandra_session.execute(query, params)
                else:
                    result = await cassandra_session.execute(query)
                
                # Verify we got results
                assert result is not None

            # Verify retry happened
            assert call_count >= 2, f"Query '{query}' was not retried"