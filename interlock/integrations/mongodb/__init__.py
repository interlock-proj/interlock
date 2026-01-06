"""MongoDB integration for Interlock.

Provides MongoDB-backed implementations for:
- EventStore: Durable event persistence with optimistic concurrency control
- SagaStateStore: Persistent saga state management with step idempotency
- AggregateSnapshotStorageBackend: Aggregate snapshot storage (single or multiple versions)
- IdempotencyStorageBackend: Command idempotency tracking with TTL-based cleanup

The MongoConfiguration class acts as both a settings container and a factory
for MongoDB resources (client, database, collections).

Type resolution is automatic - event, state, and aggregate types are
dynamically loaded from their stored qualified names using Python's import
machinery. No manual type registration is required.

Example:
    >>> from interlock.integrations.mongodb import (
    ...     MongoConfiguration,
    ...     MongoEventStore,
    ...     MongoSagaStateStore,
    ...     MongoSnapshotStorage,
    ...     MongoIdempotencyStorage,
    ... )
    >>>
    >>> # Configuration provides client, db, and collection access
    >>> config = MongoConfiguration()
    >>>
    >>> app = (
    ...     ApplicationBuilder()
    ...     .register_dependency(MongoConfiguration, lambda: config)
    ...     .register_dependency(EventStore, MongoEventStore)
    ...     .register_dependency(SagaStateStore, MongoSagaStateStore)
    ...     .register_dependency(AggregateSnapshotStorageBackend, MongoSnapshotStorage)
    ...     .register_dependency(IdempotencyStorageBackend, MongoIdempotencyStorage)
    ...     .build()
    ... )
"""

from interlock.integrations.mongodb.collection import IndexDirection, IndexSpec
from interlock.integrations.mongodb.config import MongoConfiguration
from interlock.integrations.mongodb.event_store import MongoEventStore
from interlock.integrations.mongodb.idempotency import MongoIdempotencyStorage
from interlock.integrations.mongodb.saga_store import MongoSagaStateStore
from interlock.integrations.mongodb.snapshot_storage import MongoSnapshotStorage

__all__ = [
    "IndexDirection",
    "IndexSpec",
    "MongoConfiguration",
    "MongoEventStore",
    "MongoSagaStateStore",
    "MongoSnapshotStorage",
    "MongoIdempotencyStorage",
]
