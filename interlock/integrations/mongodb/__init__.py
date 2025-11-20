"""MongoDB integration for interlock event sourcing framework.

This module provides MongoDB implementations of the EventStore,
AggregateSnapshotStorageBackend, SagaStateStore, IdempotencyStorageBackend,
and CheckpointBackend interfaces using async PyMongo driver.

Installation:
    pip install interlock[mongodb]

Usage:
    >>> from interlock.integrations.mongodb import (
    ...     MongoDBConfig,
    ...     MongoDBConnectionManager,
    ...     MongoDBEventStore,
    ...     MongoDBSnapshotBackend,
    ...     MongoDBSagaStateStore,
    ...     MongoDBIdempotencyBackend,
    ...     MongoDBCheckpointBackend,
    ...     SnapshotStorageStrategy,
    ... )
    >>>
    >>> config = MongoDBConfig(
    ...     uri="mongodb://localhost:27017",
    ...     database="myapp"
    ... )
    >>> manager = MongoDBConnectionManager(config)
    >>>
    >>> # Initialize event store
    >>> event_store = MongoDBEventStore(manager)
    >>> await event_store.initialize_schema()
    >>>
    >>> # Initialize snapshot backend
    >>> snapshot_backend = MongoDBSnapshotBackend(
    ...     manager,
    ...     strategy=SnapshotStorageStrategy.VERSIONED
    ... )
    >>> await snapshot_backend.initialize_schema()
    >>>
    >>> # Initialize saga state store
    >>> saga_store = MongoDBSagaStateStore(manager)
    >>> await saga_store.initialize_schema()
    >>>
    >>> # Initialize idempotency backend
    >>> idempotency_backend = MongoDBIdempotencyBackend(manager, ttl_seconds=86400)
    >>> await idempotency_backend.initialize_schema()
    >>>
    >>> # Initialize checkpoint backend
    >>> checkpoint_backend = MongoDBCheckpointBackend(manager)
    >>> await checkpoint_backend.initialize_schema()
"""

from .checkpoint import MongoDBCheckpointBackend
from .config import MongoDBConfig
from .connection import MongoDBConnectionManager
from .event_store import MongoDBEventStore
from .idempotency import MongoDBIdempotencyBackend
from .saga_state_store import MongoDBSagaStateStore
from .snapshot import MongoDBSnapshotBackend, SnapshotStorageStrategy

__all__ = [
    "MongoDBConfig",
    "MongoDBConnectionManager",
    "MongoDBEventStore",
    "MongoDBSnapshotBackend",
    "MongoDBSagaStateStore",
    "MongoDBIdempotencyBackend",
    "MongoDBCheckpointBackend",
    "SnapshotStorageStrategy",
]
