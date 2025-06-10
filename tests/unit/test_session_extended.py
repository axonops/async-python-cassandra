"""
Extended unit tests for session module to improve coverage.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from cassandra import InvalidRequest, ReadTimeout
from cassandra.cluster import _NOT_SET, EXEC_PROFILE_DEFAULT, ResultSet, Session
from cassandra.query import BatchStatement, PreparedStatement, SimpleStatement

from async_cassandra.exceptions import ConnectionError
from async_cassandra.session import AsyncCassandraSession
from async_cassandra.streaming import AsyncStreamingResultSet, StreamConfig


class TestAsyncCassandraSessionExtended:
    """Extended tests for AsyncCassandraSession."""

    @pytest.mark.asyncio
    async def test_execute_with_metrics(self):
        """Test execute method with metrics recording."""
        # Mock metrics
        mock_metrics = AsyncMock()
        mock_metrics.record_query_metrics = AsyncMock()

        # Mock result
        mock_result = Mock(spec=ResultSet)
        mock_result._rows = [1, 2, 3]

        # Mock session
        mock_session = Mock(spec=Session)
        mock_session.execute_async = Mock()
        mock_future = Mock()
        mock_future.result = Mock(return_value=mock_result)
        mock_session.execute_async.return_value = mock_future
        mock_session.is_shutdown = False

        async_session = AsyncCassandraSession(mock_session, "test_keyspace")
        async_session._metrics = mock_metrics

        # Execute query
        await async_session.execute("SELECT * FROM users", [123])

        # Verify metrics were recorded
        mock_metrics.record_query_metrics.assert_called_once()
        call_args = mock_metrics.record_query_metrics.call_args[1]
        assert call_args["query"] == "SELECT * FROM users"
        assert call_args["success"] is True
        assert call_args["error_type"] is None
        assert call_args["parameters_count"] == 1
        assert call_args["result_size"] == 3
        assert call_args["duration"] > 0

    @pytest.mark.asyncio
    async def test_execute_with_metrics_on_error(self):
        """Test execute method records metrics on error."""
        # Mock metrics
        mock_metrics = AsyncMock()
        mock_metrics.record_query_metrics = AsyncMock()

        # Mock session that raises exception
        mock_session = Mock(spec=Session)
        mock_session.execute_async = Mock(side_effect=InvalidRequest("Bad query"))
        mock_session.is_shutdown = False

        async_session = AsyncCassandraSession(mock_session, "test_keyspace")
        async_session._metrics = mock_metrics

        # Execute query that will fail
        with pytest.raises(InvalidRequest):
            await async_session.execute("INVALID QUERY")

        # Verify error metrics were recorded
        mock_metrics.record_query_metrics.assert_called_once()
        call_args = mock_metrics.record_query_metrics.call_args[1]
        assert call_args["success"] is False
        assert call_args["error_type"] == "InvalidRequest"
        assert call_args["result_size"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_prepared_statement(self):
        """Test execute with PreparedStatement."""
        # Mock prepared statement
        mock_prepared = Mock(spec=PreparedStatement)
        mock_prepared.query_string = "INSERT INTO users (id, name) VALUES (?, ?)"

        # Mock result
        mock_result = Mock(spec=ResultSet)
        mock_result._rows = []

        # Mock session
        mock_session = Mock(spec=Session)
        mock_future = Mock()
        mock_future.result = Mock(return_value=mock_result)
        mock_session.execute_async = Mock(return_value=mock_future)
        mock_session.is_shutdown = False

        async_session = AsyncCassandraSession(mock_session)

        # Execute prepared statement
        await async_session.execute(mock_prepared, [123, "John"])

        # Verify execution
        mock_session.execute_async.assert_called_once_with(
            mock_prepared,
            [123, "John"],
            False,  # trace
            None,  # custom_payload
            _NOT_SET,  # timeout
            EXEC_PROFILE_DEFAULT,  # execution_profile
            None,  # paging_state
            None,  # host
            None,  # execute_as
        )

    @pytest.mark.asyncio
    async def test_execute_stream_success(self):
        """Test execute_stream method."""
        # Mock streaming result
        mock_streaming_result = Mock(spec=AsyncStreamingResultSet)

        # Mock handler
        with patch("async_cassandra.session.StreamingResultHandler") as mock_handler_class:
            mock_handler = Mock()
            mock_handler.get_streaming_result = AsyncMock(return_value=mock_streaming_result)
            mock_handler_class.return_value = mock_handler

            # Mock session
            mock_session = Mock(spec=Session)
            mock_future = Mock()
            mock_session.execute_async = Mock(return_value=mock_future)
            mock_session.is_shutdown = False

            async_session = AsyncCassandraSession(mock_session)

            # Execute streaming query
            stream_config = StreamConfig(fetch_size=1000)
            result = await async_session.execute_stream(
                "SELECT * FROM large_table", stream_config=stream_config
            )

            assert result == mock_streaming_result
            mock_handler_class.assert_called_once_with(mock_future, stream_config)

    @pytest.mark.asyncio
    async def test_execute_stream_with_parameters(self):
        """Test execute_stream with all parameters."""
        # Mock handler
        with patch("async_cassandra.session.StreamingResultHandler") as mock_handler_class:
            mock_handler = Mock()
            mock_handler.get_streaming_result = AsyncMock(return_value=Mock())
            mock_handler_class.return_value = mock_handler

            # Mock session
            mock_session = Mock(spec=Session)
            mock_future = Mock()
            mock_session.execute_async = Mock(return_value=mock_future)
            mock_session.is_shutdown = False

            async_session = AsyncCassandraSession(mock_session)

            # Execute with all parameters
            await async_session.execute_stream(
                "SELECT * FROM users WHERE id = ?",
                parameters=[123],
                stream_config=StreamConfig(fetch_size=500),
                trace=True,
                custom_payload={"key": b"value"},
                timeout=30.0,
                execution_profile="custom_profile",
                paging_state=b"paging_state",
                host=Mock(),
                execute_as="other_user",
            )

            # Verify all parameters were passed
            mock_session.execute_async.assert_called_once()
            call_args = mock_session.execute_async.call_args[0]
            assert call_args[0] == "SELECT * FROM users WHERE id = ?"
            assert call_args[1] == [123]
            assert call_args[2] is True  # trace
            assert call_args[3] == {"key": b"value"}  # custom_payload
            assert call_args[4] == 30.0  # timeout

    @pytest.mark.asyncio
    async def test_execute_stream_error_handling(self):
        """Test execute_stream error handling."""
        # Mock session that raises exception
        mock_session = Mock(spec=Session)
        mock_session.execute_async = Mock(side_effect=ReadTimeout("Read timeout"))
        mock_session.is_shutdown = False

        async_session = AsyncCassandraSession(mock_session)

        # Should raise original Cassandra exception, not wrapped
        with pytest.raises(ReadTimeout):
            await async_session.execute_stream("SELECT * FROM large_table")

    @pytest.mark.asyncio
    async def test_execute_stream_on_closed_session(self):
        """Test execute_stream on closed session."""
        mock_session = Mock(spec=Session)
        mock_session.is_shutdown = True

        async_session = AsyncCassandraSession(mock_session)

        with pytest.raises(ConnectionError):
            await async_session.execute_stream("SELECT * FROM table")

    @pytest.mark.asyncio
    async def test_execute_batch(self):
        """Test executing batch statements."""
        # Create batch statement
        batch = BatchStatement()

        # Mock result
        mock_result = Mock(spec=ResultSet)
        mock_result._rows = []

        # Mock session
        mock_session = Mock(spec=Session)
        mock_future = Mock()
        mock_future.result = Mock(return_value=mock_result)
        mock_session.execute_async = Mock(return_value=mock_future)
        mock_session.is_shutdown = False

        async_session = AsyncCassandraSession(mock_session)

        # Execute batch
        await async_session.execute(batch)

        # Verify batch was executed
        mock_session.execute_async.assert_called_once()
        call_args = mock_session.execute_async.call_args[0]
        assert call_args[0] == batch

    @pytest.mark.asyncio
    async def test_execute_with_simple_statement(self):
        """Test execute with SimpleStatement."""
        # Create simple statement
        stmt = SimpleStatement(
            "SELECT * FROM users WHERE id = ?", consistency_level=1  # ConsistencyLevel.ONE
        )

        # Mock result
        mock_result = Mock(spec=ResultSet)
        mock_result._rows = [{"id": 1, "name": "John"}]

        # Mock session
        mock_session = Mock(spec=Session)
        mock_future = Mock()
        mock_future.result = Mock(return_value=mock_result)
        mock_session.execute_async = Mock(return_value=mock_future)
        mock_session.is_shutdown = False

        async_session = AsyncCassandraSession(mock_session)

        # Execute statement
        await async_session.execute(stmt, [123])

        # Verify execution
        mock_session.execute_async.assert_called_once()
        call_args = mock_session.execute_async.call_args[0]
        assert call_args[0] == stmt
        assert call_args[1] == [123]

    @pytest.mark.asyncio
    async def test_execute_with_dict_parameters(self):
        """Test execute with dictionary parameters."""
        # Mock result
        mock_result = Mock(spec=ResultSet)
        mock_result._rows = []

        # Mock session
        mock_session = Mock(spec=Session)
        mock_future = Mock()
        mock_future.result = Mock(return_value=mock_result)
        mock_session.execute_async = Mock(return_value=mock_future)
        mock_session.is_shutdown = False

        async_session = AsyncCassandraSession(mock_session)

        # Execute with dict parameters
        await async_session.execute(
            "SELECT * FROM users WHERE id = :user_id AND name = :name",
            {"user_id": 123, "name": "John"},
        )

        # Verify parameters were passed correctly
        mock_session.execute_async.assert_called_once()
        call_args = mock_session.execute_async.call_args[0]
        assert call_args[1] == {"user_id": 123, "name": "John"}

    @pytest.mark.asyncio
    async def test_set_keyspace_error_handling(self):
        """Test set_keyspace with various error conditions."""
        # Mock session
        mock_session = Mock(spec=Session)
        mock_session.is_shutdown = False

        # Test with InvalidRequest
        mock_session.execute_async = Mock(side_effect=InvalidRequest("Invalid keyspace"))
        async_session = AsyncCassandraSession(mock_session)

        with pytest.raises(InvalidRequest):
            await async_session.set_keyspace("bad-keyspace-name!")

    @pytest.mark.asyncio
    async def test_concurrent_execute_calls(self):
        """Test multiple concurrent execute calls."""
        # Mock results
        mock_results = []
        for i in range(10):
            result = Mock(spec=ResultSet)
            result._rows = [{"id": i}]
            mock_results.append(result)

        # Mock session with different results for each call
        mock_session = Mock(spec=Session)
        mock_session.is_shutdown = False

        call_count = 0

        def execute_async_side_effect(*args, **kwargs):
            nonlocal call_count
            future = Mock()
            future.result = Mock(return_value=mock_results[call_count])
            call_count += 1
            return future

        mock_session.execute_async = Mock(side_effect=execute_async_side_effect)

        async_session = AsyncCassandraSession(mock_session)

        # Execute multiple queries concurrently
        tasks = []
        for i in range(10):
            task = async_session.execute(f"SELECT * FROM table{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify all executed successfully
        assert len(results) == 10
        assert all(isinstance(r, AsyncMock) or hasattr(r, "all") for r in results)
        assert mock_session.execute_async.call_count == 10
