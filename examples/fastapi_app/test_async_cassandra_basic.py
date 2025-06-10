#!/usr/bin/env python3
"""
Basic test to verify async-cassandra wrapper functionality without Docker/Podman.
This test uses mocking to simulate Cassandra responses.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import uuid

# Test importing our async wrapper
from async_cassandra import AsyncCluster, AsyncCassandraSession, AsyncResultSet
from async_cassandra.exceptions import QueryError, ConnectionError


class TestAsyncCassandraWrapper:
    """Test the async-cassandra wrapper basic functionality."""
    
    @pytest.mark.asyncio
    async def test_import_and_basic_usage(self):
        """Test that we can import and use the async wrapper."""
        # Verify imports work
        assert AsyncCluster is not None
        assert AsyncCassandraSession is not None
        assert AsyncResultSet is not None
        
    @pytest.mark.asyncio
    async def test_cluster_creation(self):
        """Test creating an AsyncCluster instance."""
        with patch('async_cassandra.cluster.Cluster') as mock_cluster_class:
            # Create mock cluster instance
            mock_cluster = Mock()
            mock_cluster_class.return_value = mock_cluster
            
            # Create AsyncCluster
            async_cluster = AsyncCluster(
                contact_points=['localhost'],
                port=9042
            )
            
            # Verify cluster was created with correct parameters
            assert async_cluster is not None
            mock_cluster_class.assert_called_once()
            call_kwargs = mock_cluster_class.call_args.kwargs
            assert call_kwargs['contact_points'] == ['localhost']
            assert call_kwargs['port'] == 9042
            
    @pytest.mark.asyncio
    async def test_session_execute(self):
        """Test executing a query through AsyncCassandraSession."""
        with patch('async_cassandra.cluster.Cluster') as mock_cluster_class:
            # Setup mocks
            mock_cluster = Mock()
            mock_session = Mock()
            mock_response_future = Mock()
            mock_cluster_class.return_value = mock_cluster
            
            # Mock the connect method to return a session
            mock_cluster.connect.return_value = mock_session
            
            # Mock execute_async to return a ResponseFuture
            mock_response_future.has_more_pages = False
            mock_session.execute_async.return_value = mock_response_future
            
            # Create test data
            test_rows = [
                {'id': uuid.uuid4(), 'name': 'Test User', 'age': 25}
            ]
            
            # Setup the callback to be called with our test data
            def setup_callback(callback, errback):
                # Simulate successful query by calling callback
                callback(test_rows)
                return mock_response_future
                
            mock_response_future.add_callbacks.side_effect = setup_callback
            
            # Create AsyncCluster and connect
            async_cluster = AsyncCluster()
            
            # Patch the create method to avoid actual connection
            with patch('async_cassandra.session.AsyncCassandraSession.create') as mock_create:
                mock_async_session = AsyncCassandraSession(mock_session)
                mock_create.return_value = mock_async_session
                
                session = await async_cluster.connect()
                
                # Execute a query
                result = await session.execute("SELECT * FROM users")
                
                # Verify the result
                assert isinstance(result, AsyncResultSet)
                assert len(result) == 1
                assert result.one()['name'] == 'Test User'
                
    @pytest.mark.asyncio
    async def test_async_iteration(self):
        """Test async iteration over results."""
        # Create test data
        test_rows = [
            {'id': uuid.uuid4(), 'name': f'User {i}', 'age': 20 + i}
            for i in range(5)
        ]
        
        # Create AsyncResultSet
        result_set = AsyncResultSet(test_rows)
        
        # Test async iteration
        collected_rows = []
        async for row in result_set:
            collected_rows.append(row)
            
        assert len(collected_rows) == 5
        assert collected_rows[0]['name'] == 'User 0'
        assert collected_rows[4]['name'] == 'User 4'
        
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in async operations."""
        with patch('async_cassandra.cluster.Cluster') as mock_cluster_class:
            # Setup mocks
            mock_cluster = Mock()
            mock_session = Mock()
            mock_response_future = Mock()
            mock_cluster_class.return_value = mock_cluster
            mock_cluster.connect.return_value = mock_session
            
            # Mock execute_async to return a ResponseFuture that will error
            mock_session.execute_async.return_value = mock_response_future
            
            # Setup the errback to be called with an error
            def setup_error_callback(callback, errback):
                # Simulate query error
                errback(Exception("Simulated query error"))
                return mock_response_future
                
            mock_response_future.add_callbacks.side_effect = setup_error_callback
            
            # Create AsyncCluster and connect
            async_cluster = AsyncCluster()
            
            with patch('async_cassandra.session.AsyncCassandraSession.create') as mock_create:
                mock_async_session = AsyncCassandraSession(mock_session)
                mock_create.return_value = mock_async_session
                
                session = await async_cluster.connect()
                
                # Execute a query that will fail
                with pytest.raises(Exception) as exc_info:
                    await session.execute("SELECT * FROM users")
                
                assert "Simulated query error" in str(exc_info.value)
                
    @pytest.mark.asyncio
    async def test_prepared_statements(self):
        """Test preparing statements."""
        with patch('async_cassandra.cluster.Cluster') as mock_cluster_class:
            # Setup mocks
            mock_cluster = Mock()
            mock_session = Mock()
            mock_prepared = Mock()
            mock_cluster_class.return_value = mock_cluster
            mock_cluster.connect.return_value = mock_session
            
            # Mock prepare to return a prepared statement
            mock_session.prepare.return_value = mock_prepared
            
            # Create AsyncCluster and connect
            async_cluster = AsyncCluster()
            
            with patch('async_cassandra.session.AsyncCassandraSession.create') as mock_create:
                mock_async_session = AsyncCassandraSession(mock_session)
                mock_create.return_value = mock_async_session
                
                session = await async_cluster.connect()
                
                # Prepare a statement
                prepared = await session.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
                
                assert prepared == mock_prepared
                mock_session.prepare.assert_called_once_with("INSERT INTO users (id, name) VALUES (?, ?)", None)
                
    @pytest.mark.asyncio
    async def test_context_managers(self):
        """Test async context manager support."""
        with patch('async_cassandra.cluster.Cluster') as mock_cluster_class:
            mock_cluster = Mock()
            mock_cluster_class.return_value = mock_cluster
            mock_cluster.shutdown = Mock()
            
            # Test cluster context manager
            async with AsyncCluster() as cluster:
                assert isinstance(cluster, AsyncCluster)
                assert not cluster.is_closed
                
            # Verify shutdown was called
            mock_cluster.shutdown.assert_called_once()
            
    @pytest.mark.asyncio 
    async def test_keyspace_validation(self):
        """Test keyspace name validation."""
        with patch('async_cassandra.cluster.Cluster') as mock_cluster_class:
            # Setup mocks
            mock_cluster = Mock()
            mock_session = Mock()
            mock_cluster_class.return_value = mock_cluster
            mock_cluster.connect.return_value = mock_session
            
            # Create AsyncCluster and connect
            async_cluster = AsyncCluster()
            
            with patch('async_cassandra.session.AsyncCassandraSession.create') as mock_create:
                mock_async_session = AsyncCassandraSession(mock_session)
                mock_create.return_value = mock_async_session
                
                session = await async_cluster.connect()
                
                # Test valid keyspace name
                await session.set_keyspace("valid_keyspace")
                
                # Test invalid keyspace names
                invalid_names = [
                    "",
                    "keyspace with spaces",
                    "keyspace-with-dash",
                    "keyspace;drop"
                ]
                
                for invalid_name in invalid_names:
                    with pytest.raises(ValueError) as exc_info:
                        await session.set_keyspace(invalid_name)
                    assert "Invalid keyspace name" in str(exc_info.value)


async def run_basic_tests():
    """Run basic tests to verify the wrapper works."""
    print("Testing async-cassandra wrapper...")
    
    # Test basic import
    try:
        from async_cassandra import AsyncCluster, AsyncCassandraSession
        print("✓ Imports successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False
        
    # Test cluster creation
    try:
        with patch('async_cassandra.cluster.Cluster') as mock_cluster:
            cluster = AsyncCluster(contact_points=['localhost'])
            print("✓ AsyncCluster creation successful")
    except Exception as e:
        print(f"✗ Cluster creation failed: {e}")
        return False
        
    # Test AsyncResultSet
    try:
        from async_cassandra.result import AsyncResultSet
        test_data = [{'id': 1, 'name': 'test'}]
        result_set = AsyncResultSet(test_data)
        assert len(result_set) == 1
        assert result_set.one()['name'] == 'test'
        print("✓ AsyncResultSet works correctly")
    except Exception as e:
        print(f"✗ AsyncResultSet test failed: {e}")
        return False
        
    print("\nAll basic tests passed! ✅")
    return True


if __name__ == "__main__":
    # Run basic tests
    asyncio.run(run_basic_tests())
    
    # Run pytest
    print("\nRunning detailed pytest suite...")
    pytest.main([__file__, "-v"])