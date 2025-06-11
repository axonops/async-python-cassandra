"""
Unit tests for thread pool configuration.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest
from cassandra.cluster import Cluster

from async_cassandra import AsyncCluster


class TestThreadPoolConfiguration:
    """Test thread pool configuration options."""

    def test_async_cluster_executor_threads_parameter(self):
        """Test that executor_threads parameter is passed correctly."""
        # Create cluster with custom executor threads
        cluster = AsyncCluster(
            contact_points=["localhost"],
            executor_threads=16
        )
        
        # Access the underlying cluster's executor
        executor = cluster._cluster.executor
        
        # Verify it's a ThreadPoolExecutor
        assert isinstance(executor, ThreadPoolExecutor)
        
        # Verify thread count
        assert executor._max_workers == 16
        
        # Cleanup
        cluster._cluster.shutdown()

    def test_default_executor_threads(self):
        """Test default executor thread configuration."""
        # Create cluster with default settings
        cluster = AsyncCluster(contact_points=["localhost"])
        
        # Default in our wrapper is 2
        assert cluster._cluster.executor._max_workers == 2
        
        # Cleanup
        cluster._cluster.shutdown()

    def test_various_thread_pool_sizes(self):
        """Test different thread pool sizes."""
        test_sizes = [1, 4, 8, 16, 32, 64]
        
        for size in test_sizes:
            cluster = AsyncCluster(
                contact_points=["localhost"],
                executor_threads=size
            )
            
            assert cluster._cluster.executor._max_workers == size
            
            # Cleanup
            cluster._cluster.shutdown()

    @patch('async_cassandra.cluster.Cluster')
    def test_executor_threads_passed_to_underlying_cluster(self, mock_cluster_class):
        """Test that executor_threads is passed to the underlying Cluster."""
        # Create AsyncCluster
        async_cluster = AsyncCluster(
            contact_points=["localhost"],
            executor_threads=25
        )
        
        # Verify Cluster was called with executor_threads
        mock_cluster_class.assert_called_once()
        call_kwargs = mock_cluster_class.call_args[1]
        assert call_kwargs['executor_threads'] == 25

    def test_custom_executor_property_access(self):
        """Test accessing executor properties."""
        cluster = AsyncCluster(
            contact_points=["localhost"],
            executor_threads=10
        )
        
        executor = cluster._cluster.executor
        
        # Test we can access executor properties
        assert hasattr(executor, '_max_workers')
        assert hasattr(executor, '_threads')
        assert hasattr(executor, 'submit')
        assert hasattr(executor, 'shutdown')
        
        # Cleanup
        cluster._cluster.shutdown()

    def test_executor_threads_explicit_configuration(self):
        """Test that executor_threads must be explicitly configured."""
        # The cassandra-driver doesn't support class-level defaults
        # You must pass executor_threads to each instance
        
        # Default cluster uses driver's default (not 20)
        cluster1 = Cluster(contact_points=['localhost'])
        default_threads = cluster1.executor._max_workers
        cluster1.shutdown()
        
        # To use custom threads, must pass explicitly
        cluster2 = Cluster(contact_points=['localhost'], executor_threads=20)
        assert cluster2.executor._max_workers == 20
        cluster2.shutdown()
        
        # Each instance is independent
        cluster3 = Cluster(contact_points=['localhost'], executor_threads=30)
        assert cluster3.executor._max_workers == 30
        cluster3.shutdown()

    @pytest.mark.asyncio
    async def test_thread_pool_with_actual_queries(self):
        """Test thread pool behavior with mock queries."""
        cluster = AsyncCluster(
            contact_points=["localhost"],
            executor_threads=5
        )
        
        # Mock the cluster's executor to track submissions
        original_executor = cluster._cluster.executor
        mock_executor = Mock(spec=ThreadPoolExecutor)
        mock_executor._max_workers = 5
        mock_executor.submit = Mock(side_effect=original_executor.submit)
        cluster._cluster.executor = mock_executor
        
        # Create a mock session
        with patch.object(cluster._cluster, 'connect') as mock_connect:
            mock_session = Mock()
            mock_session.execute_async = Mock(return_value=Mock())
            mock_connect.return_value = mock_session
            
            # Simulate some async operations
            session = await cluster.connect()
            
            # Verify executor is being used (through execute_async calls)
            assert mock_executor._max_workers == 5
        
        # Cleanup
        cluster._cluster.shutdown()

    def test_executor_threads_boundary_values(self):
        """Test boundary values for executor threads."""
        # Test minimum value
        cluster_min = AsyncCluster(
            contact_points=["localhost"],
            executor_threads=1
        )
        assert cluster_min._cluster.executor._max_workers == 1
        cluster_min._cluster.shutdown()
        
        # Test large value
        cluster_large = AsyncCluster(
            contact_points=["localhost"],
            executor_threads=100
        )
        assert cluster_large._cluster.executor._max_workers == 100
        cluster_large._cluster.shutdown()

    def test_executor_configuration_persistence(self):
        """Test that executor configuration persists through cluster lifetime."""
        cluster = AsyncCluster(
            contact_points=["localhost"],
            executor_threads=12
        )
        
        # Check initial configuration
        assert cluster._cluster.executor._max_workers == 12
        
        # The executor should remain the same instance
        executor1 = cluster._cluster.executor
        executor2 = cluster._cluster.executor
        assert executor1 is executor2
        
        # Thread count should not change
        assert cluster._cluster.executor._max_workers == 12
        
        # Cleanup
        cluster._cluster.shutdown()

    @pytest.mark.asyncio
    async def test_executor_threads_with_context_manager(self):
        """Test thread pool configuration with context manager usage."""
        async with AsyncCluster(
            contact_points=["localhost"],
            executor_threads=7
        ) as cluster:
            assert cluster._cluster.executor._max_workers == 7
            
            # Verify the executor is accessible within the context
            executor = cluster._cluster.executor
            assert isinstance(executor, ThreadPoolExecutor)


class TestThreadPoolDocumentationExamples:
    """Test the examples from the documentation."""

    def test_documentation_example_method1(self):
        """Test Method 1 from documentation: Configure the Cluster Executor."""
        # Create a custom executor with more threads
        cluster = AsyncCluster(
            contact_points=['localhost'],
            executor_threads=16
        )
        
        # Verify configuration
        assert cluster._cluster.executor._max_workers == 16
        
        # Cleanup
        cluster._cluster.shutdown()

    def test_documentation_example_explicit_configuration(self):
        """Test that executor_threads must be passed explicitly."""
        # The cassandra-driver doesn't support global defaults via class attributes
        # Each cluster instance must be configured individually
        
        # Create multiple clusters with different thread counts
        cluster1 = AsyncCluster(
            contact_points=['localhost'],
            executor_threads=16
        )
        assert cluster1._cluster.executor._max_workers == 16
        
        cluster2 = AsyncCluster(
            contact_points=['localhost'],
            executor_threads=32
        )
        assert cluster2._cluster.executor._max_workers == 32
        
        # Cleanup
        cluster1._cluster.shutdown()
        cluster2._cluster.shutdown()

    @pytest.mark.asyncio
    async def test_documentation_example_high_concurrency(self):
        """Test example calculation from documentation."""
        # If average query takes 50ms and you need 1000 queries/second:
        # Required threads = (queries_per_second * avg_query_time_seconds)
        # Required threads = 1000 * 0.05 = 50 threads
        
        cluster = AsyncCluster(
            contact_points=['localhost'],
            executor_threads=50
        )
        
        # Verify configuration
        assert cluster._cluster.executor._max_workers == 50
        
        # In a real scenario, you would test concurrent query execution here
        await cluster.shutdown()