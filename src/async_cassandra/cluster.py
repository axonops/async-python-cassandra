"""
Async cluster management for Cassandra connections.
"""

import asyncio
from ssl import SSLContext
from typing import Dict, List, Optional

from cassandra.auth import AuthProvider, PlainTextAuthProvider
from cassandra.cluster import Cluster, Metadata
from cassandra.policies import (
    DCAwareRoundRobinPolicy,
    ExponentialReconnectionPolicy,
    LoadBalancingPolicy,
    ReconnectionPolicy,
    RetryPolicy,
    TokenAwarePolicy,
)

from .base import AsyncCloseable, AsyncContextManageable
from .exceptions import ConnectionError
from .retry_policy import AsyncRetryPolicy
from .session import AsyncCassandraSession


class AsyncCluster(AsyncCloseable, AsyncContextManageable):
    """
    Async wrapper for Cassandra Cluster.

    Manages cluster configuration and connection lifecycle with async support.
    """

    def __init__(
        self,
        contact_points: Optional[List[str]] = None,
        port: int = 9042,
        auth_provider: Optional[AuthProvider] = None,
        load_balancing_policy: Optional[LoadBalancingPolicy] = None,
        reconnection_policy: Optional[ReconnectionPolicy] = None,
        retry_policy: Optional[RetryPolicy] = None,
        ssl_context: Optional[SSLContext] = None,
        protocol_version: Optional[int] = None,
        executor_threads: int = 2,
        max_schema_agreement_wait: int = 10,
        control_connection_timeout: float = 2.0,
        idle_heartbeat_interval: float = 30.0,
        schema_event_refresh_window: float = 2.0,
        topology_event_refresh_window: float = 10.0,
        status_event_refresh_window: float = 2.0,
        **kwargs: Dict[str, object],
    ):
        """
        Initialize async cluster wrapper.

        Args:
            contact_points: List of contact points to connect to.
            port: Port to connect to on contact points.
            auth_provider: Authentication provider.
            load_balancing_policy: Load balancing policy to use.
            reconnection_policy: Reconnection policy to use.
            retry_policy: Retry policy to use.
            ssl_context: SSL context for secure connections.
            protocol_version: CQL protocol version to use.
            executor_threads: Number of executor threads.
            max_schema_agreement_wait: Max time to wait for schema agreement.
            control_connection_timeout: Timeout for control connection.
            idle_heartbeat_interval: Interval for idle heartbeats.
            schema_event_refresh_window: Window for schema event refresh.
            topology_event_refresh_window: Window for topology event refresh.
            status_event_refresh_window: Window for status event refresh.
            **kwargs: Additional cluster options as key-value pairs.
        """
        # Set defaults
        if contact_points is None:
            contact_points = ["127.0.0.1"]

        if load_balancing_policy is None:
            load_balancing_policy = TokenAwarePolicy(DCAwareRoundRobinPolicy())

        if reconnection_policy is None:
            reconnection_policy = ExponentialReconnectionPolicy(base_delay=1.0, max_delay=60.0)

        if retry_policy is None:
            retry_policy = AsyncRetryPolicy()

        # Create the underlying cluster with only non-None parameters
        cluster_kwargs = {
            "contact_points": contact_points,
            "port": port,
            "load_balancing_policy": load_balancing_policy,
            "reconnection_policy": reconnection_policy,
            "default_retry_policy": retry_policy,
            "executor_threads": executor_threads,
            "max_schema_agreement_wait": max_schema_agreement_wait,
            "control_connection_timeout": control_connection_timeout,
            "idle_heartbeat_interval": idle_heartbeat_interval,
            "schema_event_refresh_window": schema_event_refresh_window,
            "topology_event_refresh_window": topology_event_refresh_window,
            "status_event_refresh_window": status_event_refresh_window,
        }

        # Add optional parameters only if they're not None
        if auth_provider is not None:
            cluster_kwargs["auth_provider"] = auth_provider
        if ssl_context is not None:
            cluster_kwargs["ssl_context"] = ssl_context
        if protocol_version is not None:
            cluster_kwargs["protocol_version"] = protocol_version

        # Merge with any additional kwargs
        cluster_kwargs.update(kwargs)

        super().__init__()
        self._cluster = Cluster(**cluster_kwargs)

    @classmethod
    def create_with_auth(
        cls, contact_points: List[str], username: str, password: str, **kwargs: Dict[str, object]
    ) -> "AsyncCluster":
        """
        Create cluster with username/password authentication.

        Args:
            contact_points: List of contact points to connect to.
            username: Username for authentication.
            password: Password for authentication.
            **kwargs: Additional cluster options as key-value pairs.

        Returns:
            New AsyncCluster instance.
        """
        auth_provider = PlainTextAuthProvider(username=username, password=password)

        return cls(contact_points=contact_points, auth_provider=auth_provider, **kwargs)  # type: ignore[arg-type]

    async def connect(
        self, keyspace: Optional[str] = None, timeout: Optional[float] = None
    ) -> AsyncCassandraSession:
        """
        Connect to the cluster and create a session.

        Args:
            keyspace: Optional keyspace to use.
            timeout: Connection timeout in seconds. Defaults to DEFAULT_CONNECTION_TIMEOUT.

        Returns:
            New AsyncCassandraSession.

        Raises:
            ConnectionError: If connection fails.
            asyncio.TimeoutError: If connection times out.
        """
        if self.is_closed:
            raise ConnectionError("Cluster is closed")

        # Import here to avoid circular import
        from .constants import DEFAULT_CONNECTION_TIMEOUT

        if timeout is None:
            timeout = DEFAULT_CONNECTION_TIMEOUT

        try:
            session = await asyncio.wait_for(
                AsyncCassandraSession.create(self._cluster, keyspace), timeout=timeout
            )
            return session

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to connect to cluster: {str(e)}") from e

    async def _do_close(self) -> None:
        """Perform the actual cluster shutdown."""
        loop = asyncio.get_event_loop()
        # Use a reasonable timeout for shutdown operations
        await asyncio.wait_for(
            loop.run_in_executor(None, self._cluster.shutdown), timeout=30.0
        )

    async def shutdown(self) -> None:
        """
        Shutdown the cluster and release all resources.

        This method is idempotent and can be called multiple times safely.
        """
        await self.close()

    @property
    def metadata(self) -> Metadata:
        """Get cluster metadata."""
        return self._cluster.metadata

    def register_user_type(self, keyspace: str, user_type: str, klass: type) -> None:
        """
        Register a user-defined type.

        Args:
            keyspace: Keyspace containing the type.
            user_type: Name of the user-defined type.
            klass: Python class to map the type to.
        """
        self._cluster.register_user_type(keyspace, user_type, klass)
