"""Neo4j integration for interlock event sourcing framework.

This module provides Neo4j implementations of the EventStore,
AggregateSnapshotStorageBackend, and SagaStateStore interfaces
using async Neo4j driver.

Installation:
    pip install interlock[neo4j]

Usage:
    >>> from interlock.integrations.neo4j import (
    ...     Neo4jConfig,
    ...     Neo4jConnectionManager,
    ...     Neo4jEventStore,
    ...     Neo4jSnapshotBackend,
    ...     Neo4jSagaStateStore,
    ...     SnapshotStorageStrategy,
    ... )
    >>>
    >>> config = Neo4jConfig(
    ...     uri="bolt://localhost:7687",
    ...     username="neo4j",
    ...     password="password"
    ... )
    >>> manager = Neo4jConnectionManager(config)
    >>>
    >>> # Initialize event store
    >>> event_store = Neo4jEventStore(manager)
    >>> await event_store.initialize_schema()
    >>>
    >>> # Initialize snapshot backend
    >>> snapshot_backend = Neo4jSnapshotBackend(
    ...     manager,
    ...     strategy=SnapshotStorageStrategy.VERSIONED
    ... )
    >>> await snapshot_backend.initialize_schema()
    >>>
    >>> # Initialize saga state store
    >>> saga_store = Neo4jSagaStateStore(manager)
    >>> await saga_store.initialize_schema()
"""

from .config import Neo4jConfig
from .connection import Neo4jConnectionManager
from .event_store import Neo4jEventStore
from .saga_state_store import Neo4jSagaStateStore
from .snapshot import Neo4jSnapshotBackend, SnapshotStorageStrategy

__all__ = [
    "Neo4jConfig",
    "Neo4jConnectionManager",
    "Neo4jEventStore",
    "Neo4jSnapshotBackend",
    "Neo4jSagaStateStore",
    "SnapshotStorageStrategy",
]
